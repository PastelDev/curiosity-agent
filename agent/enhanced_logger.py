"""
Enhanced Logging System for Curiosity Agent.

Provides structured logging with:
- Action descriptions from the agent
- Tool execution details
- Container-specific logs
- File previews
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from collections import deque


@dataclass
class EnhancedLogEntry:
    """A structured log entry with description."""
    id: str
    timestamp: str
    level: str
    category: str  # thought, tool, system, error
    message: str
    description: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_result: Optional[Any] = None
    context_id: Optional[str] = None  # tournament_id, container_id, or "main"
    files_affected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_result": self._truncate_result(self.tool_result),
            "context_id": self.context_id,
            "files_affected": self.files_affected
        }

    def _truncate_result(self, result: Any, max_length: int = 500) -> Any:
        """Truncate large results for display."""
        if result is None:
            return None
        result_str = str(result)
        if len(result_str) > max_length:
            return result_str[:max_length] + "... [truncated]"
        return result


class EnhancedLogger:
    """
    Enhanced logging system that captures:
    - All agent thoughts and actions
    - Tool executions with full details
    - Agent-provided descriptions
    - File changes
    """

    def __init__(
        self,
        log_path: str = "logs",
        max_memory_entries: int = 1000,
        context_id: str = "main"
    ):
        self.log_path = Path(log_path)
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.max_memory_entries = max_memory_entries
        self.context_id = context_id

        # In-memory log storage (circular buffer)
        self.entries: deque[EnhancedLogEntry] = deque(maxlen=max_memory_entries)

        # Entry counter for unique IDs
        self._entry_counter = 0

        # Python logger for file output
        self._logger = logging.getLogger(f"enhanced_logger_{context_id}")

    def _generate_id(self) -> str:
        """Generate a unique log entry ID."""
        self._entry_counter += 1
        return f"log_{self.context_id}_{self._entry_counter:08d}"

    def log(
        self,
        level: str,
        category: str,
        message: str,
        description: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict] = None,
        tool_result: Optional[Any] = None,
        files_affected: Optional[list[str]] = None
    ) -> EnhancedLogEntry:
        """Create and store a log entry."""
        entry = EnhancedLogEntry(
            id=self._generate_id(),
            timestamp=datetime.now().isoformat(),
            level=level,
            category=category,
            message=message,
            description=description,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            context_id=self.context_id,
            files_affected=files_affected or []
        )

        self.entries.append(entry)

        # Also log to standard Python logger
        log_level = getattr(logging, level.upper(), logging.INFO)
        log_msg = f"[{category}] {message}"
        if description:
            log_msg += f" | {description}"
        self._logger.log(log_level, log_msg)

        # Write to JSON log file
        self._write_to_file(entry)

        return entry

    def log_tool_call(
        self,
        tool_name: str,
        tool_args: dict,
        description: Optional[str] = None
    ) -> EnhancedLogEntry:
        """Log a tool call."""
        return self.log(
            level="INFO",
            category="tool",
            message=f"Calling tool: {tool_name}",
            description=description,
            tool_name=tool_name,
            tool_args=tool_args
        )

    def log_tool_result(
        self,
        tool_name: str,
        result: Any,
        description: Optional[str] = None,
        files_affected: Optional[list[str]] = None
    ) -> EnhancedLogEntry:
        """Log a tool result."""
        success = result.get("success", True) if isinstance(result, dict) else True
        level = "INFO" if success else "WARNING"

        return self.log(
            level=level,
            category="tool",
            message=f"Tool result: {tool_name} ({'success' if success else 'failed'})",
            description=description,
            tool_name=tool_name,
            tool_result=result,
            files_affected=files_affected
        )

    def log_thought(self, thought: str, description: Optional[str] = None) -> EnhancedLogEntry:
        """Log an agent thought/reasoning."""
        return self.log(
            level="INFO",
            category="thought",
            message=thought,
            description=description
        )

    def log_system(self, message: str, description: Optional[str] = None) -> EnhancedLogEntry:
        """Log a system event."""
        return self.log(
            level="INFO",
            category="system",
            message=message,
            description=description
        )

    def log_error(self, error: str, description: Optional[str] = None) -> EnhancedLogEntry:
        """Log an error."""
        return self.log(
            level="ERROR",
            category="error",
            message=error,
            description=description
        )

    def _write_to_file(self, entry: EnhancedLogEntry):
        """Write entry to JSON log file."""
        log_file = self.log_path / f"enhanced_{self.context_id}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def get_entries(
        self,
        limit: int = 100,
        offset: int = 0,
        category: Optional[str] = None,
        level: Optional[str] = None
    ) -> list[dict]:
        """Get log entries with filtering."""
        entries = list(self.entries)

        if category:
            entries = [e for e in entries if e.category == category]
        if level:
            entries = [e for e in entries if e.level == level.upper()]

        # Most recent first
        entries.reverse()

        # Apply pagination
        entries = entries[offset:offset + limit]

        return [e.to_dict() for e in entries]

    def get_tool_history(self, limit: int = 50) -> list[dict]:
        """Get recent tool call history."""
        tool_entries = [e for e in self.entries if e.category == "tool"]
        tool_entries.reverse()
        return [e.to_dict() for e in tool_entries[:limit]]

    def clear(self):
        """Clear in-memory logs."""
        self.entries.clear()
        self._entry_counter = 0


class MainAgentLogger(EnhancedLogger):
    """
    Logger specifically for the main agent.
    Adds ability to request descriptions after actions.
    """

    def __init__(self, log_path: str = "logs"):
        super().__init__(log_path=log_path, context_id="main")
        self._pending_description_request = False
        self._last_action_entry: Optional[EnhancedLogEntry] = None

    def log_action_start(
        self,
        action_type: str,
        details: str,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict] = None
    ) -> EnhancedLogEntry:
        """Log the start of an action, preparing for description."""
        entry = self.log(
            level="INFO",
            category="action",
            message=f"{action_type}: {details}",
            tool_name=tool_name,
            tool_args=tool_args
        )
        self._last_action_entry = entry
        self._pending_description_request = True
        return entry

    def add_description_to_last_action(self, description: str):
        """Add a description to the last logged action."""
        if self._last_action_entry:
            self._last_action_entry.description = description
            self._pending_description_request = False

            # Re-write to file with description
            self._write_to_file(self._last_action_entry)

    def needs_description(self) -> bool:
        """Check if the last action needs a description."""
        return self._pending_description_request

    def get_description_prompt(self) -> Optional[str]:
        """Get a prompt for the agent to provide a description."""
        if self._last_action_entry and self._pending_description_request:
            return (
                f"Please provide a brief (1-2 sentence) description of what you just did: "
                f"{self._last_action_entry.message}"
            )
        return None


class ContainerLogger(EnhancedLogger):
    """Logger for a specific container in a tournament."""

    def __init__(self, log_path: str, container_id: str, tournament_id: str):
        super().__init__(
            log_path=log_path,
            context_id=f"{tournament_id}_{container_id}"
        )
        self.container_id = container_id
        self.tournament_id = tournament_id

    def log_file_reveal(
        self,
        filename: str,
        file_type: str,
        description: Optional[str] = None
    ) -> EnhancedLogEntry:
        """Log when a file is revealed."""
        return self.log(
            level="INFO",
            category="reveal",
            message=f"Revealed file: {filename}",
            description=description,
            files_affected=[filename]
        )


class LogManager:
    """
    Central manager for all loggers.
    Provides access to main agent logs and container logs.
    """

    def __init__(self, base_log_path: str = "logs"):
        self.base_log_path = Path(base_log_path)
        self.base_log_path.mkdir(parents=True, exist_ok=True)

        # Main agent logger
        self.main_logger = MainAgentLogger(str(self.base_log_path))

        # Container loggers indexed by container_id
        self.container_loggers: dict[str, ContainerLogger] = {}

    def get_main_logger(self) -> MainAgentLogger:
        """Get the main agent logger."""
        return self.main_logger

    def get_or_create_container_logger(
        self,
        container_id: str,
        tournament_id: str
    ) -> ContainerLogger:
        """Get or create a logger for a container."""
        key = f"{tournament_id}_{container_id}"
        if key not in self.container_loggers:
            log_path = self.base_log_path / "containers" / tournament_id
            log_path.mkdir(parents=True, exist_ok=True)
            self.container_loggers[key] = ContainerLogger(
                str(log_path),
                container_id,
                tournament_id
            )
        return self.container_loggers[key]

    def get_container_logs(
        self,
        tournament_id: str,
        container_id: str,
        limit: int = 100
    ) -> list[dict]:
        """Get logs for a specific container."""
        key = f"{tournament_id}_{container_id}"
        if key in self.container_loggers:
            return self.container_loggers[key].get_entries(limit=limit)

        # Try to load from file
        log_file = self.base_log_path / "containers" / tournament_id / f"enhanced_{key}.jsonl"
        if log_file.exists():
            entries = []
            with open(log_file) as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
            return entries[-limit:]

        return []

    def get_all_container_ids(self) -> list[str]:
        """Get all container IDs that have logs."""
        container_ids = list(self.container_loggers.keys())

        # Also scan for log files
        containers_dir = self.base_log_path / "containers"
        if containers_dir.exists():
            for tournament_dir in containers_dir.iterdir():
                if tournament_dir.is_dir():
                    for log_file in tournament_dir.glob("enhanced_*.jsonl"):
                        key = log_file.stem.replace("enhanced_", "")
                        if key not in container_ids:
                            container_ids.append(key)

        return container_ids

    def get_main_agent_files(self, sandbox_path: str = "agent_sandbox") -> list[dict]:
        """Get files from the main agent's sandbox."""
        sandbox = Path(sandbox_path)
        files = []

        if sandbox.exists():
            for path in sandbox.rglob("*"):
                if path.is_file():
                    rel_path = path.relative_to(sandbox)
                    try:
                        # Try to read as text
                        content = path.read_text()
                        is_binary = False
                    except Exception:
                        content = "[Binary file]"
                        is_binary = True

                    files.append({
                        "path": str(rel_path),
                        "full_path": str(path),
                        "content": content[:10000] if not is_binary else content,
                        "size": path.stat().st_size,
                        "is_binary": is_binary,
                        "extension": path.suffix,
                        "modified": datetime.fromtimestamp(
                            path.stat().st_mtime
                        ).isoformat()
                    })

        return sorted(files, key=lambda f: f["modified"], reverse=True)
