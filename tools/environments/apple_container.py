"""Apple Container execution environment.

Executes commands in Apple Containers (macOS native containers).
https://github.com/apple/container

Requires:
- macOS with Apple Silicon or Rosetta
- container CLI installed: brew install apple/tap/container-tools
- Optionally GITHUB_API_KEY for GitHub admin tasks

Configuration (in config.yaml):
    terminal:
      backend: apple_container
      apple_container_image: ghcr.io/apple/container-base:latest
      apple_container_name: hermes-agent
"""

import json
import logging
import os
import subprocess
import threading
import time
from typing import Any, Dict, Optional

from tools.environments.base import BaseEnvironment
from tools.interrupt import is_interrupted

logger = logging.getLogger(__name__)


class AppleContainerEnvironment(BaseEnvironment):
    """Execute commands in an Apple Container.
    
    The container is created on first use and persists until cleanup() is called.
    Supports passing environment variables like GITHUB_API_KEY into the container.
    """
    
    def __init__(
        self,
        cwd: str = "/root",
        timeout: int = 60,
        image: str = "ghcr.io/hdresearch/hermes-github-admin:latest",
        container_name: str = None,
        task_id: str = "default",
        env: dict = None,
        inherit_env: list = None,
    ):
        super().__init__(cwd=cwd, timeout=timeout, env=env)
        
        self._image = image
        self._container_name = container_name or f"hermes-{task_id}"
        self._task_id = task_id
        self._inherit_env = inherit_env or ["GITHUB_API_KEY", "GITHUB_TOKEN"]
        
        # Container state
        self._container_id = None
        self._provisioned = False
    
    def _run_container_cmd(self, args: list, timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a container CLI command."""
        cmd = ["container"] + args
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Apple container CLI not found. Install with: "
                "brew install apple/tap/container-tools"
            )
    
    def _provision_container(self) -> None:
        """Create or connect to an Apple Container."""
        if self._provisioned:
            return
        
        # Check if container already exists
        result = self._run_container_cmd(["list", "--format", "json"])
        if result.returncode == 0:
            try:
                containers = json.loads(result.stdout) if result.stdout.strip() else []
                for container in containers:
                    if container.get("name") == self._container_name:
                        if container.get("state") == "running":
                            self._container_id = container.get("id")
                            self._provisioned = True
                            logger.info(f"Connected to existing container: {self._container_name}")
                            return
                        else:
                            # Remove stopped container
                            self._run_container_cmd(["rm", self._container_name])
            except json.JSONDecodeError:
                pass
        
        # Build environment variable arguments
        env_args = []
        for var in self._inherit_env:
            value = os.environ.get(var)
            if value:
                env_args.extend(["-e", f"{var}={value}"])
        
        # Also pass any custom env vars
        if self.env:
            for key, value in self.env.items():
                env_args.extend(["-e", f"{key}={value}"])
        
        # Create new container
        logger.info(f"Creating Apple Container: {self._container_name} from {self._image}")
        
        create_args = [
            "run", "-d",
            "--name", self._container_name,
        ] + env_args + [
            self._image,
            "sleep", "infinity",  # Keep container running
        ]
        
        result = self._run_container_cmd(create_args, timeout=120)
        
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create container: {result.stderr}")
        
        self._container_id = result.stdout.strip()
        self._provisioned = True
        logger.info(f"Created Apple Container: {self._container_id[:12]}")
        
        # Wait for container to be ready
        self._wait_for_ready()
    
    def _wait_for_ready(self, timeout: int = 30) -> None:
        """Wait for container to be ready."""
        start = time.time()
        while time.time() - start < timeout:
            result = self._run_container_cmd(
                ["exec", self._container_name, "echo", "ready"],
                timeout=10,
            )
            if result.returncode == 0 and "ready" in result.stdout:
                logger.info(f"Container {self._container_name} is ready")
                return
            time.sleep(1)
        
        logger.warning(f"Container may not be fully ready after {timeout}s")
    
    def execute(
        self,
        command: str,
        cwd: str = "",
        *,
        timeout: int | None = None,
        stdin_data: str | None = None,
    ) -> dict:
        """Execute a command in the Apple Container."""
        self._provision_container()
        
        exec_command = self._prepare_command(command)
        work_dir = cwd or self.cwd
        effective_timeout = timeout or self.timeout
        
        # Build the full command with cd if needed
        if work_dir and work_dir != "/":
            exec_command = f"cd {work_dir} && {exec_command}"
        
        # Use container exec
        cmd = [
            "container", "exec",
            self._container_name,
            "/bin/bash", "-c", exec_command,
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
                "output": "Apple container CLI not found. Install with: brew install apple/tap/container-tools",
                "returncode": 1,
            }
        except Exception as e:
            return {
                "output": f"Container execution error: {e}",
                "returncode": 1,
            }
    
    def cleanup(self) -> None:
        """Stop and remove the Apple Container."""
        if self._container_name and self._provisioned:
            try:
                logger.info(f"Cleaning up Apple Container: {self._container_name}")
                self._run_container_cmd(["stop", self._container_name], timeout=10)
                self._run_container_cmd(["rm", self._container_name], timeout=10)
            except Exception as e:
                logger.warning(f"Failed to cleanup container: {e}")
        
        self._provisioned = False
        self._container_id = None
    
    def get_container_id(self) -> Optional[str]:
        """Get the current container ID."""
        return self._container_id
