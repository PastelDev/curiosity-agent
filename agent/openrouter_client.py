"""
OpenRouter API client for Curiosity Agent.
Handles chat completions with tool calling support.
"""

import httpx
import json
import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResponse:
    content: Optional[str]
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""


class OpenRouterClient:
    """Client for OpenRouter API with tool calling support."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "x-ai/grok-4.1-fast",
        base_url: str = "https://openrouter.ai/api/v1"
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        self.model = model
        self.base_url = base_url
        self.total_tokens_used = 0
        self.total_cost = 0.0
    
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: Optional[str] = None
    ) -> ChatResponse:
        """
        Send a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            model: Override the default model
        
        Returns:
            ChatResponse with content and/or tool calls
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/curiosity-agent",
                    "X-Title": "Curiosity Agent"
                },
                json=payload
            )
            
            if response.status_code != 200:
                raise Exception(f"API error {response.status_code}: {response.text}")
            
            data = response.json()
        
        # Parse response
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        
        # Track usage
        usage = data.get("usage", {})
        self.total_tokens_used += usage.get("total_tokens", 0)
        
        # Parse tool calls if present
        tool_calls = []
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"])
                ))
        
        return ChatResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            usage=usage,
            model=data.get("model", ""),
            finish_reason=choice.get("finish_reason", "")
        )
    
    async def simple_completion(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048
    ) -> str:
        """Simple completion without tools, returns just the text."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.chat(
            messages=messages,
            model=model,
            max_tokens=max_tokens
        )
        return response.content or ""


# Utility for counting tokens (approximate)
def count_tokens(text: str) -> int:
    """Approximate token count. ~4 chars per token for English."""
    return len(text) // 4


def count_messages_tokens(messages: list[dict]) -> int:
    """Count approximate tokens in a message list."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content)
        total += 4  # Message overhead
    return total
