"""
Sub Agent - Agent type for one-off tasks.

Inherits from BaseAgent and provides:
- Isolated workspace for task execution
- Configurable tool sets (can include web search, etc.)
- File output system
- Task-specific execution
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
import logging

from .base_agent import BaseAgent, AgentTool, AgentConfig
from .openrouter_client import OpenRouterClient


logger = logging.getLogger(__name__)


class SubAgent(BaseAgent):
    """
    Agent for one-off tasks.

    Features:
    - Isolated workspace
    - Configurable tool set
    - Optional web search capabilities
    - File output system
    - Complete task when done
    - Context management
    """

    def __init__(
        self,
        task: str,
        workspace_path: Path,
        agent_id: Optional[str] = None,
        client: Optional[OpenRouterClient] = None,
        config: Optional[AgentConfig] = None,
        enable_web_search: bool = False,
        enable_code_execution: bool = False,
        summarizer_fn: Optional[Callable[[str], str]] = None,
        additional_tools: Optional[list[AgentTool]] = None,
        system_prompt_additions: str = ""
    ):
        # Set defaults for sub-agent config
        if config is None:
            config = AgentConfig()
        # Sub-agents have different defaults
        if config.max_turns is None:
            config.max_turns = 30  # Reasonable limit for sub-agents

        super().__init__(
            agent_id=agent_id,
            agent_type="sub",
            client=client,
            config=config,
            context_state_path=str(workspace_path / "context_state.json")
        )

        self.task = task
        self.workspace_path = workspace_path
        self.enable_web_search = enable_web_search
        self.enable_code_execution = enable_code_execution
        self.summarizer_fn = summarizer_fn
        self.system_prompt_additions = system_prompt_additions

        # Create workspace directories
        self.workspace = workspace_path / "workspace"
        self.output_path = workspace_path / "output"
        self.logs_path = workspace_path / "logs"

        self.workspace.mkdir(parents=True, exist_ok=True)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        # Set workspace path for code execution (from BaseAgent)
        self._workspace_path = self.workspace

        # Track output files
        self.output_files: list[dict] = []

        # Register sub-agent tools
        self._register_sub_agent_tools()

        # Enable Python code execution if requested (uses BaseAgent's sandboxed implementation)
        if enable_code_execution:
            self._register_code_execution_tool()

        # Register additional tools if provided
        if additional_tools:
            for tool in additional_tools:
                self.register_tool(tool)

    def _register_sub_agent_tools(self):
        """Register tools for sub-agents."""

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

        # Output file tool - mark a file as output
        self.register_tool(AgentTool(
            name="output",
            description="Mark a file as output to be returned as part of your results",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the file to output"
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of this output"
                    }
                },
                "required": ["filename"]
            },
            execute=self._execute_output,
            category="output"
        ))

        # Web search tool (if enabled)
        if self.enable_web_search:
            self.register_tool(AgentTool(
                name="internet_search",
                description="Search the internet for information",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "summarize": {
                            "type": "boolean",
                            "description": "Whether to summarize results",
                            "default": True
                        }
                    },
                    "required": ["query"]
                },
                execute=self._execute_web_search,
                category="web"
            ))

        # Note: Code execution (run_python) is registered separately via BaseAgent's
        # _register_code_execution_tool() if enable_code_execution=True

    def _execute_write_file(self, params: dict) -> dict:
        """Write a file to the workspace."""
        filename = params.get("filename", "untitled.txt")
        content = params.get("content", "")

        # Sanitize filename
        filename = Path(filename).name

        file_path = self.workspace / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        self.log("INFO", f"Wrote file: {filename} ({len(content)} chars)")

        return {"success": True, "filename": filename, "size": len(content)}

    def _execute_read_file(self, params: dict) -> dict:
        """Read a file from the workspace."""
        filename = params.get("filename", "")
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

    def _execute_output(self, params: dict) -> dict:
        """Mark a file as output."""
        filename = params.get("filename", "")
        description = params.get("description")

        filename = Path(filename).name
        file_path = self.workspace / filename

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {filename}"}

        try:
            content = file_path.read_text()
            file_type = filename.split(".")[-1] if "." in filename else "txt"

            # Copy to output directory
            output_file_path = self.output_path / filename
            output_file_path.write_text(content)

            # Track output file
            output_entry = {
                "filename": filename,
                "content": content,
                "file_type": file_type,
                "agent_id": self.agent_id,
                "output_at": datetime.now().isoformat(),
                "description": description
            }
            self.output_files.append(output_entry)

            self.log("INFO", f"Output file: {filename}", description=description)

            return {"success": True, "output": filename, "description": description}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_web_search(self, params: dict) -> dict:
        """Execute web search."""
        if not self.enable_web_search:
            return {"success": False, "error": "Web search not enabled"}

        query = params.get("query", "")
        summarize = params.get("summarize", True)

        if not query:
            return {"success": False, "error": "Query is required"}

        try:
            # Use DuckDuckGo search
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            if not results:
                return {"success": True, "results": [], "message": "No results found"}

            # Format results
            formatted_results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                }
                for r in results
            ]

            # Optionally summarize
            if summarize and self.summarizer_fn:
                summary_prompt = f"Query: {query}\n\nSearch Results:\n"
                for r in formatted_results:
                    summary_prompt += f"- {r['title']}: {r['snippet']}\n"
                summary_prompt += "\nProvide a concise summary of these search results."

                summary = await self.summarizer_fn(summary_prompt)
                return {
                    "success": True,
                    "results": formatted_results,
                    "summary": summary
                }

            return {"success": True, "results": formatted_results}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def build_system_prompt(self) -> str:
        """Build the system prompt for sub-agent."""
        tools_list = ", ".join(self.list_tools())

        prompt = f"""You are an autonomous agent assigned to complete a specific task.

## Your Task
{self.task}

## Available Tools
{tools_list}

## Instructions
1. Analyze the task carefully
2. Work systematically to complete it
3. Create files to document your work and results
4. Use the 'output' tool to mark files that should be returned as results
5. When you're done, call 'complete_task' to signal completion

## Context Management
Your context will be automatically compacted when it gets too full.
You can also manually manage context with 'manage_context'.

## Guidelines
- Think step by step
- Document your reasoning
- Focus on completing the task effectively
- Call 'complete_task' when you're done

{self.system_prompt_additions}

Begin working on your task now.
"""
        return prompt

    def get_initial_prompt(self) -> Optional[str]:
        """No additional initial prompt needed."""
        return None

    def setup(self):
        """Setup hook."""
        self.log("INFO", "Sub-agent initialized",
                description=f"Task: {self.task[:100]}...")

    def teardown(self):
        """Teardown hook - save output."""
        # Save output index
        output_index = self.output_path / "index.json"
        output_index.write_text(json.dumps({
            "agent_id": self.agent_id,
            "task": self.task,
            "output_files": self.output_files,
            "completed_at": datetime.now().isoformat()
        }, indent=2))

        # Save logs
        logs_file = self.logs_path / "agent_logs.json"
        logs_file.write_text(json.dumps(self.logs, indent=2))

        self.log("INFO", "Sub-agent teardown complete",
                description=f"Output {len(self.output_files)} files")

    def get_output_files(self) -> list[dict]:
        """Get all output files from this agent."""
        return self.output_files.copy()

    def get_workspace_files(self) -> list[dict]:
        """Get all files in the workspace."""
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


class WebSearchAgent(SubAgent):
    """
    Specialized sub-agent for web search tasks.

    Pre-configured with web search enabled and summarization.
    """

    def __init__(
        self,
        task: str,
        workspace_path: Path,
        agent_id: Optional[str] = None,
        client: Optional[OpenRouterClient] = None,
        config: Optional[AgentConfig] = None,
        summarizer_fn: Optional[Callable[[str], str]] = None
    ):
        super().__init__(
            task=task,
            workspace_path=workspace_path,
            agent_id=agent_id,
            client=client,
            config=config,
            enable_web_search=True,
            enable_code_execution=False,
            summarizer_fn=summarizer_fn,
            system_prompt_additions="""
## Web Search Guidelines
- Use internet_search to find relevant information
- Synthesize information from multiple sources
- Document your sources
- Focus on recent and reliable information
"""
        )


class CodeExecutionAgent(SubAgent):
    """
    Specialized sub-agent for code execution tasks.

    Pre-configured with code execution enabled.
    """

    def __init__(
        self,
        task: str,
        workspace_path: Path,
        agent_id: Optional[str] = None,
        client: Optional[OpenRouterClient] = None,
        config: Optional[AgentConfig] = None
    ):
        super().__init__(
            task=task,
            workspace_path=workspace_path,
            agent_id=agent_id,
            client=client,
            config=config,
            enable_web_search=False,
            enable_code_execution=True,
            system_prompt_additions="""
## Code Execution Guidelines
- Write clean, well-documented code
- Test your code before marking as output
- Handle errors appropriately
- Use appropriate languages for the task
"""
        )
