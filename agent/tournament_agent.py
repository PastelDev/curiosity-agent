"""
Tournament Agent - Agent type for tournament containers.

Inherits from BaseAgent and adds tournament-specific functionality:
- Isolated workspace (container)
- File reveal system for sharing outputs
- Tournament-specific tools
- Access to previous round inputs (for synthesis)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from .base_agent import BaseAgent, AgentTool, AgentConfig
from .openrouter_client import OpenRouterClient


logger = logging.getLogger(__name__)


class TournamentAgent(BaseAgent):
    """
    Agent for tournament containers.

    Features:
    - Isolated container workspace
    - File read/write within workspace
    - Reveal files for synthesis with other agents
    - Complete task when done
    - Context management
    """

    def __init__(
        self,
        container_path: Path,
        tournament_id: str,
        round_number: int,
        topic: str,
        input_files: Optional[list[dict]] = None,
        is_initial_round: bool = True,
        agent_id: Optional[str] = None,
        client: Optional[OpenRouterClient] = None,
        config: Optional[AgentConfig] = None
    ):
        # Set defaults for tournament config
        if config is None:
            config = AgentConfig()
        # Tournament agents have different defaults
        if config.max_turns is None:
            config.max_turns = 50  # Reasonable limit for tournament agents

        super().__init__(
            agent_id=agent_id,
            agent_type="tournament",
            client=client,
            config=config,
            context_state_path=str(container_path / "context_state.json")
        )

        self.container_path = container_path
        self.tournament_id = tournament_id
        self.round_number = round_number
        self.topic = topic
        self.input_files = input_files or []
        self.is_initial_round = is_initial_round

        # Create container directories
        self.workspace = container_path / "workspace"
        self.revealed_path = container_path / "revealed"
        self.logs_path = container_path / "logs"

        self.workspace.mkdir(parents=True, exist_ok=True)
        self.revealed_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        # Set workspace path for code execution (from BaseAgent)
        self._workspace_path = self.workspace

        # Track revealed files
        self.revealed_files: list[dict] = []

        # Register tournament-specific tools
        self._register_tournament_tools()

        # Enable Python code execution (sandboxed to workspace)
        self._register_code_execution_tool()

    def _register_tournament_tools(self):
        """Register tools specific to tournament agents."""

        # Write file tool
        self.register_tool(AgentTool(
            name="write_file",
            description="Write content to a file in your workspace",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of the file"
                    }
                },
                "required": ["filename", "content"]
            },
            execute=self._execute_write_file,
            category="file"
        ))

        # Read file tool
        self.register_tool(AgentTool(
            name="read_file",
            description="Read a file from your workspace",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the file to read"
                    }
                },
                "required": ["filename"]
            },
            execute=self._execute_read_file,
            category="file"
        ))

        # List files tool
        self.register_tool(AgentTool(
            name="list_files",
            description="List all files in your workspace",
            parameters={
                "type": "object",
                "properties": {}
            },
            execute=self._execute_list_files,
            category="file"
        ))

        # Reveal file tool - share with other agents
        self.register_tool(AgentTool(
            name="reveal",
            description="Reveal/share a file from your workspace for synthesis with other agents. Use this to share your final outputs.",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the file to reveal"
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of what this file contributes"
                    }
                },
                "required": ["filename"]
            },
            execute=self._execute_reveal,
            category="synthesis"
        ))

    def _execute_write_file(self, params: dict) -> dict:
        """Write a file to the workspace."""
        filename = params.get("filename", "untitled.txt")
        content = params.get("content", "")
        description = params.get("description")

        # Sanitize filename (prevent path traversal)
        filename = Path(filename).name

        file_path = self.workspace / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        self.log(
            "INFO",
            f"Wrote file: {filename} ({len(content)} chars)",
            description=description
        )

        return {
            "success": True,
            "filename": filename,
            "size": len(content)
        }

    def _execute_read_file(self, params: dict) -> dict:
        """Read a file from the workspace."""
        filename = params.get("filename", "")

        # Sanitize filename
        filename = Path(filename).name

        file_path = self.workspace / filename

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {filename}"}

        try:
            content = file_path.read_text()
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _execute_list_files(self, params: dict) -> dict:
        """List files in the workspace."""
        files = []
        for path in self.workspace.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(self.workspace)
                files.append({
                    "path": str(rel_path),
                    "size": path.stat().st_size
                })

        return {"success": True, "files": files}

    def _execute_reveal(self, params: dict) -> dict:
        """Reveal a file for synthesis with other agents."""
        filename = params.get("filename", "")
        description = params.get("description")

        # Sanitize filename
        filename = Path(filename).name

        file_path = self.workspace / filename

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {filename}"}

        try:
            content = file_path.read_text()
            file_type = filename.split(".")[-1] if "." in filename else "txt"

            # Copy to revealed directory
            revealed_file_path = self.revealed_path / filename
            revealed_file_path.write_text(content)

            # Track revealed file
            revealed_entry = {
                "filename": filename,
                "content": content,
                "file_type": file_type,
                "agent_id": self.agent_id,
                "revealed_at": datetime.now().isoformat(),
                "description": description
            }
            self.revealed_files.append(revealed_entry)

            self.log("INFO", f"Revealed file: {filename}", description=description)

            return {
                "success": True,
                "revealed": filename,
                "description": description
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def build_system_prompt(self) -> str:
        """Build the system prompt for tournament agent."""
        tools_list = ", ".join(self.list_tools())

        if self.is_initial_round:
            return f"""You are an autonomous agent participating in a collaborative tournament.

## Your Task
{self.topic}

## Available Tools
{tools_list}

## Instructions
1. Analyze the topic and develop your approach
2. Create files to document your work:
   - Create a main .md file explaining your reasoning and approach
   - Create any code files or additional documentation as needed
3. You can use 'run_python' to execute Python code in your workspace
4. Use the 'reveal' tool to share files you want to contribute to the synthesis
5. When you're done, call 'complete_task' to signal completion

## Context Management
Your context will be automatically compacted when it gets too full.
You can also manually manage context with 'manage_context'.

## Guidelines
- Think carefully about the topic before starting
- Document your reasoning clearly
- Focus on quality over quantity
- Be creative but practical
- Call 'complete_task' when you're done with your work

Begin your work now.
"""
        else:
            # Synthesis round - include input files info
            files_summary = "\n".join([
                f"- {f['filename']} (from agent {f['agent_id'][:8]}): {f.get('description', 'No description')}"
                for f in self.input_files
            ])

            return f"""You are an autonomous agent in a synthesis round of a collaborative tournament.

## Original Topic
{self.topic}

## Your Task
Review the contributions from the previous round and synthesize the best ideas into improved outputs.

## Input Files from Previous Round
{files_summary}

## Available Tools
{tools_list}

## Instructions
1. Review all input files carefully
2. Identify the strongest ideas and approaches
3. Synthesize and improve upon them
4. Create new files that combine the best elements
5. Add your own insights and improvements
6. You can use 'run_python' to execute Python code in your workspace
7. Use the 'reveal' tool to share your synthesized outputs
8. When done, call 'complete_task' to signal completion

## Context Management
Your context will be automatically compacted when it gets too full.

## Guidelines
- Build on what works, improve what doesn't
- Explain your synthesis reasoning in your main .md file
- Be constructive and collaborative
- Focus on creating the best possible outcome
- Call 'complete_task' when you're done

Begin your synthesis now.
"""

    def get_initial_prompt(self) -> Optional[str]:
        """Get the initial prompt for the tournament agent."""
        if self.is_initial_round:
            return None  # System prompt is sufficient

        # For synthesis rounds, include the file contents
        if not self.input_files:
            return "No input files from previous round. Start fresh."

        files_content = "\n\n---\n\n".join([
            f"### {f['filename']}\n```{f.get('file_type', 'txt')}\n{f['content']}\n```"
            for f in self.input_files
        ])

        return f"""Here are the files from the previous round for you to synthesize:

{files_content}

Review these carefully and create improved, synthesized outputs."""

    def setup(self):
        """Setup hook - initialize container."""
        self.log("INFO", "Tournament agent initialized",
                description=f"Round {self.round_number}, Initial: {self.is_initial_round}")

    def teardown(self):
        """Teardown hook - save container state."""
        # Save revealed files index
        revealed_index = self.revealed_path / "index.json"
        revealed_index.write_text(json.dumps({
            "agent_id": self.agent_id,
            "tournament_id": self.tournament_id,
            "round_number": self.round_number,
            "revealed_files": self.revealed_files,
            "completed_at": datetime.now().isoformat()
        }, indent=2))

        # Save logs
        logs_file = self.logs_path / "agent_logs.json"
        logs_file.write_text(json.dumps(self.logs, indent=2))

        self.log("INFO", "Tournament agent teardown complete",
                description=f"Revealed {len(self.revealed_files)} files")

    def get_revealed_files(self) -> list[dict]:
        """Get all files revealed by this agent."""
        return self.revealed_files.copy()

    def get_container_files(self) -> list[dict]:
        """Get all files in the container workspace."""
        files = []
        for path in self.workspace.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(self.workspace)
                try:
                    content = path.read_text()
                except Exception:
                    content = "[Binary or unreadable]"
                files.append({
                    "path": str(rel_path),
                    "content": content,
                    "size": path.stat().st_size
                })
        return files
