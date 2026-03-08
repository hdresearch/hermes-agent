"""iMessage tool for reading and sending messages on macOS.

Uses AppleScript and the Messages SQLite database for read operations.
Send operations use AppleScript to send messages via Messages.app.

Requires:
- macOS with Messages.app configured
- Full Disk Access permission for reading chat.db
"""

import json
import logging
import os
import subprocess
from typing import Optional

from tools.registry import registry

logger = logging.getLogger(__name__)


def check_imessage_requirements() -> bool:
    """Check if running on macOS."""
    import platform
    return platform.system() == "Darwin"


def _run_osascript(script: str) -> dict:
    """Run an AppleScript and return the result."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "output": result.stdout.strip(),
            "error": result.stderr.strip() if result.returncode != 0 else None,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"output": "", "error": "Command timed out", "returncode": 124}
    except Exception as e:
        return {"output": "", "error": str(e), "returncode": 1}


def _run_sqlite_query(query: str) -> dict:
    """Run a query against the Messages database."""
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    
    if not os.path.exists(db_path):
        return {"error": "Messages database not found. Is Messages.app configured?"}
    
    try:
        result = subprocess.run(
            ["sqlite3", "-json", db_path, query],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            # Try without -json flag for older sqlite versions
            result = subprocess.run(
                ["sqlite3", "-header", "-separator", "|", db_path, query],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                return {"error": result.stderr.strip()}
            
            # Parse pipe-separated output
            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return {"rows": [], "columns": []}
            
            columns = lines[0].split("|")
            rows = []
            for line in lines[1:]:
                values = line.split("|")
                rows.append(dict(zip(columns, values)))
            
            return {"rows": rows, "columns": columns}
        
        # Parse JSON output
        import json as json_module
        try:
            rows = json_module.loads(result.stdout) if result.stdout.strip() else []
            return {"rows": rows}
        except:
            return {"output": result.stdout.strip()}
            
    except subprocess.TimeoutExpired:
        return {"error": "Query timed out"}
    except Exception as e:
        return {"error": str(e)}


def imessage_read(action: str, contact: str = None, limit: int = 10, search: str = None, task_id: str = None) -> str:
    """
    Read iMessage data (READ-ONLY operations).
    
    Actions:
    - list_chats: List recent conversations
    - read_messages: Read messages from a specific contact (requires contact)
    - search_messages: Search messages by text (requires search)
    """
    try:
        if action == "list_chats":
            # Get recent chats from the database
            query = """
                SELECT 
                    chat.chat_identifier,
                    chat.display_name,
                    MAX(message.date) as last_message_date,
                    COUNT(message.rowid) as message_count
                FROM chat
                LEFT JOIN chat_message_join ON chat.rowid = chat_message_join.chat_id
                LEFT JOIN message ON chat_message_join.message_id = message.rowid
                GROUP BY chat.rowid
                ORDER BY last_message_date DESC
                LIMIT {limit};
            """.format(limit=limit)
            
            result = _run_sqlite_query(query)
            
            if "error" in result:
                return json.dumps({"error": result["error"]})
            
            return json.dumps({
                "success": True,
                "action": "list_chats",
                "chats": result.get("rows", [])
            })
            
        elif action == "read_messages":
            if not contact:
                return json.dumps({"error": "contact parameter required for read_messages"})
            
            # Escape contact for SQL
            safe_contact = contact.replace("'", "''")
            
            query = f"""
                SELECT 
                    message.text,
                    message.is_from_me,
                    datetime(message.date/1000000000 + 978307200, 'unixepoch', 'localtime') as timestamp,
                    handle.id as sender
                FROM message
                JOIN chat_message_join ON message.rowid = chat_message_join.message_id
                JOIN chat ON chat_message_join.chat_id = chat.rowid
                LEFT JOIN handle ON message.handle_id = handle.rowid
                WHERE chat.chat_identifier LIKE '%{safe_contact}%'
                   OR chat.display_name LIKE '%{safe_contact}%'
                ORDER BY message.date DESC
                LIMIT {limit};
            """
            
            result = _run_sqlite_query(query)
            
            if "error" in result:
                return json.dumps({"error": result["error"]})
            
            return json.dumps({
                "success": True,
                "action": "read_messages",
                "contact": contact,
                "messages": result.get("rows", [])
            })
            
        elif action == "search_messages":
            if not search:
                return json.dumps({"error": "search parameter required for search_messages"})
            
            safe_search = search.replace("'", "''")
            
            query = f"""
                SELECT 
                    message.text,
                    message.is_from_me,
                    datetime(message.date/1000000000 + 978307200, 'unixepoch', 'localtime') as timestamp,
                    chat.chat_identifier,
                    handle.id as sender
                FROM message
                JOIN chat_message_join ON message.rowid = chat_message_join.message_id
                JOIN chat ON chat_message_join.chat_id = chat.rowid
                LEFT JOIN handle ON message.handle_id = handle.rowid
                WHERE message.text LIKE '%{safe_search}%'
                ORDER BY message.date DESC
                LIMIT {limit};
            """
            
            result = _run_sqlite_query(query)
            
            if "error" in result:
                return json.dumps({"error": result["error"]})
            
            return json.dumps({
                "success": True,
                "action": "search_messages",
                "query": search,
                "messages": result.get("rows", [])
            })
            
        else:
            return json.dumps({"error": f"Unknown action: {action}. Use: list_chats, read_messages, search_messages"})
            
    except Exception as e:
        logger.exception(f"iMessage read error: {e}")
        return json.dumps({"error": str(e)})


def imessage_send(recipient: str, message: str, task_id: str = None) -> str:
    """
    Send an iMessage (WRITE operation).
    
    Uses AppleScript to send a message via Messages.app.
    The recipient can be a phone number or email address.
    
    NOTE: This is a WRITE operation and should be used with caution.
    """
    try:
        # Escape for AppleScript
        safe_recipient = recipient.replace('"', '\\"')
        safe_message = message.replace('"', '\\"').replace('\n', '\\n')
        
        script = f'''
            tell application "Messages"
                set targetService to 1st account whose service type = iMessage
                set targetBuddy to participant "{safe_recipient}" of targetService
                send "{safe_message}" to targetBuddy
            end tell
        '''
        
        result = _run_osascript(script)
        
        if result.get("error"):
            return json.dumps({
                "success": False,
                "error": result["error"]
            })
        
        return json.dumps({
            "success": True,
            "action": "send",
            "recipient": recipient,
            "message": message,
            "status": "Message sent"
        })
        
    except Exception as e:
        logger.exception(f"iMessage send error: {e}")
        return json.dumps({"error": str(e)})


# Register READ tool
IMESSAGE_READ_SCHEMA = {
    "name": "imessage_read",
    "description": """Read iMessage data on macOS (READ-ONLY).

Actions:
- list_chats: List recent conversations
- read_messages: Read messages from a contact (requires 'contact' parameter)
- search_messages: Search messages by text (requires 'search' parameter)

Examples:
- {"action": "list_chats", "limit": 10}
- {"action": "read_messages", "contact": "+1234567890", "limit": 20}
- {"action": "search_messages", "search": "meeting tomorrow"}""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_chats", "read_messages", "search_messages"],
                "description": "The read action to perform"
            },
            "contact": {
                "type": "string",
                "description": "Phone number or email for read_messages action"
            },
            "search": {
                "type": "string",
                "description": "Search query for search_messages action"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 10)",
                "default": 10
            }
        },
        "required": ["action"]
    }
}

# Register SEND tool (write operation)
IMESSAGE_SEND_SCHEMA = {
    "name": "imessage_send",
    "description": """Send an iMessage on macOS (WRITE operation).

⚠️ This sends a real message - use with caution!

Parameters:
- recipient: Phone number or email address
- message: Text message to send

Example: {"recipient": "+1234567890", "message": "Hello!"}""",
    "parameters": {
        "type": "object",
        "properties": {
            "recipient": {
                "type": "string",
                "description": "Phone number or email address to send to"
            },
            "message": {
                "type": "string",
                "description": "Message text to send"
            }
        },
        "required": ["recipient", "message"]
    }
}

registry.register(
    name="imessage_read",
    toolset="imessage",
    schema=IMESSAGE_READ_SCHEMA,
    handler=lambda args, **kw: imessage_read(
        action=args.get("action", ""),
        contact=args.get("contact"),
        limit=args.get("limit", 10),
        search=args.get("search"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_imessage_requirements,
)

registry.register(
    name="imessage_send",
    toolset="imessage_write",  # Separate toolset for write operations
    schema=IMESSAGE_SEND_SCHEMA,
    handler=lambda args, **kw: imessage_send(
        recipient=args.get("recipient", ""),
        message=args.get("message", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_imessage_requirements,
)
