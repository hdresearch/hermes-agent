"""
Anthropic API client wrapper that provides OpenAI-compatible interface.

This module wraps the Anthropic Python SDK to provide an interface compatible
with the OpenAI client that hermes-agent uses. This allows using Anthropic's
Claude models directly without routing through OpenRouter.

Note: Using Anthropic directly loses some features that depend on OpenRouter:
- Text-to-voice (requires separate voice model access)
- Some MoA configurations that use non-Claude models

But gains:
- Potentially lower latency (direct API)
- Full prompt caching support
- No middleman pricing

Usage:
    from tools.anthropic_client import AnthropicOpenAIWrapper
    
    client = AnthropicOpenAIWrapper(api_key="sk-ant-...")
    response = client.chat.completions.create(
        model="claude-sonnet-4-20250514",
        messages=[...],
        tools=[...],
    )
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

try:
    import anthropic
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None


def check_anthropic_requirements() -> bool:
    """Check if anthropic SDK is available."""
    return ANTHROPIC_AVAILABLE


# =============================================================================
# OpenAI-compatible response structures
# =============================================================================

@dataclass
class FunctionCall:
    """OpenAI-compatible function call."""
    name: str
    arguments: str  # JSON string


@dataclass
class ToolCall:
    """OpenAI-compatible tool call."""
    id: str
    type: str = "function"
    function: FunctionCall = None


@dataclass
class Choice:
    """OpenAI-compatible choice."""
    index: int
    message: Any
    finish_reason: str


@dataclass
class Usage:
    """OpenAI-compatible usage."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class Message:
    """OpenAI-compatible message."""
    role: str
    content: Optional[str]
    tool_calls: Optional[List[ToolCall]] = None
    reasoning: Optional[str] = None  # For extended thinking
    reasoning_content: Optional[str] = None


@dataclass
class ChatCompletion:
    """OpenAI-compatible completion response."""
    id: str
    object: str = "chat.completion"
    created: int = field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: List[Choice] = field(default_factory=list)
    usage: Optional[Usage] = None


# =============================================================================
# Completion wrapper
# =============================================================================

class ChatCompletions:
    """Wrapper for chat completions that mimics OpenAI's interface."""
    
    def __init__(self, client: "Anthropic"):
        self._client = client
    
    def create(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 8192,
        temperature: float = 1.0,
        **kwargs
    ) -> ChatCompletion:
        """
        Create a chat completion using Anthropic's API.
        
        Translates between OpenAI and Anthropic message formats.
        """
        # Extract system message
        system_content = None
        anthropic_messages = []
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            
            if role == "system":
                # Anthropic uses a separate system parameter
                if system_content is None:
                    system_content = content
                else:
                    system_content += "\n\n" + content
            elif role == "user":
                anthropic_messages.append({
                    "role": "user",
                    "content": content or ""
                })
            elif role == "assistant":
                # Handle assistant messages with potential tool calls
                assistant_content = []
                
                if content:
                    assistant_content.append({
                        "type": "text",
                        "text": content
                    })
                
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    func = tc.get("function", {})
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                    
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                        "name": func.get("name", ""),
                        "input": args
                    })
                
                if assistant_content:
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": assistant_content
                    })
                else:
                    # Empty assistant message
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": ""
                    })
            elif role == "tool":
                # Tool results need to be formatted as user messages with tool_result type
                tool_call_id = msg.get("tool_call_id", "")
                tool_content = msg.get("content", "")
                
                # Anthropic expects tool results in user messages
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": tool_content
                    }]
                })
        
        # Convert tools to Anthropic format
        anthropic_tools = None
        if tools:
            anthropic_tools = []
            for tool in tools:
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}})
                })
        
        # Map model names (strip provider prefix if present)
        if "/" in model:
            model = model.split("/")[-1]
        
        # Build request kwargs
        request_kwargs = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
        }
        
        if system_content:
            request_kwargs["system"] = system_content
        
        if anthropic_tools:
            request_kwargs["tools"] = anthropic_tools
        
        # Check for extended thinking support
        thinking_config = kwargs.get("thinking")
        if thinking_config:
            request_kwargs["thinking"] = thinking_config
        
        # Make the API call
        response = self._client.messages.create(**request_kwargs)
        
        # Convert response to OpenAI format
        return self._convert_response(response, model)
    
    def _convert_response(self, response: Any, model: str) -> ChatCompletion:
        """Convert Anthropic response to OpenAI-compatible format."""
        content_text = None
        tool_calls = []
        reasoning_content = None
        
        for block in response.content:
            if hasattr(block, 'type'):
                if block.type == "text":
                    if content_text is None:
                        content_text = block.text
                    else:
                        content_text += block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        type="function",
                        function=FunctionCall(
                            name=block.name,
                            arguments=json.dumps(block.input)
                        )
                    ))
                elif block.type == "thinking":
                    # Extended thinking support
                    reasoning_content = block.thinking
        
        # Determine finish reason
        finish_reason = "stop"
        if response.stop_reason == "tool_use":
            finish_reason = "tool_calls"
        elif response.stop_reason == "max_tokens":
            finish_reason = "length"
        elif response.stop_reason == "end_turn":
            finish_reason = "stop"
        
        message = Message(
            role="assistant",
            content=content_text,
            tool_calls=tool_calls if tool_calls else None,
            reasoning=reasoning_content,
            reasoning_content=reasoning_content,
        )
        
        choice = Choice(
            index=0,
            message=message,
            finish_reason=finish_reason
        )
        
        usage = Usage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens
        )
        
        return ChatCompletion(
            id=response.id,
            model=model,
            choices=[choice],
            usage=usage
        )


# =============================================================================
# Main client wrapper
# =============================================================================

class Chat:
    """Namespace wrapper for chat operations."""
    
    def __init__(self, client: "Anthropic"):
        self.completions = ChatCompletions(client)


class AnthropicOpenAIWrapper:
    """
    Wrapper that provides an OpenAI-compatible interface for Anthropic's API.
    
    This allows hermes-agent to use Anthropic's Claude models directly
    without routing through OpenRouter.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        **kwargs
    ):
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            )
        
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        
        self._client = Anthropic(api_key=self.api_key)
        self.chat = Chat(self._client)
    
    def __getattr__(self, name: str) -> Any:
        """Forward unknown attributes to underlying client."""
        return getattr(self._client, name)


def create_anthropic_client(api_key: Optional[str] = None) -> AnthropicOpenAIWrapper:
    """Factory function to create an Anthropic client with OpenAI-compatible interface."""
    return AnthropicOpenAIWrapper(api_key=api_key)
