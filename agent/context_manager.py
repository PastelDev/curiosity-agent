"""
Context Manager for Curiosity Agent.
Tracks context usage and handles automatic compaction.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .openrouter_client import OpenRouterClient, count_messages_tokens

logger = logging.getLogger(__name__)


@dataclass
class ContextState:
    """Serializable context state."""
    messages: list[dict] = field(default_factory=list)
    system_prompt: str = ""
    threshold: float = 0.85
    max_tokens: int = 128000
    compaction_count: int = 0
    created_at: str = ""
    last_compacted_at: Optional[str] = None


class ContextManager:
    """
    Manages the agent's context window.
    
    Features:
    - Token counting and usage tracking
    - Automatic compaction when threshold exceeded
    - Manual compaction trigger
    - Adjustable threshold
    - State persistence to JSON
    """
    
    def __init__(
        self,
        state_path: str = "config/context_state.json",
        max_tokens: int = 128000,
        threshold: float = 0.85,
        preserve_recent: int = 5
    ):
        self.state_path = Path(state_path)
        self.max_tokens = max_tokens
        self.threshold = threshold
        self.preserve_recent = preserve_recent
        
        self.messages: list[dict] = []
        self.system_prompt = ""
        self.compaction_count = 0
        self.last_compacted_at: Optional[str] = None
        
        # Load existing state if available
        self._load_state()
    
    def _load_state(self):
        """Load state from JSON file."""
        if self.state_path.exists():
            try:
                with open(self.state_path) as f:
                    data = json.load(f)
                self.messages = data.get("messages", [])
                self.system_prompt = data.get("system_prompt", "")
                self.threshold = data.get("threshold", self.threshold)
                self.compaction_count = data.get("compaction_count", 0)
                self.last_compacted_at = data.get("last_compacted_at")
            except Exception as e:
                logger.warning(f"Could not load context state: {e}")
    
    def save_state(self):
        """Save state to JSON file."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "messages": self.messages,
            "system_prompt": self.system_prompt,
            "threshold": self.threshold,
            "max_tokens": self.max_tokens,
            "compaction_count": self.compaction_count,
            "last_compacted_at": self.last_compacted_at,
            "saved_at": datetime.now().isoformat()
        }
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2)
    
    def set_system_prompt(self, prompt: str):
        """Set the system prompt."""
        self.system_prompt = prompt
        # Ensure system message is first
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = prompt
        else:
            self.messages.insert(0, {"role": "system", "content": prompt})
    
    @property
    def token_count(self) -> int:
        """Current token count of all messages."""
        return count_messages_tokens(self.messages)
    
    @property
    def usage_percent(self) -> float:
        """Current usage as percentage of max tokens."""
        return self.token_count / self.max_tokens
    
    @property
    def needs_compaction(self) -> bool:
        """Check if context exceeds threshold."""
        return self.usage_percent > self.threshold
    
    def get_status(self) -> dict:
        """Get current context status."""
        return {
            "token_count": self.token_count,
            "max_tokens": self.max_tokens,
            "usage_percent": round(self.usage_percent * 100, 1),
            "threshold_percent": round(self.threshold * 100, 1),
            "needs_compaction": self.needs_compaction,
            "message_count": len(self.messages),
            "compaction_count": self.compaction_count
        }
    
    def append_user(self, content: str):
        """Add a user message."""
        self.messages.append({"role": "user", "content": content})
        self.save_state()
    
    def append_assistant(self, content: str):
        """Add an assistant message."""
        self.messages.append({"role": "assistant", "content": content})
        self.save_state()
    
    def append_tool_call(self, tool_call_id: str, name: str, arguments: dict):
        """Add a tool call from the assistant."""
        self.messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments)
                }
            }]
        })
        self.save_state()
    
    def append_tool_result(self, tool_call_id: str, result: str):
        """Add a tool result."""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result
        })
        self.save_state()
    
    def append_system_notification(self, content: str):
        """Add a system notification (injected context)."""
        # Add as a special user message that looks like a system notification
        self.messages.append({
            "role": "user",
            "content": f"[SYSTEM NOTIFICATION]\n{content}"
        })
        self.save_state()
    
    def set_threshold(self, new_threshold: float) -> bool:
        """
        Adjust the compaction threshold.
        Returns True if successful.
        """
        if 0.5 <= new_threshold <= 0.95:
            self.threshold = new_threshold
            self.save_state()
            return True
        return False
    
    def get_messages_for_api(self) -> list[dict]:
        """Get messages formatted for API call."""
        return self.messages.copy()
    
    async def compact(
        self,
        client: OpenRouterClient,
        summarizer_model: Optional[str] = None,
        archive_path: Optional[str] = None
    ) -> str:
        """
        Compact the context using an LLM summarizer.
        
        Args:
            client: OpenRouter client to use
            summarizer_model: Model to use for summarization
            archive_path: Path to save full context before compacting
        
        Returns:
            The generated summary
        """
        # Archive full context if path provided
        if archive_path:
            archive_file = Path(archive_path) / f"context_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            archive_file.parent.mkdir(parents=True, exist_ok=True)
            with open(archive_file, "w") as f:
                json.dump({
                    "archived_at": datetime.now().isoformat(),
                    "messages": self.messages,
                    "token_count": self.token_count
                }, f, indent=2)
        
        # Build summarization prompt
        # Keep recent messages separate
        if len(self.messages) > self.preserve_recent + 1:  # +1 for system
            messages_to_summarize = self.messages[1:-self.preserve_recent]  # Skip system, keep recent
            recent_messages = self.messages[-self.preserve_recent:]
        else:
            messages_to_summarize = self.messages[1:]  # Skip system
            recent_messages = []
        
        # Create summary prompt
        context_text = "\n\n".join([
            f"[{m['role'].upper()}]: {m.get('content', '')}"
            for m in messages_to_summarize
            if m.get('content')
        ])
        
        summary_prompt = f"""You are a context summarizer for an AI agent. 
Summarize the following conversation history, preserving:

1. CURRENT GOAL: What the agent is trying to achieve
2. KEY DECISIONS: Important choices made and why
3. PENDING TASKS: What still needs to be done
4. IMPORTANT FACTS: Names, paths, configurations, etc.
5. RECENT PROGRESS: What was just accomplished
6. FAILED ATTEMPTS: What didn't work and why (to avoid repeating)

Be concise but preserve all critical information needed to continue the work.

CONVERSATION TO SUMMARIZE:
{context_text}

SUMMARY:"""
        
        summary = await client.simple_completion(
            prompt=summary_prompt,
            system="You are a precise summarizer. Extract and preserve all actionable information.",
            model=summarizer_model,
            max_tokens=2048
        )
        
        # Rebuild messages with summary
        new_messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "assistant", "content": f"[CONTEXT SUMMARY - Compaction #{self.compaction_count + 1}]\n\n{summary}"}
        ]
        
        # Add preserved recent messages
        new_messages.extend(recent_messages)
        
        self.messages = new_messages
        self.compaction_count += 1
        self.last_compacted_at = datetime.now().isoformat()
        self.save_state()
        
        return summary
    
    def reset(self):
        """Reset context to initial state (keeps system prompt)."""
        self.messages = []
        if self.system_prompt:
            self.messages.append({"role": "system", "content": self.system_prompt})
        self.save_state()
