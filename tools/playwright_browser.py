"""Playwright browser tool using Vers VM.

Provides browser automation via Playwright running in a Vers cloud VM.
This avoids the need for Browserbase credentials.

Requires:
- VERS_API_KEY environment variable
- vers CLI installed
"""

import json
import logging
import os
import time
from typing import Optional

from tools.registry import registry

logger = logging.getLogger(__name__)

# Singleton Vers VM for browser operations
_browser_vm = None
_browser_ready = False


def check_playwright_requirements() -> bool:
    """Check if Vers API key is available."""
    return bool(os.getenv("VERS_API_KEY"))


def _get_browser_vm():
    """Get or create the singleton browser VM with Playwright installed."""
    global _browser_vm, _browser_ready
    
    if _browser_vm and _browser_ready:
        return _browser_vm
    
    from tools.environments.vers import VersEnvironment
    
    logger.info("Creating Vers VM for Playwright browser...")
    
    _browser_vm = VersEnvironment(
        cwd="/root",
        timeout=120,
        vcpu=2,
        memory=4096,
        disk=8192,
        task_id="playwright-browser",
    )
    
    # Install Playwright and dependencies
    setup_script = """
set -e
apt-get update -qq
apt-get install -y -qq python3 python3-pip nodejs npm > /dev/null 2>&1
pip3 install playwright > /dev/null 2>&1
playwright install chromium > /dev/null 2>&1
playwright install-deps chromium > /dev/null 2>&1
echo "PLAYWRIGHT_READY"
"""
    
    result = _browser_vm.execute(setup_script, timeout=300)
    if "PLAYWRIGHT_READY" in result.get("output", ""):
        logger.info("Playwright browser VM ready")
        _browser_ready = True
    else:
        logger.error(f"Failed to setup Playwright: {result.get('output', '')}")
        raise RuntimeError("Failed to setup Playwright in Vers VM")
    
    return _browser_vm


def playwright_navigate(url: str, task_id: str = None) -> str:
    """Navigate to a URL and return the page content."""
    try:
        vm = _get_browser_vm()
        
        # Python script to navigate and get content
        script = f'''
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("{url}", timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    
    # Get text content
    title = page.title()
    text = page.inner_text("body")[:10000]  # Limit to 10k chars
    
    result = {{"title": title, "url": page.url, "content": text}}
    print("RESULT_JSON:" + json.dumps(result))
    browser.close()
'''
        
        result = vm.execute(f"python3 -c '{script}'", timeout=60)
        output = result.get("output", "")
        
        if "RESULT_JSON:" in output:
            json_str = output.split("RESULT_JSON:")[1].strip()
            # Get just the first line (the JSON)
            json_str = json_str.split("\n")[0]
            return json_str
        else:
            return json.dumps({"error": f"Navigation failed: {output}"})
            
    except Exception as e:
        logger.exception(f"Playwright navigate error: {e}")
        return json.dumps({"error": str(e)})


def playwright_snapshot(task_id: str = None) -> str:
    """Get the current page content (text snapshot)."""
    try:
        vm = _get_browser_vm()
        
        script = '''
import json
from playwright.sync_api import sync_playwright

# Try to reuse existing context or report no page
print("RESULT_JSON:" + json.dumps({"error": "No page open. Use playwright_navigate first."}))
'''
        result = vm.execute(f"python3 -c '{script}'", timeout=30)
        output = result.get("output", "")
        
        if "RESULT_JSON:" in output:
            json_str = output.split("RESULT_JSON:")[1].strip().split("\n")[0]
            return json_str
        
        return json.dumps({"error": "Failed to get snapshot"})
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def playwright_click(selector: str, task_id: str = None) -> str:
    """Click an element on the page."""
    return json.dumps({"error": "Click requires active page session. Use playwright_navigate first."})


def playwright_browser(action: str, url: str = None, selector: str = None, text: str = None, task_id: str = None) -> str:
    """
    Unified browser tool for web automation via Playwright.
    
    Actions:
    - navigate: Go to a URL (requires url parameter)
    - snapshot: Get current page text content
    - click: Click an element (requires selector)
    - type: Type text into an element (requires selector and text)
    """
    try:
        vm = _get_browser_vm()
        
        if action == "navigate":
            if not url:
                return json.dumps({"error": "url parameter required for navigate action"})
            
            script = f'''
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("{url}", timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    
    title = page.title()
    text = page.inner_text("body")[:15000]
    
    result = {{"success": True, "title": title, "url": page.url, "content": text}}
    print("RESULT_JSON:" + json.dumps(result))
    browser.close()
'''
            result = vm.execute(f"python3 -c '{script}'", timeout=60)
            
        elif action == "snapshot":
            return json.dumps({"error": "Snapshot requires persistent session. Use navigate to get page content."})
            
        else:
            return json.dumps({"error": f"Unknown action: {action}. Use: navigate, snapshot, click, type"})
        
        output = result.get("output", "")
        if "RESULT_JSON:" in output:
            json_str = output.split("RESULT_JSON:")[1].strip().split("\n")[0]
            return json_str
        else:
            return json.dumps({"error": f"Action failed: {output}"})
            
    except Exception as e:
        logger.exception(f"Playwright browser error: {e}")
        return json.dumps({"error": str(e)})


def cleanup_playwright_browser():
    """Cleanup the browser VM."""
    global _browser_vm, _browser_ready
    if _browser_vm:
        try:
            _browser_vm.cleanup()
        except Exception as e:
            logger.warning(f"Failed to cleanup browser VM: {e}")
        _browser_vm = None
        _browser_ready = False


# Register the unified browser tool
PLAYWRIGHT_BROWSER_SCHEMA = {
    "name": "playwright_browser",
    "description": """Browser automation tool using Playwright. Navigate to URLs and extract page content.

Actions:
- navigate: Go to a URL and get page content (requires 'url' parameter)

Example: {"action": "navigate", "url": "https://news.ycombinator.com"}

Returns page title and text content.""",
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
