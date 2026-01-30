"""
Base Agent - Core agent class that all agent types inherit from.

Provides:
- Context management (with automatic compaction)
- Tool execution framework
- Lifecycle control (with complete_task tool)
- Logging
- Agent loop execution

All agent types (MainAgent, TournamentAgent, SubAgent) inherit from this.
"""

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any
import logging

from .openrouter_client import OpenRouterClient, ChatResponse
from .context_manager import ContextManager


logger = logging.getLogger(__name__)


@dataclass
class AgentTool:
    """Definition of a tool available to an agent."""
    name: str
    description: str
    parameters: dict
    execute: Callable
    category: str = "core"
    protected: bool = False

    def to_schema(self) -> dict:
        """Convert to OpenAI-compatible tool schema."""
        # Add tool_description to parameters if not present
        params = self.parameters.copy()
        if "properties" not in params:
            params["properties"] = {}
        if "tool_description" not in params["properties"]:
            params["properties"]["tool_description"] = {
                "type": "string",
                "description": "Brief description of what you're doing with this tool call"
            }
        if "required" not in params:
            params["required"] = []
        if "tool_description" not in params["required"]:
            params["required"].append("tool_description")

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params
            }
        }


@dataclass
class AgentState:
    """Agent execution state."""
    agent_id: str
    agent_type: str
    status: str = "initialized"  # initialized, running, paused, completed, failed
    turn_count: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    completion_reason: Optional[str] = None
    completion_output: Optional[dict] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "turn_count": self.turn_count,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "completion_reason": self.completion_reason,
            "completion_output": self.completion_output,
            "error": self.error
        }


@dataclass
class AgentConfig:
    """Configuration for an agent instance."""
    model: str = "x-ai/grok-4.1-fast"
    summarizer_model: Optional[str] = None
    max_tokens: int = 128000
    compaction_threshold: float = 0.85
    temperature: float = 0.7
    max_response_tokens: int = 4096
    max_turns: Optional[int] = None  # None = unlimited
    timeout: Optional[int] = None  # None = no timeout
    preserve_recent_messages: int = 5


class BaseAgent(ABC):
    """
    Base class for all agent types.

    Provides core functionality that all agents share:
    - Context management with automatic compaction
    - Tool registration and execution
    - Lifecycle control (running, paused, completed)
    - The `complete_task` tool for agents to signal they're done
    - Agent loop execution
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_type: str = "base",
        client: Optional[OpenRouterClient] = None,
        config: Optional[AgentConfig] = None,
        context_state_path: Optional[str] = None
    ):
        self.agent_id = agent_id or f"{agent_type}_{uuid.uuid4().hex[:8]}"
        self.agent_type = agent_type
        self.config = config or AgentConfig()

        # Create client if not provided
        if client:
            self.client = client
        else:
            self.client = OpenRouterClient(model=self.config.model)

        # Initialize context manager
        self.context = ContextManager(
            state_path=context_state_path or f"config/contexts/{self.agent_id}_context.json",
            max_tokens=self.config.max_tokens,
            threshold=self.config.compaction_threshold,
            preserve_recent=self.config.preserve_recent_messages
        )

        # Initialize state
        self.state = AgentState(
            agent_id=self.agent_id,
            agent_type=self.agent_type
        )

        # Tool registry
        self._tools: dict[str, AgentTool] = {}

        # Control flags
        self._running = False
        self._paused = False
        self._completed = False
        self._completion_event = asyncio.Event()

        # Completion data
        self._completion_reason: Optional[str] = None
        self._completion_output: Optional[dict] = None

        # Logs for this agent
        self.logs: list[dict] = []

        # Register core tools
        self._register_core_tools()

    def _register_core_tools(self):
        """Register tools available to all agents."""
        # Complete task tool - allows agent to signal completion
        self.register_tool(AgentTool(
            name="complete_task",
            description="Signal that you have completed your task. Call this when your work is done. This will end your execution.",
            parameters={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why the task is complete (success, blocked, need_input, etc.)"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of what was accomplished"
                    },
                    "output": {
                        "type": "object",
                        "description": "Any structured output data to return",
                        "additionalProperties": True
                    }
                },
                "required": ["reason", "summary"]
            },
            execute=self._execute_complete_task,
            category="lifecycle",
            protected=True
        ))

        # Context management tool
        self.register_tool(AgentTool(
            name="manage_context",
            description="Manage your context: compact_now (summarize and free space), set_threshold (adjust auto-compact threshold), or get_status (check usage)",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["compact_now", "set_threshold", "get_status"]
                    },
                    "threshold": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 0.95,
                        "description": "New threshold for auto-compaction (only for set_threshold)"
                    }
                },
                "required": ["action"]
            },
            execute=self._execute_manage_context,
            category="meta",
            protected=True
        ))

    def register_tool(self, tool: AgentTool):
        """Register a tool for this agent."""
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> bool:
        """Unregister a tool. Protected tools cannot be unregistered."""
        if name in self._tools:
            if self._tools[name].protected:
                return False
            del self._tools[name]
            return True
        return False

    def get_tool_schemas(self) -> list[dict]:
        """Get OpenAI-compatible tool schemas."""
        return [tool.to_schema() for tool in self._tools.values()]

    def list_tools(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    async def execute_tool(self, name: str, arguments: dict) -> dict:
        """Execute a tool by name."""
        if name not in self._tools:
            return {"success": False, "error": f"Tool not found: {name}"}

        tool = self._tools[name]

        # Extract description from arguments
        description = arguments.pop("tool_description", "")

        try:
            # Execute tool (handle async and sync)
            if asyncio.iscoroutinefunction(tool.execute):
                result = await tool.execute(arguments)
            else:
                result = tool.execute(arguments)

            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"result": result}

            result["description"] = description
            return result

        except Exception as e:
            logger.error(f"Tool execution error: {name}: {e}")
            return {"success": False, "error": str(e), "description": description}

    async def _execute_complete_task(self, params: dict) -> dict:
        """Execute the complete_task tool - signals agent is done."""
        reason = params.get("reason", "completed")
        summary = params.get("summary", "")
        output = params.get("output", {})

        self._completion_reason = reason
        self._completion_output = {
            "reason": reason,
            "summary": summary,
            "output": output
        }
        self._completed = True
        self._completion_event.set()

        self.log("INFO", f"Agent signaled completion: {reason}",
                description=summary)

        return {
            "success": True,
            "message": "Task marked as complete. Execution will end after this turn.",
            "reason": reason
        }

    async def _execute_manage_context(self, params: dict) -> dict:
        """Execute context management actions."""
        action = params["action"]

        if action == "get_status":
            return self.context.get_status()

        elif action == "set_threshold":
            threshold = params.get("threshold")
            if threshold:
                success = self.context.set_threshold(threshold)
                return {"success": success, "new_threshold": self.context.threshold}
            return {"success": False, "error": "threshold parameter required"}

        elif action == "compact_now":
            summary = await self.context.compact(
                self.client,
                summarizer_model=self.config.summarizer_model
            )
            return {"success": True, "summary_length": len(summary)}

        return {"success": False, "error": f"Unknown action: {action}"}

    def log(self, level: str, message: str, description: Optional[str] = None, **kwargs):
        """Add a log entry for this agent."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "description": description,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            **kwargs
        }
        self.logs.append(entry)
        logger.log(
            getattr(logging, level.upper(), logging.INFO),
            f"[{self.agent_type}:{self.agent_id[:8]}] {message}" +
            (f" | {description}" if description else "")
        )
        return entry

    @abstractmethod
    def build_system_prompt(self) -> str:
        """Build the system prompt for this agent. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def get_initial_prompt(self) -> Optional[str]:
        """Get the initial user prompt. Returns None if not needed."""
        pass

    def setup(self):
        """Called before the agent starts running. Override for custom setup."""
        pass

    def teardown(self):
        """Called after the agent finishes. Override for custom cleanup."""
        pass

    async def pre_step(self):
        """Called before each step. Override for custom pre-step logic."""
        pass

    async def post_step(self, step_info: dict):
        """Called after each step. Override for custom post-step logic."""
        pass

    async def step(self) -> dict:
        """Execute one iteration of the agent loop."""
        step_info = {
            "turn": self.state.turn_count,
            "timestamp": datetime.now().isoformat(),
            "actions": [],
            "completed": False
        }

        try:
            # Pre-step hook
            await self.pre_step()

            # Check if context needs compaction
            if self.context.needs_compaction:
                self.log("INFO", f"Context at {self.context.usage_percent*100:.1f}%, compacting...")
                await self.context.compact(
                    self.client,
                    summarizer_model=self.config.summarizer_model
                )
                step_info["actions"].append({"type": "context_compacted"})

            # Get next action from LLM
            response = await self.client.chat(
                messages=self.context.get_messages_for_api(),
                tools=self.get_tool_schemas(),
                temperature=self.config.temperature,
                max_tokens=self.config.max_response_tokens,
                model=self.config.model
            )

            # Process response
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_description = tool_call.arguments.get("tool_description", "")

                    self.log(
                        "INFO",
                        f"Tool call: {tool_call.name}",
                        description=tool_description,
                        tool_name=tool_call.name,
                        tool_args=tool_call.arguments
                    )

                    # Add tool call to context
                    self.context.append_tool_call(
                        tool_call.id,
                        tool_call.name,
                        tool_call.arguments
                    )

                    # Execute tool
                    result = await self.execute_tool(tool_call.name, tool_call.arguments)

                    # Get description from result
                    result_description = result.get("description", tool_description)

                    # Clean result for context
                    result_for_context = {k: v for k, v in result.items() if k != "description"}
                    result_str = json.dumps(result_for_context, indent=2, default=str)

                    # Add result to context
                    self.context.append_tool_result(tool_call.id, result_str)

                    step_info["actions"].append({
                        "type": "tool_call",
                        "tool": tool_call.name,
                        "description": result_description,
                        "success": result.get("success", True)
                    })

                    # Check if agent signaled completion
                    if self._completed:
                        step_info["completed"] = True
                        step_info["completion_reason"] = self._completion_reason
                        break

            elif response.content:
                self.context.append_assistant(response.content)
                step_info["actions"].append({
                    "type": "response",
                    "length": len(response.content)
                })

            # Update state
            self.state.turn_count += 1
            step_info["context_usage"] = self.context.usage_percent
            step_info["success"] = True

            # Post-step hook
            await self.post_step(step_info)

        except Exception as e:
            logger.error(f"Error in agent step: {e}")
            step_info["success"] = False
            step_info["error"] = str(e)
            self.state.error = str(e)

        return step_info

    async def run(self, initial_prompt: Optional[str] = None) -> AgentState:
        """
        Run the agent until completion or limits reached.

        Args:
            initial_prompt: Optional prompt to use instead of get_initial_prompt()

        Returns:
            Final agent state
        """
        self._running = True
        self._completed = False
        self._completion_event.clear()

        self.state.status = "running"
        self.state.started_at = datetime.now().isoformat()

        self.log("INFO", "Agent starting",
                description=f"Max turns: {self.config.max_turns}, Timeout: {self.config.timeout}")

        # Setup
        self.setup()

        # Build and set system prompt
        system_prompt = self.build_system_prompt()
        self.context.set_system_prompt(system_prompt)

        # Add initial prompt if provided
        prompt = initial_prompt or self.get_initial_prompt()
        if prompt:
            self.context.append_user(prompt)

        try:
            # Create run coroutine
            async def run_loop():
                while self._running and not self._completed:
                    if self._paused:
                        await asyncio.sleep(0.5)
                        continue

                    step_info = await self.step()

                    # Check if completed
                    if step_info.get("completed"):
                        break

                    # Check turn limit
                    if self.config.max_turns and self.state.turn_count >= self.config.max_turns:
                        self.log("INFO", f"Reached max turns ({self.config.max_turns})")
                        self._completion_reason = "max_turns"
                        break

                    # Small delay between turns
                    await asyncio.sleep(0.1)

            # Run with optional timeout
            if self.config.timeout:
                try:
                    await asyncio.wait_for(run_loop(), timeout=self.config.timeout)
                except asyncio.TimeoutError:
                    self.log("WARNING", f"Agent timed out after {self.config.timeout}s")
                    self._completion_reason = "timeout"
            else:
                await run_loop()

            # Update state
            if self._completed:
                self.state.status = "completed"
                self.state.completion_reason = self._completion_reason
                self.state.completion_output = self._completion_output
            elif self._completion_reason:
                self.state.status = "completed"
                self.state.completion_reason = self._completion_reason
            else:
                self.state.status = "stopped"

        except Exception as e:
            self.state.status = "failed"
            self.state.error = str(e)
            self.log("ERROR", f"Agent failed: {e}")

        finally:
            self.state.completed_at = datetime.now().isoformat()
            self._running = False
            self.teardown()

        self.log("INFO", f"Agent finished: {self.state.status}",
                description=f"Turns: {self.state.turn_count}, Reason: {self.state.completion_reason}")

        return self.state

    def pause(self):
        """Pause the agent loop."""
        self._paused = True
        self.state.status = "paused"
        self.log("INFO", "Agent paused")

    def resume(self):
        """Resume the agent loop."""
        self._paused = False
        self.state.status = "running"
        self.log("INFO", "Agent resumed")

    def stop(self):
        """Stop the agent loop without marking as complete."""
        self._running = False
        self.log("INFO", "Agent stopped externally")

    async def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for the agent to signal completion.

        Returns True if completed, False if timed out.
        """
        try:
            await asyncio.wait_for(self._completion_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def get_status(self) -> dict:
        """Get current agent status."""
        return {
            **self.state.to_dict(),
            "context": self.context.get_status(),
            "tools_count": len(self._tools),
            "logs_count": len(self.logs)
        }

    def get_logs(self, limit: Optional[int] = None) -> list[dict]:
        """Get agent logs, optionally limited to most recent."""
        if limit:
            return self.logs[-limit:]
        return self.logs.copy()
