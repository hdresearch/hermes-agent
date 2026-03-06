"""
iMessage platform adapter using AppleScript.

Uses AppleScript to interact with Messages.app on macOS for:
- Receiving messages (via polling Messages.app)
- Sending responses back
- No app windows opened (all background automation)

Requirements:
- macOS only (AppleScript)
- Messages.app configured with iMessage account
- Automation permissions granted to terminal/python

Note: This adapter uses polling since Messages.app doesn't expose
webhooks. It checks for new messages periodically.
"""

import asyncio
import json
import logging
import os
import platform
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)


def check_imessage_requirements() -> bool:
    """Check if iMessage dependencies are available (macOS only)."""
    if platform.system() != "Darwin":
        return False
    # Check if osascript is available
    try:
        result = subprocess.run(
            ["which", "osascript"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# AppleScript templates (no app windows opened)
APPLESCRIPT_GET_RECENT_MESSAGES = '''
-- Get recent messages from Messages.app without opening windows
tell application "Messages"
    set output to ""
    set chatList to every chat
    repeat with aChat in chatList
        try
            set chatId to id of aChat
            set chatName to name of aChat
            if chatName is missing value then
                set chatName to chatId
            end if
            set msgs to messages of aChat
            set msgCount to count of msgs
            if msgCount > 0 then
                -- Get last N messages
                set startIdx to msgCount - {max_messages} + 1
                if startIdx < 1 then set startIdx to 1
                repeat with i from startIdx to msgCount
                    set aMsg to item i of msgs
                    try
                        set msgId to id of aMsg
                        set msgDate to date received of aMsg
                        set msgSender to sender of aMsg
                        set msgText to text of aMsg
                        set msgDirection to direction of aMsg
                        if msgDirection is received then
                            set dirStr to "received"
                        else
                            set dirStr to "sent"
                        end if
                        set senderHandle to ""
                        if msgSender is not missing value then
                            set senderHandle to handle of msgSender
                        end if
                        -- Format: chatId|msgId|date|direction|sender|text
                        set output to output & chatId & "|" & msgId & "|" & (msgDate as string) & "|" & dirStr & "|" & senderHandle & "|" & msgText & linefeed
                    end try
                end repeat
            end if
        end try
    end repeat
    return output
end tell
'''

APPLESCRIPT_SEND_MESSAGE = '''
-- Send a message without opening any windows
tell application "Messages"
    set targetChat to a reference to chat id "{chat_id}"
    send "{message}" to targetChat
end tell
'''

APPLESCRIPT_GET_CHAT_INFO = '''
-- Get info about a specific chat
tell application "Messages"
    set targetChat to chat id "{chat_id}"
    set chatName to name of targetChat
    set chatId to id of targetChat
    set participantList to participants of targetChat
    set participantNames to ""
    repeat with p in participantList
        set pHandle to handle of p
        set pName to name of p
        if pName is missing value then
            set pName to pHandle
        end if
        set participantNames to participantNames & pName & ","
    end repeat
    return chatId & "|" & chatName & "|" & participantNames
end tell
'''

APPLESCRIPT_GET_CHATS = '''
-- Get all available chats
tell application "Messages"
    set output to ""
    set chatList to every chat
    repeat with aChat in chatList
        try
            set chatId to id of aChat
            set chatName to name of aChat
            if chatName is missing value then
                set chatName to chatId
            end if
            set output to output & chatId & "|" & chatName & linefeed
        end try
    end repeat
    return output
end tell
'''


@dataclass
class IMessageMessage:
    """Parsed iMessage message."""
    chat_id: str
    message_id: str
    timestamp: datetime
    direction: str  # "received" or "sent"
    sender: str
    text: str


class IMessageAdapter(BasePlatformAdapter):
    """
    iMessage adapter using AppleScript.
    
    Handles:
    - Polling for new messages via AppleScript
    - Sending responses via AppleScript
    - No windows or UI elements opened
    """
    
    # iMessage doesn't have a strict limit but keep reasonable for UI
    MAX_MESSAGE_LENGTH = 10000
    
    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.LOCAL)  # Use LOCAL as platform type
        self._poll_task: Optional[asyncio.Task] = None
        self._seen_messages: set = set()  # Track seen message IDs
        self._poll_interval: float = config.extra.get("poll_interval", 2.0)
        self._max_messages_per_chat: int = config.extra.get("max_messages_per_chat", 5)
        self._last_poll_time: float = 0
        
        # Allowed senders (phone numbers or email addresses)
        allowed_str = os.getenv("IMESSAGE_ALLOWED_SENDERS", "")
        self._allowed_senders: set = set()
        if allowed_str:
            self._allowed_senders = {s.strip() for s in allowed_str.split(",") if s.strip()}
    
    @property
    def name(self) -> str:
        return "iMessage"
    
    def _run_applescript(self, script: str, timeout: float = 30.0) -> str:
        """Run AppleScript and return output."""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode != 0:
                logger.error(f"[{self.name}] AppleScript error: {result.stderr}")
                return ""
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error(f"[{self.name}] AppleScript timeout")
            return ""
        except Exception as e:
            logger.error(f"[{self.name}] AppleScript execution error: {e}")
            return ""
    
    def _parse_messages(self, output: str) -> List[IMessageMessage]:
        """Parse AppleScript output into message objects."""
        messages = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 5)
            if len(parts) < 6:
                continue
            try:
                chat_id, msg_id, date_str, direction, sender, text = parts
                # Parse date (format varies by locale)
                try:
                    timestamp = datetime.strptime(date_str.strip(), "%A, %B %d, %Y at %I:%M:%S %p")
                except ValueError:
                    try:
                        timestamp = datetime.strptime(date_str.strip(), "%m/%d/%Y, %I:%M:%S %p")
                    except ValueError:
                        timestamp = datetime.now()
                
                messages.append(IMessageMessage(
                    chat_id=chat_id.strip(),
                    message_id=msg_id.strip(),
                    timestamp=timestamp,
                    direction=direction.strip(),
                    sender=sender.strip(),
                    text=text.strip()
                ))
            except Exception as e:
                logger.debug(f"[{self.name}] Failed to parse message line: {e}")
        return messages
    
    async def connect(self) -> bool:
        """Connect to iMessage and start polling for updates."""
        if not check_imessage_requirements():
            print(f"[{self.name}] macOS with osascript required")
            return False
        
        # Test AppleScript access
        try:
            test_script = 'tell application "Messages" to return "ok"'
            result = self._run_applescript(test_script, timeout=10)
            if "ok" not in result.lower():
                print(f"[{self.name}] Failed to access Messages.app. Grant automation permissions.")
                return False
        except Exception as e:
            print(f"[{self.name}] Failed to connect: {e}")
            return False
        
        self._running = True
        
        # Start polling task
        self._poll_task = asyncio.create_task(self._poll_messages())
        
        print(f"[{self.name}] Connected and polling for messages")
        return True
    
    async def disconnect(self) -> None:
        """Stop polling and disconnect."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        print(f"[{self.name}] Disconnected")
    
    async def _poll_messages(self) -> None:
        """Poll for new messages periodically."""
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
                
                # Get recent messages via AppleScript
                script = APPLESCRIPT_GET_RECENT_MESSAGES.format(
                    max_messages=self._max_messages_per_chat
                )
                output = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._run_applescript(script)
                )
                
                messages = self._parse_messages(output)
                
                for msg in messages:
                    # Skip already seen messages
                    if msg.message_id in self._seen_messages:
                        continue
                    
                    # Skip sent messages (our own)
                    if msg.direction == "sent":
                        self._seen_messages.add(msg.message_id)
                        continue
                    
                    # Check allowed senders
                    if self._allowed_senders and msg.sender not in self._allowed_senders:
                        logger.debug(f"[{self.name}] Ignoring message from non-allowed sender: {msg.sender}")
                        self._seen_messages.add(msg.message_id)
                        continue
                    
                    self._seen_messages.add(msg.message_id)
                    
                    # Build message event
                    event = self._build_message_event(msg)
                    
                    # Handle the message
                    await self.handle_message(event)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.name}] Poll error: {e}")
                await asyncio.sleep(5)  # Back off on error
    
    def _build_message_event(self, msg: IMessageMessage) -> MessageEvent:
        """Build a MessageEvent from an iMessage."""
        source = self.build_source(
            chat_id=msg.chat_id,
            chat_name=msg.sender or msg.chat_id,
            chat_type="dm",  # iMessage is primarily 1:1
            user_id=msg.sender,
            user_name=msg.sender,
        )
        
        msg_type = MessageType.TEXT
        if msg.text.startswith("/"):
            msg_type = MessageType.COMMAND
        
        return MessageEvent(
            text=msg.text,
            message_type=msg_type,
            source=source,
            raw_message=msg,
            message_id=msg.message_id,
            timestamp=msg.timestamp,
        )
    
    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SendResult:
        """Send a message to an iMessage chat."""
        try:
            # Escape special characters for AppleScript
            escaped_content = content.replace("\\", "\\\\").replace('"', '\\"')
            
            # Split long messages
            chunks = self.truncate_message(escaped_content, self.MAX_MESSAGE_LENGTH)
            
            for chunk in chunks:
                script = APPLESCRIPT_SEND_MESSAGE.format(
                    chat_id=chat_id,
                    message=chunk
                )
                
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._run_applescript(script)
                )
                
                # Small delay between chunks
                if len(chunks) > 1:
                    await asyncio.sleep(0.5)
            
            return SendResult(
                success=True,
                message_id=None  # iMessage doesn't return message IDs on send
            )
            
        except Exception as e:
            return SendResult(success=False, error=str(e))
    
    async def send_typing(self, chat_id: str) -> None:
        """iMessage doesn't support typing indicators via AppleScript."""
        pass  # No-op
    
    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get information about an iMessage chat."""
        try:
            script = APPLESCRIPT_GET_CHAT_INFO.format(chat_id=chat_id)
            output = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._run_applescript(script)
            )
            
            parts = output.split("|")
            if len(parts) >= 3:
                return {
                    "id": parts[0],
                    "name": parts[1] or parts[0],
                    "participants": [p for p in parts[2].split(",") if p],
                    "type": "dm",
                }
        except Exception as e:
            logger.error(f"[{self.name}] Failed to get chat info: {e}")
        
        return {"name": chat_id, "type": "dm"}
    
    def format_message(self, content: str) -> str:
        """Format message for iMessage.
        
        iMessage supports basic formatting but not markdown.
        Convert common markdown to plain text.
        """
        # Remove markdown formatting
        content = re.sub(r'\*\*(.+?)\*\*', r'\1', content)  # Bold
        content = re.sub(r'\*(.+?)\*', r'\1', content)  # Italic
        content = re.sub(r'`(.+?)`', r'\1', content)  # Inline code
        content = re.sub(r'```[\w]*\n?', '', content)  # Code blocks
        
        # Convert markdown links to plain text
        content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', content)
        
        return content


def get_available_chats() -> List[Dict[str, str]]:
    """Get all available iMessage chats (utility function)."""
    if not check_imessage_requirements():
        return []
    
    try:
        result = subprocess.run(
            ["osascript", "-e", APPLESCRIPT_GET_CHATS],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return []
        
        chats = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split("|", 1)
            if len(parts) == 2:
                chats.append({
                    "id": parts[0].strip(),
                    "name": parts[1].strip()
                })
        return chats
    except Exception:
        return []
