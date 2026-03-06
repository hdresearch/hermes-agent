"""
Shapez Factory Tool - Execute visual factory workflows.

This tool allows the agent to execute Shapez factory definitions,
which are visual workflows consisting of connected blocks.

Factories can include:
- Tool invocations (terminal, web_search, etc.)
- Sub-agent delegations with custom prompts
- Data transformations and routing
- Template-based prompt construction
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Add shapez to path if available
_shapez_path = Path(__file__).resolve().parents[1].parent / "shapez"
if _shapez_path.exists():
    sys.path.insert(0, str(_shapez_path))
    sys.path.insert(0, str(_shapez_path / "src"))

from tools.registry import registry


def check_shapez_requirements() -> bool:
    """Check if Shapez is available."""
    try:
        from core.factory import Factory
        return True
    except ImportError:
        return False


def execute_factory(
    factory_json: str,
    inputs: Optional[str] = None,
    task_id: str = None,
) -> str:
    """
    Execute a Shapez factory workflow.
    
    Args:
        factory_json: JSON string defining the factory workflow
        inputs: JSON string of input values to inject
        task_id: Task ID for session isolation
    
    Returns:
        JSON string with results or error
    """
    try:
        from core.factory import Factory
        import asyncio
        
        # Parse factory
        factory = Factory.from_json(factory_json)
        
        # Parse inputs
        input_dict = {}
        if inputs:
            input_dict = json.loads(inputs)
        
        # Execute
        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(
                factory.execute(inputs=input_dict)
            )
        finally:
            loop.close()
        
        return json.dumps({
            "success": True,
            "factory_name": factory.name,
            "results": results,
        }, ensure_ascii=False)
        
    except json.JSONDecodeError as e:
        return json.dumps({
            "success": False,
            "error": f"Invalid JSON: {e}",
        })
    except ImportError as e:
        return json.dumps({
            "success": False,
            "error": f"Shapez not available: {e}",
        })
    except Exception as e:
        logger.exception("Factory execution error")
        return json.dumps({
            "success": False,
            "error": str(e),
        })


def list_factories(
    directory: Optional[str] = None,
    task_id: str = None,
) -> str:
    """
    List available factory definitions.
    
    Args:
        directory: Directory to search (default: ~/.hermes/factories)
        task_id: Task ID for session isolation
    
    Returns:
        JSON string with factory list
    """
    try:
        if directory:
            search_dir = Path(directory).expanduser()
        else:
            search_dir = Path.home() / ".hermes" / "factories"
        
        if not search_dir.exists():
            return json.dumps({
                "success": True,
                "factories": [],
                "message": f"No factories directory at {search_dir}",
            })
        
        factories = []
        for f in search_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                factories.append({
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "path": str(f),
                    "blocks": len(data.get("blocks", [])),
                })
            except Exception:
                factories.append({
                    "name": f.stem,
                    "path": str(f),
                    "error": "Invalid factory file",
                })
        
        return json.dumps({
            "success": True,
            "factories": factories,
            "count": len(factories),
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        })


def load_factory(
    path: str,
    task_id: str = None,
) -> str:
    """
    Load a factory definition from a file.
    
    Args:
        path: Path to factory JSON file
        task_id: Task ID for session isolation
    
    Returns:
        JSON string with factory definition
    """
    try:
        factory_path = Path(path).expanduser()
        
        if not factory_path.exists():
            return json.dumps({
                "success": False,
                "error": f"File not found: {path}",
            })
        
        data = json.loads(factory_path.read_text())
        
        return json.dumps({
            "success": True,
            "factory": data,
        }, ensure_ascii=False)
        
    except json.JSONDecodeError as e:
        return json.dumps({
            "success": False,
            "error": f"Invalid JSON: {e}",
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        })


# Tool schemas
EXECUTE_FACTORY_SCHEMA = {
    "name": "execute_factory",
    "description": (
        "Execute a Shapez factory workflow. Factories are visual workflows "
        "consisting of connected blocks that perform tool calls, agent "
        "operations, and data transformations. Use this to run complex "
        "multi-step workflows defined as factory JSON."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "factory_json": {
                "type": "string",
                "description": "JSON string defining the factory workflow",
            },
            "inputs": {
                "type": "string",
                "description": "JSON string of input values to inject into the factory",
            },
        },
        "required": ["factory_json"],
    },
}

LIST_FACTORIES_SCHEMA = {
    "name": "list_factories",
    "description": (
        "List available Shapez factory definitions. Searches the factories "
        "directory for .json factory files."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Directory to search (default: ~/.hermes/factories)",
            },
        },
        "required": [],
    },
}

LOAD_FACTORY_SCHEMA = {
    "name": "load_factory",
    "description": (
        "Load a Shapez factory definition from a file. Returns the full "
        "factory JSON so it can be modified or executed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the factory JSON file",
            },
        },
        "required": ["path"],
    },
}

# Register tools
registry.register(
    name="execute_factory",
    toolset="shapez",
    schema=EXECUTE_FACTORY_SCHEMA,
    handler=lambda args, **kw: execute_factory(
        factory_json=args.get("factory_json", "{}"),
        inputs=args.get("inputs"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_shapez_requirements,
)

registry.register(
    name="list_factories",
    toolset="shapez",
    schema=LIST_FACTORIES_SCHEMA,
    handler=lambda args, **kw: list_factories(
        directory=args.get("directory"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_shapez_requirements,
)

registry.register(
    name="load_factory",
    toolset="shapez",
    schema=LOAD_FACTORY_SCHEMA,
    handler=lambda args, **kw: load_factory(
        path=args.get("path", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_shapez_requirements,
)
