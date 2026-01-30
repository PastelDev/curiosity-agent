"""
Tool Registry and Executor for Curiosity Agent.
Handles tool loading, schema generation, and execution.
"""

import json
import importlib.util
import subprocess
import tempfile
import os
import asyncio
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Tool:
    """Tool definition."""
    name: str
    description: str
    parameters: dict
    execute: Callable
    category: str = "custom"
    protected: bool = False


class ToolRegistry:
    """
    Registry for all available tools.
    Handles loading, schema generation, and execution.

    All tool calls require a 'tool_description' field that explains
    what the agent is trying to accomplish with this tool call.
    """

    # Global flag to require descriptions on all tool calls
    REQUIRE_DESCRIPTION = True
    DESCRIPTION_FIELD_NAME = "tool_description"

    def __init__(
        self,
        tools_dir: str = "tools",
        sandbox_root: Optional[str] = None,
        sandbox_temp_path: Optional[str] = None,
        protected_paths: Optional[list[str]] = None,
        summarizer_fn: Optional[Callable] = None
    ):
        self.sandbox_root = Path(sandbox_root).resolve() if sandbox_root else None
        self.sandbox_temp_path = Path(sandbox_temp_path).resolve() if sandbox_temp_path else None
        self.protected_paths = [Path(p).resolve() for p in (protected_paths or [])]
        self.summarizer_fn = summarizer_fn
        self.tools_dir = Path(tools_dir)
        if self.sandbox_root and not self.tools_dir.is_absolute():
            self.tools_dir = (self.sandbox_root / self.tools_dir).resolve()
        else:
            self.tools_dir = self.tools_dir.resolve()

        if self.sandbox_root and not self._is_within_sandbox(self.tools_dir):
            raise ValueError(f"tools_dir must be within sandbox root: {self.tools_dir}")
        self.tools: dict[str, Tool] = {}
        self._load_builtin_tools()
        self._load_custom_tools()
    
    def _load_builtin_tools(self):
        """Load the built-in core tools."""
        
        # File operations
        self.register(Tool(
            name="read_file",
            description="Read the contents of a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"}
                },
                "required": ["path"]
            },
            execute=self._execute_read_file,
            category="core",
            protected=True
        ))
        
        self.register(Tool(
            name="write_file",
            description="Write content to a file (creates directories if needed)",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "content": {"type": "string", "description": "Content to write"},
                    "mode": {"type": "string", "enum": ["overwrite", "append"], "default": "overwrite"}
                },
                "required": ["path", "content"]
            },
            execute=self._execute_write_file,
            category="core",
            protected=True
        ))
        
        self.register(Tool(
            name="list_directory",
            description="List contents of a directory",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to directory"},
                    "recursive": {"type": "boolean", "default": False}
                },
                "required": ["path"]
            },
            execute=self._execute_list_directory,
            category="core",
            protected=True
        ))
        
        # Code execution
        run_code_default_dir = str(self.sandbox_temp_path or Path("workspace/temp"))
        self.register(Tool(
            name="run_code",
            description="Execute code in a sandboxed environment",
            parameters={
                "type": "object",
                "properties": {
                    "language": {"type": "string", "enum": ["python", "bash", "javascript"]},
                    "code": {"type": "string", "description": "Code to execute"},
                    "timeout": {"type": "integer", "default": 30},
                    "working_dir": {"type": "string", "default": run_code_default_dir}
                },
                "required": ["language", "code"]
            },
            execute=self._execute_run_code,
            category="core",
            protected=True
        ))
        
        # Internet tools
        self.register(Tool(
            name="internet_search",
            description="Search the web for information using DuckDuckGo",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num_results": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            },
            execute=self._execute_internet_search,
            category="core",
            protected=True
        ))
        
        self.register(Tool(
            name="fetch_url",
            description="Fetch and extract text content from a URL",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "use_jina": {"type": "boolean", "default": True, "description": "Use Jina Reader for clean text"}
                },
                "required": ["url"]
            },
            execute=self._execute_fetch_url,
            category="core",
            protected=True
        ))
    
    def _load_custom_tools(self):
        """Load custom tools from the tools/custom directory."""
        custom_dir = self.tools_dir / "custom"
        if not custom_dir.exists():
            return
        
        for tool_file in custom_dir.glob("*.json"):
            try:
                with open(tool_file) as f:
                    tool_def = json.load(f)
                
                # Load the implementation
                impl_file = custom_dir / f"{tool_def['name']}.py"
                if impl_file.exists():
                    spec = importlib.util.spec_from_file_location(tool_def['name'], impl_file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    execute_fn = getattr(module, 'execute', None)
                    
                    if execute_fn:
                        self.register(Tool(
                            name=tool_def['name'],
                            description=tool_def['description'],
                            parameters=tool_def['parameters'],
                            execute=execute_fn,
                            category="custom",
                            protected=False
                        ))
            except Exception as e:
                print(f"Warning: Could not load custom tool {tool_file}: {e}")
    
    def register(self, tool: Tool):
        """Register a tool."""
        self.tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def list_tools(self, category: Optional[str] = None) -> list[str]:
        """List all tool names, optionally filtered by category."""
        if category:
            return [name for name, tool in self.tools.items() if tool.category == category]
        return list(self.tools.keys())
    
    def get_schemas(self, tool_names: Optional[list[str]] = None) -> list[dict]:
        """
        Get OpenAI-format tool schemas for API calls.

        If REQUIRE_DESCRIPTION is True, adds a required 'tool_description' field
        to all tool schemas so the agent must explain what it's doing.
        """
        schemas = []
        for name, tool in self.tools.items():
            if tool_names and name not in tool_names:
                continue

            # Clone the parameters to avoid mutating the original
            params = json.loads(json.dumps(tool.parameters))

            # Add tool_description field if required
            if self.REQUIRE_DESCRIPTION:
                if "properties" not in params:
                    params["properties"] = {}

                params["properties"][self.DESCRIPTION_FIELD_NAME] = {
                    "type": "string",
                    "description": "A brief description of what you are doing with this tool call and why"
                }

                # Make it required
                if "required" not in params:
                    params["required"] = []
                if self.DESCRIPTION_FIELD_NAME not in params["required"]:
                    params["required"].append(self.DESCRIPTION_FIELD_NAME)

            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": params
                }
            })
        return schemas

    def extract_description(self, arguments: dict) -> tuple[dict, Optional[str]]:
        """
        Extract the tool_description from arguments and return clean args.

        Returns:
            tuple of (cleaned_arguments, description)
        """
        description = arguments.pop(self.DESCRIPTION_FIELD_NAME, None)
        return arguments, description

    async def execute(self, name: str, arguments: dict) -> dict:
        """
        Execute a tool by name.

        Returns:
            dict with 'success', 'result' or 'error', and 'description' if provided
        """
        tool = self.get(name)
        if not tool:
            return {"success": False, "error": f"Unknown tool: {name}"}

        # Extract description before execution
        clean_args, description = self.extract_description(arguments.copy())

        try:
            # Handle both sync and async execute functions
            if asyncio.iscoroutinefunction(tool.execute):
                result = await tool.execute(clean_args)
            else:
                result = tool.execute(clean_args)

            response = {"success": True, "result": result}
            if description:
                response["description"] = description
            return response
        except Exception as e:
            response = {"success": False, "error": str(e)}
            if description:
                response["description"] = description
            return response
    
    def create_tool(
        self,
        name: str,
        description: str,
        parameters: dict,
        implementation: str
    ) -> dict:
        """
        Create a new custom tool.
        
        Args:
            name: Tool name (lowercase, underscores)
            description: What the tool does
            parameters: JSON Schema for parameters
            implementation: Python code with async def execute(params) function
        
        Returns:
            dict with 'success' and 'message' or 'error'
        """
        if name in self.tools:
            if self.tools[name].protected:
                return {"success": False, "error": f"Cannot overwrite protected tool: {name}"}
        
        custom_dir = self.tools_dir / "custom"
        custom_dir.mkdir(parents=True, exist_ok=True)
        
        # Save tool definition
        tool_def = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "created_at": datetime.now().isoformat()
        }
        
        with open(custom_dir / f"{name}.json", "w") as f:
            json.dump(tool_def, f, indent=2)
        
        # Save implementation
        with open(custom_dir / f"{name}.py", "w") as f:
            f.write(implementation)
        
        # Load and register the new tool
        try:
            spec = importlib.util.spec_from_file_location(name, custom_dir / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            execute_fn = getattr(module, 'execute', None)
            
            if not execute_fn:
                return {"success": False, "error": "Implementation must define 'execute' function"}
            
            self.register(Tool(
                name=name,
                description=description,
                parameters=parameters,
                execute=execute_fn,
                category="custom",
                protected=False
            ))
            
            return {"success": True, "message": f"Tool '{name}' created successfully"}
        except Exception as e:
            return {"success": False, "error": f"Failed to load tool: {e}"}
    
    def delete_tool(self, name: str) -> dict:
        """Delete a custom tool."""
        if name not in self.tools:
            return {"success": False, "error": f"Tool not found: {name}"}
        
        if self.tools[name].protected:
            return {"success": False, "error": f"Cannot delete protected tool: {name}"}
        
        # Remove files
        custom_dir = self.tools_dir / "custom"
        (custom_dir / f"{name}.json").unlink(missing_ok=True)
        (custom_dir / f"{name}.py").unlink(missing_ok=True)
        
        # Unregister
        del self.tools[name]
        
        return {"success": True, "message": f"Tool '{name}' deleted"}
    
    # ==================== Built-in Tool Implementations ====================
    
    def _execute_read_file(self, params: dict) -> str:
        path = self._resolve_path(params["path"])
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path.read_text()
    
    def _execute_write_file(self, params: dict) -> str:
        path = self._resolve_path(params["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        
        mode = params.get("mode", "overwrite")
        if mode == "append":
            with open(path, "a") as f:
                f.write(params["content"])
        else:
            path.write_text(params["content"])
        
        return f"Written to {path}"
    
    def _execute_list_directory(self, params: dict) -> str:
        path = self._resolve_path(params["path"])
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        
        recursive = params.get("recursive", False)
        
        if recursive:
            items = list(path.rglob("*"))
        else:
            items = list(path.iterdir())
        
        result = []
        for item in sorted(items):
            prefix = "📁 " if item.is_dir() else "📄 "
            rel_path = item.relative_to(path) if recursive else item.name
            result.append(f"{prefix}{rel_path}")
        
        return "\n".join(result) if result else "(empty directory)"
    
    def _execute_run_code(self, params: dict) -> str:
        language = params["language"]
        code = params["code"]
        timeout = params.get("timeout", 30)
        working_dir = params.get("working_dir")
        if working_dir:
            working_dir_path = self._resolve_path(working_dir)
        elif self.sandbox_temp_path:
            working_dir_path = self._resolve_path(str(self.sandbox_temp_path))
        else:
            working_dir_path = self._resolve_path("workspace/temp") if self.sandbox_root else Path("workspace/temp").resolve()
        
        # Ensure working directory exists
        working_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Create temp file with appropriate extension
        suffix = {"python": ".py", "bash": ".sh", "javascript": ".js"}.get(language, ".txt")
        
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            dir=working_dir_path,
            delete=False
        ) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            cmd = {
                "python": ["python", temp_path],
                "bash": ["bash", temp_path],
                "javascript": ["node", temp_path]
            }.get(language)
            
            if not cmd:
                raise ValueError(f"Unsupported language: {language}")
            
            result = subprocess.run(
                cmd,
                cwd=working_dir_path,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            output = ""
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"
            output += f"Exit code: {result.returncode}"
            
            return output
        except subprocess.TimeoutExpired:
            return f"ERROR: Execution timed out after {timeout}s"
        finally:
            os.unlink(temp_path)

    def _is_within_sandbox(self, path: Path) -> bool:
        """Check whether a path is within the sandbox root."""
        if not self.sandbox_root:
            return True
        try:
            path.resolve().relative_to(self.sandbox_root)
            return True
        except ValueError:
            return False

    def _resolve_path(self, raw_path: str) -> Path:
        """Resolve a path and enforce sandbox boundaries if configured."""
        path = Path(raw_path)
        if not path.is_absolute():
            if self.sandbox_root:
                path = self.sandbox_root / path
        resolved = path.resolve()

        # Check sandbox boundaries
        if self.sandbox_root and not self._is_within_sandbox(resolved):
            raise PermissionError(f"Access denied outside sandbox: {raw_path}")

        # Check protected paths
        for protected in self.protected_paths:
            try:
                resolved.relative_to(protected)
                raise PermissionError(f"Access denied to protected path: {raw_path}")
            except ValueError:
                pass  # Not within this protected path, continue

        return resolved
    
    async def _execute_internet_search(self, params: dict) -> str:
        """Search using DuckDuckGo and optionally summarize with sub-agent."""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return json.dumps({"error": "duckduckgo-search not installed. Run: pip install duckduckgo-search"})

        query = params["query"]
        num_results = params.get("num_results", 5)

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=num_results))

            if not results:
                return json.dumps({"error": f"No results found for: {query}"})

            # Build raw results text
            raw_text = []
            sources = []
            for i, r in enumerate(results, 1):
                raw_text.append(f"Result {i}:\nTitle: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}\n")
                sources.append({"title": r['title'], "url": r['href']})

            # If summarizer available, use sub-agent
            if self.summarizer_fn:
                summary_prompt = f"""Analyze these search results for the query: "{query}"

{chr(10).join(raw_text)}

Provide a structured summary with:
1. KEY_FINDINGS: 3-5 bullet points of main findings
2. IMPORTANT_FACTS: Specific facts, numbers, dates extracted
3. SOURCE_RELEVANCE: Rate each source's relevance (high/medium/low)
4. FOLLOW_UP_QUERIES: 2-3 suggested follow-up searches

Format as JSON with keys: key_findings, important_facts, source_relevance, follow_up_queries"""

                try:
                    summary = await self.summarizer_fn(summary_prompt)
                    return json.dumps({
                        "query": query,
                        "summary": summary,
                        "sources": sources,
                        "raw_results_count": len(results)
                    }, indent=2)
                except Exception as e:
                    # Log error but continue with raw results
                    print(f"Summarizer error: {e}")

            # Return raw results if no summarizer
            return json.dumps({
                "query": query,
                "results": [
                    {"title": r['title'], "url": r['href'], "snippet": r['body'][:200]}
                    for r in results
                ]
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Search error: {e}"})
    
    async def _execute_fetch_url(self, params: dict) -> str:
        """Fetch URL content, optionally via Jina Reader."""
        import httpx
        
        url = params["url"]
        use_jina = params.get("use_jina", True)
        
        if use_jina:
            # Jina Reader provides clean, LLM-friendly text
            fetch_url = f"https://r.jina.ai/{url}"
        else:
            fetch_url = url
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(fetch_url)
                response.raise_for_status()
                
                content = response.text
                
                # Truncate if too long
                if len(content) > 50000:
                    content = content[:50000] + "\n\n[TRUNCATED - content too long]"
                
                return content
        except Exception as e:
            return f"Fetch error: {e}"
