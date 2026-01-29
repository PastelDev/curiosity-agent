"""
Journal Manager for Curiosity Agent.
Handles persistent knowledge storage in structured and freeform formats.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass, asdict
import uuid


EntryType = Literal["idea", "empirical_result", "tool_spec", "failed_attempt", "freeform"]


@dataclass
class JournalEntry:
    """A journal entry."""
    id: str
    entry_type: EntryType
    title: str
    content: str
    tags: list[str]
    created_at: str
    metadata: dict  # Additional structured data


class JournalManager:
    """
    Manages the agent's persistent knowledge base.
    
    Two storage modes:
    - Structured: JSON files by entry type (ideas, experiments, etc.)
    - Freeform: Date-prefixed markdown files
    """
    
    def __init__(
        self,
        structured_path: str = "journal/structured",
        freeform_path: str = "journal/freeform"
    ):
        self.structured_path = Path(structured_path)
        self.freeform_path = Path(freeform_path)
        
        # Ensure directories exist
        self.structured_path.mkdir(parents=True, exist_ok=True)
        self.freeform_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize structured files
        self._init_structured_files()
    
    def _init_structured_files(self):
        """Initialize empty JSON files for each entry type."""
        types = ["ideas", "empirical_results", "tool_specs", "failed_attempts"]
        for t in types:
            path = self.structured_path / f"{t}.json"
            if not path.exists():
                with open(path, "w") as f:
                    json.dump({"entries": []}, f, indent=2)
    
    def _get_structured_file(self, entry_type: EntryType) -> Path:
        """Get the JSON file path for an entry type."""
        mapping = {
            "idea": "ideas.json",
            "empirical_result": "empirical_results.json",
            "tool_spec": "tool_specs.json",
            "failed_attempt": "failed_attempts.json"
        }
        return self.structured_path / mapping.get(entry_type, "ideas.json")
    
    def _load_structured(self, entry_type: EntryType) -> list[dict]:
        """Load entries from a structured file."""
        path = self._get_structured_file(entry_type)
        if path.exists():
            with open(path) as f:
                return json.load(f).get("entries", [])
        return []
    
    def _save_structured(self, entry_type: EntryType, entries: list[dict]):
        """Save entries to a structured file."""
        path = self._get_structured_file(entry_type)
        with open(path, "w") as f:
            json.dump({"entries": entries, "updated_at": datetime.now().isoformat()}, f, indent=2)
    
    def write(
        self,
        entry_type: EntryType,
        title: str,
        content: str,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Write a new journal entry.
        
        Args:
            entry_type: Type of entry (idea, empirical_result, tool_spec, failed_attempt, freeform)
            title: Entry title
            content: Main content
            tags: Optional tags for searching
            metadata: Additional structured data (e.g., hypothesis, results for experiments)
        
        Returns:
            Entry ID
        """
        entry_id = f"{entry_type[:4]}_{uuid.uuid4().hex[:8]}"
        tags = tags or []
        metadata = metadata or {}
        
        entry = JournalEntry(
            id=entry_id,
            entry_type=entry_type,
            title=title,
            content=content,
            tags=tags,
            created_at=datetime.now().isoformat(),
            metadata=metadata
        )
        
        if entry_type == "freeform":
            # Save as markdown file
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"{date_str}_{self._slugify(title)}.md"
            path = self.freeform_path / filename
            
            # Build markdown content
            md_content = f"# {title}\n\n"
            md_content += f"*Created: {entry.created_at}*\n\n"
            if tags:
                md_content += f"Tags: {', '.join(tags)}\n\n"
            md_content += "---\n\n"
            md_content += content
            
            if metadata:
                md_content += "\n\n---\n\n## Metadata\n\n```json\n"
                md_content += json.dumps(metadata, indent=2)
                md_content += "\n```\n"
            
            path.write_text(md_content)
        else:
            # Save to structured JSON
            entries = self._load_structured(entry_type)
            entries.append(asdict(entry))
            self._save_structured(entry_type, entries)
        
        return entry_id
    
    def read(
        self,
        query: Optional[str] = None,
        entry_type: Optional[EntryType] = None,
        tags: Optional[list[str]] = None,
        limit: int = 10
    ) -> list[dict]:
        """
        Search and retrieve journal entries.
        
        Args:
            query: Text search query (searches title and content)
            entry_type: Filter by type
            tags: Filter by tags (any match)
            limit: Maximum entries to return
        
        Returns:
            List of matching entries
        """
        results = []
        
        # Search structured files
        types_to_search = [entry_type] if entry_type and entry_type != "freeform" else [
            "idea", "empirical_result", "tool_spec", "failed_attempt"
        ]
        
        for et in types_to_search:
            entries = self._load_structured(et)
            for entry in entries:
                if self._matches(entry, query, tags):
                    results.append(entry)
        
        # Search freeform files if applicable
        if entry_type is None or entry_type == "freeform":
            for md_file in self.freeform_path.glob("*.md"):
                content = md_file.read_text()
                title = md_file.stem.split("_", 1)[-1].replace("-", " ").title()
                
                entry = {
                    "id": md_file.stem,
                    "entry_type": "freeform",
                    "title": title,
                    "content": content[:500] + "..." if len(content) > 500 else content,
                    "file_path": str(md_file),
                    "tags": [],
                    "created_at": md_file.stat().st_mtime
                }
                
                if self._matches(entry, query, tags):
                    results.append(entry)
        
        # Sort by created_at descending
        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return results[:limit]
    
    def _matches(self, entry: dict, query: Optional[str], tags: Optional[list[str]]) -> bool:
        """Check if entry matches search criteria."""
        if query:
            query_lower = query.lower()
            title_match = query_lower in entry.get("title", "").lower()
            content_match = query_lower in entry.get("content", "").lower()
            if not (title_match or content_match):
                return False
        
        if tags:
            entry_tags = entry.get("tags", [])
            if not any(t in entry_tags for t in tags):
                return False
        
        return True
    
    def _slugify(self, text: str) -> str:
        """Convert text to filename-safe slug."""
        import re
        text = text.lower()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text[:50]
    
    def get_recent(self, limit: int = 10) -> list[dict]:
        """Get most recent entries across all types."""
        return self.read(limit=limit)
    
    def get_by_id(self, entry_id: str) -> Optional[dict]:
        """Get a specific entry by ID."""
        # Determine type from ID prefix
        prefix = entry_id[:4]
        type_mapping = {
            "idea": "idea",
            "empi": "empirical_result",
            "tool": "tool_spec",
            "fail": "failed_attempt"
        }
        
        entry_type = type_mapping.get(prefix)
        if entry_type:
            entries = self._load_structured(entry_type)
            for entry in entries:
                if entry["id"] == entry_id:
                    return entry
        
        # Check freeform
        for md_file in self.freeform_path.glob("*.md"):
            if md_file.stem == entry_id:
                return {
                    "id": entry_id,
                    "entry_type": "freeform",
                    "content": md_file.read_text(),
                    "file_path": str(md_file)
                }
        
        return None
    
    def get_stats(self) -> dict:
        """Get journal statistics."""
        stats = {
            "ideas": len(self._load_structured("idea")),
            "empirical_results": len(self._load_structured("empirical_result")),
            "tool_specs": len(self._load_structured("tool_spec")),
            "failed_attempts": len(self._load_structured("failed_attempt")),
            "freeform": len(list(self.freeform_path.glob("*.md")))
        }
        stats["total"] = sum(stats.values())
        return stats
