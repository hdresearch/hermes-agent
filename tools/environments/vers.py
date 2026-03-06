"""Vers VM execution environment.

Executes commands in Vers cloud VMs. Supports persistent VMs that
stay running between commands, with automatic provisioning.

Requires:
- VERS_API_KEY environment variable
- vers CLI installed (optional, for local tunnel access)

Configuration (in config.yaml):
    terminal:
      backend: vers
      vers_image: ubuntu:24.04  # or vers project with vers.toml
      vers_vm_id: <existing-vm-id>  # optional, reuse existing VM
      vers_vcpu: 4
      vers_memory: 4096  # MiB
      vers_disk: 8192    # MiB
"""

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from tools.environments.base import BaseEnvironment
from tools.interrupt import is_interrupted

logger = logging.getLogger(__name__)

VERS_API_BASE = "https://api.vers.sh/api/v1"


class VersEnvironment(BaseEnvironment):
    """Execute commands in a Vers cloud VM.
    
    The VM is created on first use and persists until cleanup() is called.
    Commands are executed via the Vers API (not SSH), so no local vers CLI
    is required for basic operation.
    """
    
    def __init__(
        self,
        cwd: str = "/root",
        timeout: int = 60,
        api_key: str = None,
        vm_id: str = None,
        vcpu: int = 4,
        memory: int = 4096,
        disk: int = 8192,
        task_id: str = "default",
        env: dict = None,
    ):
        super().__init__(cwd=cwd, timeout=timeout, env=env)
        
        self._api_key = api_key or os.getenv("VERS_API_KEY")
        if not self._api_key:
            raise ValueError("VERS_API_KEY environment variable required for vers backend")
        
        self._vm_id = vm_id
        self._vcpu = vcpu
        self._memory = memory
        self._disk = disk
        self._task_id = task_id
        self._client = httpx.Client(
            base_url=VERS_API_BASE,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        
        # Lazily provision VM on first command
        self._provisioned = False
        self._vm_info: Dict[str, Any] = {}
    
    def _api_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an API request to Vers."""
        try:
            response = self._client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response.json() if response.text else {}
        except httpx.HTTPStatusError as e:
            logger.error(f"Vers API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Vers API request failed: {e}")
            raise
    
    def _provision_vm(self) -> None:
        """Create or connect to a Vers VM."""
        if self._provisioned:
            return
        
        if self._vm_id:
            # Check if existing VM is running
            try:
                vms = self._api_request("GET", "/vms")
                for vm in vms:
                    if vm.get("vm_id") == self._vm_id:
                        if vm.get("state") == "running":
                            self._vm_info = vm
                            self._provisioned = True
                            logger.info(f"Connected to existing Vers VM: {self._vm_id}")
                            return
                        else:
                            logger.warning(f"VM {self._vm_id} exists but state is {vm.get('state')}")
            except Exception as e:
                logger.warning(f"Failed to check existing VM: {e}")
        
        # Create new VM
        logger.info(f"Provisioning new Vers VM (vcpu={self._vcpu}, mem={self._memory}MB, disk={self._disk}MB)")
        
        # Use vers CLI to create VM (API doesn't have direct create endpoint)
        try:
            result = subprocess.run(
                [
                    "vers", "run",
                    "-N", f"hermes-{self._task_id}",
                    "--vcpu-count", str(self._vcpu),
                    "--mem-size", str(self._memory),
                    "--fs-size-vm", str(self._disk),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"vers run failed: {result.stderr}")
            
            # Parse VM ID from output
            for line in result.stdout.split("\n"):
                if "VM '" in line and "' started successfully" in line:
                    # Extract: VM 'uuid' started successfully
                    start = line.find("'") + 1
                    end = line.find("'", start)
                    self._vm_id = line[start:end]
                    break
            
            if not self._vm_id:
                raise RuntimeError(f"Could not parse VM ID from: {result.stdout}")
            
            logger.info(f"Created Vers VM: {self._vm_id}")
            self._provisioned = True
            
            # Wait for VM to be ready
            self._wait_for_ready()
            
        except FileNotFoundError:
            raise RuntimeError("vers CLI not found. Install with: go install github.com/verscloud/vers@latest")
    
    def _wait_for_ready(self, timeout: int = 60) -> None:
        """Wait for VM to be ready to accept commands."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                # Try a simple command
                result = subprocess.run(
                    ["vers", "execute", self._vm_id, "--timeout", "10", "--", "echo", "ready"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0 and "ready" in result.stdout:
                    logger.info(f"VM {self._vm_id} is ready")
                    return
            except Exception:
                pass
            time.sleep(2)
        
        logger.warning(f"VM {self._vm_id} may not be fully ready after {timeout}s")
    
    def execute(
        self,
        command: str,
        cwd: str = "",
        *,
        timeout: int | None = None,
        stdin_data: str | None = None,
    ) -> dict:
        """Execute a command in the Vers VM."""
        self._provision_vm()
        
        exec_command = self._prepare_command(command)
        work_dir = cwd or self.cwd
        effective_timeout = timeout or self.timeout
        
        # Build the full command with cd if needed
        if work_dir and work_dir != "/":
            exec_command = f"cd {work_dir} && {exec_command}"
        
        # Use vers execute command
        cmd = [
            "vers", "execute", self._vm_id,
            "--timeout", str(effective_timeout),
            "--", "/bin/bash", "-c", exec_command,
        ]
        
        try:
            output_chunks = []
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE if stdin_data else subprocess.DEVNULL,
                text=True,
            )
            
            if stdin_data:
                try:
                    proc.stdin.write(stdin_data)
                    proc.stdin.close()
                except Exception:
                    pass
            
            def drain():
                try:
                    for line in proc.stdout:
                        output_chunks.append(line)
                except Exception:
                    pass
            
            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            deadline = time.monotonic() + effective_timeout
            
            while proc.poll() is None:
                if is_interrupted():
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    reader.join(timeout=2)
                    return {
                        "output": "".join(output_chunks) + "\n[Command interrupted]",
                        "returncode": 130,
                    }
                if time.monotonic() > deadline:
                    proc.kill()
                    reader.join(timeout=2)
                    return self._timeout_result(effective_timeout)
                time.sleep(0.2)
            
            reader.join(timeout=5)
            return {
                "output": "".join(output_chunks),
                "returncode": proc.returncode,
            }
            
        except FileNotFoundError:
            return {
                "output": "vers CLI not found. Install with: go install github.com/verscloud/vers@latest",
                "returncode": 1,
            }
        except Exception as e:
            return {
                "output": f"Vers execution error: {e}",
                "returncode": 1,
            }
    
    def cleanup(self) -> None:
        """Stop and delete the Vers VM."""
        if self._vm_id and self._provisioned:
            try:
                logger.info(f"Cleaning up Vers VM: {self._vm_id}")
                subprocess.run(
                    ["vers", "delete", self._vm_id, "-y"],
                    capture_output=True,
                    timeout=30,
                )
            except Exception as e:
                logger.warning(f"Failed to cleanup Vers VM: {e}")
        
        self._provisioned = False
        self._vm_id = None
        
        try:
            self._client.close()
        except Exception:
            pass
    
    def get_vm_id(self) -> Optional[str]:
        """Get the current VM ID (for reuse or debugging)."""
        return self._vm_id
    
    def get_public_url(self, port: int = 80) -> Optional[str]:
        """Get the public URL for a service running in the VM."""
        if not self._vm_id:
            return None
        return f"https://{self._vm_id}.vm.vers.sh"
