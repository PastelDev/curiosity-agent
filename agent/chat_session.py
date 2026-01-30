"""
Independent Chat Session Manager for Curiosity Agent.
Allows users to chat with the model using a snapshot of agent context.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str
    timestamp: str


@dataclass
class ChatSession:
    id: str
    created_at: str
    title: str
    messages: list = field(default_factory=list)
    context_snapshot: list = field(default_factory=list)


class ChatSessionManager:
    """
    Manages independent chat sessions that start with agent context snapshots.
    """

    def __init__(self, sessions_path: str = "config/chat_sessions.json"):
        self.sessions_path = Path(sessions_path)
        self.sessions: dict[str, ChatSession] = {}
        self._load()

    def _load(self):
        """Load sessions from file."""
        if self.sessions_path.exists():
            try:
                with open(self.sessions_path) as f:
                    data = json.load(f)
                for session_data in data.get("sessions", []):
                    session = ChatSession(
                        id=session_data["id"],
                        created_at=session_data["created_at"],
                        title=session_data["title"],
                        messages=[
                            ChatMessage(**msg) if isinstance(msg, dict) else msg
                            for msg in session_data.get("messages", [])
                        ],
                        context_snapshot=session_data.get("context_snapshot", [])
                    )
                    self.sessions[session.id] = session
            except Exception as e:
                logger.warning(f"Failed to load chat sessions: {e}")
                self.sessions = {}

    def _save(self):
        """Save sessions to file."""
        self.sessions_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "sessions": [
                {
                    "id": s.id,
                    "created_at": s.created_at,
                    "title": s.title,
                    "messages": [
                        asdict(m) if isinstance(m, ChatMessage) else m
                        for m in s.messages
                    ],
                    "context_snapshot": s.context_snapshot
                }
                for s in self.sessions.values()
            ]
        }
        with open(self.sessions_path, "w") as f:
            json.dump(data, f, indent=2)

    def create_session(self, context_snapshot: list, title: str = "") -> str:
        """
        Create a new chat session with a snapshot of the agent's context.
        Returns session_id.
        """
        session_id = f"chat_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        session = ChatSession(
            id=session_id,
            created_at=now,
            title=title or f"Chat {now[:10]}",
            context_snapshot=[msg.copy() for msg in context_snapshot],  # Deep copy
            messages=[]
        )

        self.sessions[session_id] = session
        self._save()
        return session_id

    async def send_message(
        self,
        session_id: str,
        user_message: str,
        client: OpenRouterClient,
        model: str,
        temperature: float = 0.7
    ) -> Optional[str]:
        """
        Send a message in a chat session, get response.
        Completely independent from agent - uses only session's own messages.
        """
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]
        now = datetime.now().isoformat()

        # Add user message
        session.messages.append(ChatMessage(role="user", content=user_message, timestamp=now))

        # Build messages for API: context snapshot + session messages
        api_messages = [msg.copy() for msg in session.context_snapshot]
        for msg in session.messages:
            if isinstance(msg, ChatMessage):
                api_messages.append({"role": msg.role, "content": msg.content})
            else:
                api_messages.append({"role": msg["role"], "content": msg["content"]})

        # Get response from model
        response = await client.chat(
            messages=api_messages,
            model=model,
            temperature=temperature
        )

        assistant_content = response.content or ""

        # Add assistant response
        session.messages.append(ChatMessage(
            role="assistant",
            content=assistant_content,
            timestamp=datetime.now().isoformat()
        ))

        self._save()
        return assistant_content

    def list_sessions(self) -> list[dict]:
        """List all sessions."""
        return [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at,
                "message_count": len(s.messages)
            }
            for s in sorted(self.sessions.values(), key=lambda x: x.created_at, reverse=True)
        ]

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session details."""
        if session_id not in self.sessions:
            return None
        s = self.sessions[session_id]
        return {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at,
            "messages": [
                asdict(m) if isinstance(m, ChatMessage) else m
                for m in s.messages
            ]
        }

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self._save()
            return True
        return False
