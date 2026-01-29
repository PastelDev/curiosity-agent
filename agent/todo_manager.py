"""
Todo Manager for Curiosity Agent.
Handles hierarchical task management with subtasks.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass, asdict, field
import uuid


TodoStatus = Literal["pending", "in_progress", "done"]
TodoPriority = Literal["low", "medium", "high", "critical"]


@dataclass
class TodoItem:
    """A todo item with optional subtasks."""
    id: str
    title: str
    description: str = ""
    status: TodoStatus = "pending"
    priority: TodoPriority = "medium"
    created_at: str = ""
    updated_at: str = ""
    due_date: Optional[str] = None
    parent_id: Optional[str] = None
    subtasks: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    notes: str = ""


class TodoManager:
    """
    Manages the agent's todo list with hierarchical subtasks.
    """

    def __init__(self, todo_path: str = "agent_sandbox/todo.json"):
        self.todo_path = Path(todo_path)
        self.items: dict[str, TodoItem] = {}
        self._load()

    def _load(self):
        """Load todos from file."""
        if self.todo_path.exists():
            try:
                with open(self.todo_path) as f:
                    data = json.load(f)
                for item_data in data.get("items", []):
                    item = self._dict_to_item(item_data)
                    self.items[item.id] = item
            except Exception as e:
                print(f"Warning: Could not load todos: {e}")

    def _dict_to_item(self, data: dict) -> TodoItem:
        """Convert dict to TodoItem recursively."""
        subtasks = [self._dict_to_item(s) for s in data.get("subtasks", [])]
        return TodoItem(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            priority=data.get("priority", "medium"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            due_date=data.get("due_date"),
            parent_id=data.get("parent_id"),
            subtasks=subtasks,
            tags=data.get("tags", []),
            notes=data.get("notes", "")
        )

    def _item_to_dict(self, item: TodoItem) -> dict:
        """Convert TodoItem to dict recursively."""
        d = asdict(item)
        d["subtasks"] = [self._item_to_dict(s) for s in item.subtasks]
        return d

    def _save(self):
        """Save todos to file."""
        self.todo_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "items": [self._item_to_dict(item) for item in self.items.values() if item.parent_id is None],
            "updated_at": datetime.now().isoformat()
        }
        with open(self.todo_path, "w") as f:
            json.dump(data, f, indent=2)

    def add(
        self,
        title: str,
        description: str = "",
        priority: TodoPriority = "medium",
        due_date: Optional[str] = None,
        tags: Optional[list[str]] = None
    ) -> str:
        """Add a new todo item."""
        item_id = f"todo_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        item = TodoItem(
            id=item_id,
            title=title,
            description=description,
            status="pending",
            priority=priority,
            created_at=now,
            updated_at=now,
            due_date=due_date,
            tags=tags or []
        )

        self.items[item_id] = item
        self._save()
        return item_id

    def add_subtask(
        self,
        parent_id: str,
        title: str,
        description: str = ""
    ) -> Optional[str]:
        """Add a subtask to an existing todo."""
        if parent_id not in self.items:
            return None

        subtask_id = f"sub_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        subtask = TodoItem(
            id=subtask_id,
            title=title,
            description=description,
            status="pending",
            priority=self.items[parent_id].priority,
            created_at=now,
            updated_at=now,
            parent_id=parent_id
        )

        self.items[parent_id].subtasks.append(subtask)
        self.items[parent_id].updated_at = now
        self._save()
        return subtask_id

    def update(
        self,
        item_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[TodoStatus] = None,
        priority: Optional[TodoPriority] = None,
        notes: Optional[str] = None
    ) -> bool:
        """Update a todo item."""
        item = self._find_item(item_id)
        if not item:
            return False

        if title is not None:
            item.title = title
        if description is not None:
            item.description = description
        if status is not None:
            item.status = status
        if priority is not None:
            item.priority = priority
        if notes is not None:
            item.notes = notes

        item.updated_at = datetime.now().isoformat()
        self._save()
        return True

    def _find_item(self, item_id: str) -> Optional[TodoItem]:
        """Find an item by ID, including subtasks."""
        if item_id in self.items:
            return self.items[item_id]

        # Search in subtasks
        for item in self.items.values():
            for subtask in item.subtasks:
                if subtask.id == item_id:
                    return subtask
        return None

    def delete(self, item_id: str) -> bool:
        """Delete a todo item."""
        if item_id in self.items:
            del self.items[item_id]
            self._save()
            return True

        # Search in subtasks
        for item in self.items.values():
            for i, subtask in enumerate(item.subtasks):
                if subtask.id == item_id:
                    item.subtasks.pop(i)
                    self._save()
                    return True
        return False

    def list_all(self) -> list[dict]:
        """List all todos."""
        return [self._item_to_dict(item) for item in self.items.values() if item.parent_id is None]

    def list_by_status(self, status: TodoStatus) -> list[dict]:
        """List todos by status."""
        return [
            self._item_to_dict(item)
            for item in self.items.values()
            if item.status == status and item.parent_id is None
        ]

    def get_context_summary(self) -> str:
        """
        Generate a summary of the todo list for context injection.
        This is called at each agent step to include in the system prompt.
        """
        if not self.items:
            return "No active todo items."

        lines = ["## Current Todo List"]

        # Group by status
        in_progress = [i for i in self.items.values() if i.status == "in_progress" and not i.parent_id]
        pending = [i for i in self.items.values() if i.status == "pending" and not i.parent_id]

        if in_progress:
            lines.append("\n### In Progress")
            for item in in_progress:
                lines.append(f"- [{item.priority.upper()}] {item.title}")
                if item.description:
                    lines.append(f"  {item.description[:100]}...")
                for sub in item.subtasks:
                    status_mark = "x" if sub.status == "done" else " "
                    lines.append(f"  - [{status_mark}] {sub.title}")

        if pending:
            lines.append("\n### Pending")
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            for item in sorted(pending, key=lambda x: priority_order.get(x.priority, 2)):
                lines.append(f"- [{item.priority.upper()}] {item.title}")
                if item.subtasks:
                    done_count = sum(1 for s in item.subtasks if s.status == "done")
                    lines.append(f"  Subtasks: {done_count}/{len(item.subtasks)} done")

        return "\n".join(lines)
