"""Playwright browser tool using Vers VM.

Provides browser automation via Playwright running in a Vers cloud VM.
This avoids the need for Browserbase credentials.

Requires:
- VERS_API_KEY environment variable
- vers CLI installed
- Pre-provisioned VM (run scripts/setup_playwright_vm.sh first)
  OR set PLAYWRIGHT_VM_ID environment variable
"""

import json
import logging
import os
import subprocess
import time
from typing import Optional

from tools.registry import registry

logger = logging.getLogger(__name__)

# Singleton VM ID
_playwright_vm_id: Optional[str] = None


def check_playwright_requirements() -> bool:
    """Check if Vers API key is available."""
    return bool(os.getenv("VERS_API_KEY"))


def _get_vm_id() -> Optional[str]:
    """Get the Playwright VM ID from env or saved file."""
    global _playwright_vm_id
    
    if _playwright_vm_id:
        return _playwright_vm_id
    
    # Check environment variable first
    vm_id = os.environ.get("PLAYWRIGHT_VM_ID")
    if vm_id:
        _playwright_vm_id = vm_id
        return vm_id
    
    # Check saved file
    vm_id_file = os.path.expanduser("~/.hermes/playwright_vm_id")
    if os.path.exists(vm_id_file):
        with open(vm_id_file) as f:
            vm_id = f.read().strip()
            if vm_id:
                _playwright_vm_id = vm_id
                return vm_id
    
    return None


def _vers_execute(vm_id: str, command: str, timeout: int = 60) -> dict:
    """Execute a command in a Vers VM."""
    try:
        result = subprocess.run(
            ["vers", "execute", vm_id, "--timeout", str(timeout), "--", "bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )
        return {
            "output": result.stdout + result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"output": "Command timed out", "returncode": 124}
    except FileNotFoundError:
        return {"output": "vers CLI not found", "returncode": 1}
    except Exception as e:
        return {"output": str(e), "returncode": 1}


def playwright_browser(action: str, url: str = None, selector: str = None, text: str = None, task_id: str = None) -> str:
    """
    Browser automation tool using Playwright in a Vers VM.
    
    Actions:
    - navigate: Go to a URL and get page content (requires url parameter)
    
    Returns JSON with page title and text content.
    """
    vm_id = _get_vm_id()
    
    if not vm_id:
        return json.dumps({
            "error": "No Playwright VM configured. Run: scripts/setup_playwright_vm.sh or set PLAYWRIGHT_VM_ID"
        })
    
    try:
        if action == "navigate":
            if not url:
                return json.dumps({"error": "url parameter required for navigate action"})
            
            # Escape the URL for shell
            safe_url = url.replace("'", "'\\''")
            
            # Python script to navigate and get content
            script = f'''
import json
import sys
from playwright.sync_api import sync_playwright

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto('{safe_url}', timeout=30000)
        page.wait_for_load_state('domcontentloaded')
        
        title = page.title()
        text = page.inner_text('body')[:15000]
        
        result = {{"success": True, "title": title, "url": page.url, "content": text}}
        print("RESULT_START" + json.dumps(result) + "RESULT_END")
        browser.close()
except Exception as e:
    print("RESULT_START" + json.dumps({{"error": str(e)}}) + "RESULT_END")
'''
            
            result = _vers_execute(vm_id, f"python3 -c '{script}'", timeout=60)
            output = result.get("output", "")
            
            # Extract JSON from output
            if "RESULT_START" in output and "RESULT_END" in output:
                start = output.index("RESULT_START") + len("RESULT_START")
                end = output.index("RESULT_END")
                json_str = output[start:end].strip()
                return json_str
            else:
                # Return raw output as error
                return json.dumps({"error": f"Unexpected output: {output[:500]}"})
        
        else:
            return json.dumps({"error": f"Unknown action: {action}. Use: navigate"})
            
    except Exception as e:
        logger.exception(f"Playwright browser error: {e}")
        return json.dumps({"error": str(e)})


def cleanup_playwright_browser():
    """Note: We don't cleanup the VM since it's meant to be persistent."""
    pass


# Register the tool
PLAYWRIGHT_BROWSER_SCHEMA = {
    "name": "playwright_browser",
    "description": """Browser automation tool using Playwright. Navigate to URLs and extract page content.

Actions:
- navigate: Go to a URL and get page content (requires 'url' parameter)

Example: {"action": "navigate", "url": "https://news.ycombinator.com"}

Returns JSON with page title, URL, and text content.""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["navigate"],
                "description": "The browser action to perform"
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to (required for 'navigate' action)"
            },
        },
        "required": ["action"]
    }
}

registry.register(
    name="playwright_browser",
    toolset="playwright",
    schema=PLAYWRIGHT_BROWSER_SCHEMA,
    handler=lambda args, **kw: playwright_browser(
        action=args.get("action", ""),
        url=args.get("url"),
        selector=args.get("selector"),
        text=args.get("text"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_playwright_requirements,
    requires_env=["VERS_API_KEY"],
)
