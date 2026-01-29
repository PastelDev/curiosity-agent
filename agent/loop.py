"""
Main Agent Loop for Curiosity Agent.
The core autonomous loop that runs continuously.
"""

import asyncio
import json
import yaml
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from .openrouter_client import OpenRouterClient, ChatResponse
from .context_manager import ContextManager
from .tool_registry import ToolRegistry, Tool
from .questions_manager import QuestionsManager
from .journal_manager import JournalManager
from .todo_manager import TodoManager


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/agent.log')
    ]
)
logger = logging.getLogger(__name__)


class AgentState:
    """Persistent agent state."""
    
    def __init__(self, state_path: str = "config/agent_state.json"):
        self.state_path = Path(state_path)
        self.loop_count = 0
        self.total_cost = 0.0
        self.total_tokens = 0
        self.started_at: Optional[str] = None
        self.last_action: Optional[str] = None
        self.status = "stopped"  # stopped, running, paused, error
        self._load()
    
    def _load(self):
        if self.state_path.exists():
            with open(self.state_path) as f:
                data = json.load(f)
            self.loop_count = data.get("loop_count", 0)
            self.total_cost = data.get("total_cost", 0.0)
            self.total_tokens = data.get("total_tokens", 0)
            self.started_at = data.get("started_at")
            self.status = data.get("status", "stopped")
    
    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump({
                "loop_count": self.loop_count,
                "total_cost": self.total_cost,
                "total_tokens": self.total_tokens,
                "started_at": self.started_at,
                "last_action": self.last_action,
                "status": self.status,
                "saved_at": datetime.now().isoformat()
            }, f, indent=2)
    
    def to_dict(self) -> dict:
        return {
            "loop_count": self.loop_count,
            "total_cost": round(self.total_cost, 6),
            "total_tokens": self.total_tokens,
            "started_at": self.started_at,
            "last_action": self.last_action,
            "status": self.status
        }


class CuriosityAgent:
    """
    The main autonomous agent.
    
    Runs in a continuous loop:
    1. Check context usage, compact if needed
    2. Check for answered questions
    3. Decide next action
    4. Execute action
    5. Update state and repeat
    """
    
    def __init__(self, config_path: str = "config/settings.yaml"):
        # Load configuration
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        
        # Initialize components
        self.client = OpenRouterClient(
            model=self.config["openrouter"]["models"]["main"]
        )
        
        self.context = ContextManager(
            max_tokens=self.config["context"]["max_tokens"],
            threshold=self.config["context"]["compaction_threshold"]
        )

        # Initialize TodoManager
        sandbox_config = self.config.get("sandbox", {})
        self.todos = TodoManager(
            todo_path=sandbox_config.get("todo_path", "agent_sandbox/todo.json")
        )

        # Create summarizer function for web search sub-agent
        async def search_summarizer(prompt: str) -> str:
            summarizer_model = self.config["openrouter"]["models"].get("summarizer")
            return await self.client.simple_completion(
                prompt=prompt,
                system="You are a search result analyzer. Extract and structure key information concisely.",
                model=summarizer_model,
                max_tokens=1024
            )

        # Initialize ToolRegistry with sandbox config and summarizer
        self.tools = ToolRegistry(
            tools_dir=sandbox_config.get("tools_path", "agent_sandbox/tools"),
            sandbox_root=sandbox_config.get("root", "agent_sandbox"),
            sandbox_temp_path=sandbox_config.get("temp_path", "agent_sandbox/temp"),
            protected_paths=sandbox_config.get("protected_paths", ["agent/", "app/", "config/"]),
            summarizer_fn=search_summarizer
        )
        self.questions = QuestionsManager(questions_path=self.config["questions"]["path"])
        self.journal = JournalManager(
            structured_path=self.config["journal"]["structured_path"],
            freeform_path=self.config["journal"]["freeform_path"]
        )

        self.state = AgentState()
        
        # Load goal
        goal_path = Path("config/goal.md")
        self.goal = goal_path.read_text() if goal_path.exists() else "Explore and improve."
        
        # Build system prompt
        self._build_system_prompt()
        
        # Control flags
        self._running = False
        self._paused = False

        # Prompt queue for user messages to inject at next loop
        self._prompt_queue: deque = deque()

        # Register meta tools
        self._register_meta_tools()
    
    def _build_system_prompt(self):
        """Build the system prompt with current goal, capabilities, and todos."""
        tools_list = ", ".join(self.tools.list_tools())
        todo_context = self.todos.get_context_summary()

        system_prompt = f"""You are Curiosity, an autonomous self-improving agent.

## Your Current Goal
{self.goal}

## Your Todo List
{todo_context}

## Your Capabilities
You have access to these tools: {tools_list}

## Guidelines
1. Work autonomously toward your goal
2. Use the journal to track ideas, experiments, and learnings
3. Ask the user questions when you need input (they'll answer asynchronously)
4. Create tournaments for complex problems requiring multiple perspectives
5. Track your experiments and document what works and what doesn't
6. You can create new tools and modify your skills library
7. Be curious, explore, and continuously improve
8. Use manage_todos to track and update your task progress

## Context Management
Your context will be automatically compacted when it gets too full.
Current threshold: {self.context.threshold * 100}% (you can adjust this)

## Important
- Think step by step before acting
- Log important findings to the journal
- When uncertain, ask the user
- Learn from failed attempts
"""
        self.context.set_system_prompt(system_prompt)
    
    def _register_meta_tools(self):
        """Register the meta-tools for self-modification."""
        
        # Context management tool
        self.tools.register(Tool(
            name="manage_context",
            description="Manage context: compact_now, set_threshold, or get_status",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["compact_now", "set_threshold", "get_status"]},
                    "threshold": {"type": "number", "minimum": 0.5, "maximum": 0.95}
                },
                "required": ["action"]
            },
            execute=self._execute_manage_context,
            category="meta",
            protected=True
        ))
        
        # Tool creation
        self.tools.register(Tool(
            name="create_tool",
            description="Create a new custom tool",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "parameters_schema": {"type": "object"},
                    "implementation": {"type": "string", "description": "Python code with async def execute(params):"}
                },
                "required": ["name", "description", "parameters_schema", "implementation"]
            },
            execute=lambda p: self.tools.create_tool(
                p["name"], p["description"], p["parameters_schema"], p["implementation"]
            ),
            category="meta",
            protected=True
        ))
        
        # Tool deletion
        self.tools.register(Tool(
            name="delete_tool",
            description="Delete a custom tool",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "confirm": {"type": "boolean"}
                },
                "required": ["name", "confirm"]
            },
            execute=lambda p: self.tools.delete_tool(p["name"]) if p.get("confirm") else {"success": False, "error": "Must confirm deletion"},
            category="meta",
            protected=True
        ))
        
        # Journal tools
        self.tools.register(Tool(
            name="write_journal",
            description="Write to the knowledge base (idea, empirical_result, tool_spec, failed_attempt, freeform)",
            parameters={
                "type": "object",
                "properties": {
                    "entry_type": {"type": "string", "enum": ["idea", "empirical_result", "tool_spec", "failed_attempt", "freeform"]},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"}
                },
                "required": ["entry_type", "title", "content"]
            },
            execute=lambda p: {"entry_id": self.journal.write(
                p["entry_type"], p["title"], p["content"],
                p.get("tags"), p.get("metadata")
            )},
            category="meta",
            protected=True
        ))
        
        self.tools.register(Tool(
            name="read_journal",
            description="Search the knowledge base",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "entry_type": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "default": 10}
                }
            },
            execute=lambda p: {"entries": self.journal.read(
                p.get("query"), p.get("entry_type"),
                p.get("tags"), p.get("limit", 10)
            )},
            category="meta",
            protected=True
        ))
        
        # Question tools
        self.tools.register(Tool(
            name="ask_user",
            description="Post a question for the user (non-blocking)",
            parameters={
                "type": "object",
                "properties": {
                    "question_text": {"type": "string"},
                    "question_type": {"type": "string", "enum": ["multiple_choice", "free_text", "yes_no", "rating"]},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
                    "context": {"type": "string"}
                },
                "required": ["question_text", "question_type"]
            },
            execute=lambda p: {"question_id": self.questions.ask(
                p["question_text"], p["question_type"],
                p.get("options"), p.get("priority", "medium"),
                p.get("context", "")
            )},
            category="meta",
            protected=True
        ))
        
        self.tools.register(Tool(
            name="manage_questions",
            description="View or manage questions (list_pending, list_answered, delete, check_new_answers)",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list_pending", "list_answered", "delete", "check_new_answers"]},
                    "question_id": {"type": "string"}
                },
                "required": ["action"]
            },
            execute=self._execute_manage_questions,
            category="meta",
            protected=True
        ))

        # Todo management tool
        self.tools.register(Tool(
            name="manage_todos",
            description="Manage todo list: add, update, delete, list, add_subtask",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "update", "delete", "list", "add_subtask"]
                    },
                    "item_id": {"type": "string", "description": "Item ID for update/delete/add_subtask"},
                    "title": {"type": "string", "description": "Title for add/update"},
                    "description": {"type": "string"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "done"]},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "parent_id": {"type": "string", "description": "Parent ID for add_subtask"}
                },
                "required": ["action"]
            },
            execute=self._execute_manage_todos,
            category="meta",
            protected=True
        ))
    
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
            summarizer_model = self.config["openrouter"]["models"].get("summarizer")
            summary = await self.context.compact(
                self.client,
                summarizer_model=summarizer_model,
                archive_path=self.config["journal"]["freeform_path"]
            )
            return {"success": True, "summary_length": len(summary)}
        
        return {"success": False, "error": f"Unknown action: {action}"}
    
    def _execute_manage_questions(self, params: dict) -> dict:
        """Execute question management actions."""
        action = params["action"]
        
        if action == "list_pending":
            questions = self.questions.get_pending()
            return {"questions": [{"id": q.id, "text": q.question_text, "priority": q.priority} for q in questions]}
        
        elif action == "list_answered":
            questions = self.questions.get_answered()
            return {"questions": [{"id": q.id, "text": q.question_text, "answer": q.answer} for q in questions]}
        
        elif action == "delete":
            q_id = params.get("question_id")
            if q_id:
                success = self.questions.delete(q_id)
                return {"success": success}
            return {"success": False, "error": "question_id required"}
        
        elif action == "check_new_answers":
            new_answers = self.questions.check_new_answers()
            return {"new_answers": [{"id": q.id, "text": q.question_text, "answer": q.answer} for q in new_answers]}
        
        return {"success": False, "error": f"Unknown action: {action}"}

    def _execute_manage_todos(self, params: dict) -> dict:
        """Execute todo management actions."""
        action = params["action"]

        if action == "add":
            item_id = self.todos.add(
                title=params.get("title", "Untitled"),
                description=params.get("description", ""),
                priority=params.get("priority", "medium")
            )
            return {"success": True, "item_id": item_id}

        elif action == "update":
            success = self.todos.update(
                item_id=params.get("item_id"),
                title=params.get("title"),
                description=params.get("description"),
                status=params.get("status"),
                priority=params.get("priority")
            )
            return {"success": success}

        elif action == "delete":
            success = self.todos.delete(params.get("item_id"))
            return {"success": success}

        elif action == "list":
            items = self.todos.list_all()
            return {"items": items}

        elif action == "add_subtask":
            subtask_id = self.todos.add_subtask(
                parent_id=params.get("parent_id") or params.get("item_id"),
                title=params.get("title", "Subtask"),
                description=params.get("description", "")
            )
            return {"success": subtask_id is not None, "subtask_id": subtask_id}

        return {"success": False, "error": f"Unknown action: {action}"}

    async def step(self) -> dict:
        """Execute one iteration of the agent loop."""
        step_info = {
            "loop": self.state.loop_count,
            "timestamp": datetime.now().isoformat(),
            "actions": [],
            "injected_prompts": []
        }

        try:
            # 0. Rebuild system prompt to include updated todo list
            self._build_system_prompt()

            # 0.5. Inject queued prompts at START of loop
            injected_count = 0
            while self._prompt_queue:
                prompt_data = self._prompt_queue.popleft()
                self.context.append_system_notification(
                    f"[USER PROMPT]\nThe user has sent you the following message:\n\n{prompt_data['prompt']}"
                )
                step_info["injected_prompts"].append(prompt_data["id"])
                injected_count += 1
                logger.info(f"Injected queued prompt: {prompt_data['id']}")

            if injected_count > 0:
                step_info["actions"].append({"type": "prompts_injected", "count": injected_count})

            # 1. Check for answered questions
            new_answers = self.questions.check_new_answers()
            if new_answers:
                notification = self.questions.format_for_notification(new_answers)
                self.context.append_system_notification(notification)
                step_info["actions"].append({"type": "answers_received", "count": len(new_answers)})
            
            # 2. Check context usage
            if self.context.needs_compaction:
                logger.info(f"Context at {self.context.usage_percent*100:.1f}%, compacting...")
                await self.context.compact(
                    self.client,
                    summarizer_model=self.config["openrouter"]["models"].get("summarizer"),
                    archive_path=self.config["journal"]["freeform_path"]
                )
                step_info["actions"].append({"type": "context_compacted"})
            
            # 3. Get next action from LLM
            response = await self.client.chat(
                messages=self.context.get_messages_for_api(),
                tools=self.tools.get_schemas(),
                temperature=self.config["openrouter"]["temperature"],
                max_tokens=self.config["openrouter"]["max_tokens"]
            )
            
            # Track usage
            if response.usage:
                self.state.total_tokens += response.usage.get("total_tokens", 0)
            
            # 4. Process response
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    logger.info(f"Tool call: {tool_call.name}")
                    
                    # Add tool call to context
                    self.context.append_tool_call(
                        tool_call.id,
                        tool_call.name,
                        tool_call.arguments
                    )
                    
                    # Execute tool
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    result_str = json.dumps(result, indent=2, default=str)
                    
                    # Add result to context
                    self.context.append_tool_result(tool_call.id, result_str)
                    
                    step_info["actions"].append({
                        "type": "tool_call",
                        "tool": tool_call.name,
                        "success": result.get("success", True)
                    })
                    
                    self.state.last_action = f"tool:{tool_call.name}"
            
            elif response.content:
                self.context.append_assistant(response.content)
                step_info["actions"].append({"type": "response", "length": len(response.content)})
                self.state.last_action = "response"
            
            # 5. Update state
            self.state.loop_count += 1
            self.state.save()
            self.context.save_state()
            
            step_info["context_usage"] = self.context.usage_percent
            step_info["success"] = True
            
        except Exception as e:
            logger.error(f"Error in agent step: {e}")
            step_info["success"] = False
            step_info["error"] = str(e)
            self.state.status = "error"
            self.state.save()
        
        return step_info
    
    async def run(self, max_iterations: Optional[int] = None):
        """
        Run the agent loop.
        
        Args:
            max_iterations: Stop after this many iterations (None = run forever)
        """
        self._running = True
        self.state.status = "running"
        self.state.started_at = datetime.now().isoformat()
        self.state.save()
        
        logger.info("Agent started")
        
        iteration = 0
        while self._running:
            if self._paused:
                await asyncio.sleep(1)
                continue
            
            step_info = await self.step()
            logger.info(f"Loop {step_info['loop']}: {step_info.get('actions', [])}")
            
            iteration += 1
            if max_iterations and iteration >= max_iterations:
                logger.info(f"Reached max iterations ({max_iterations})")
                break
            
            # Small delay between iterations
            await asyncio.sleep(0.5)
        
        self.state.status = "stopped"
        self.state.save()
        logger.info("Agent stopped")
    
    def pause(self):
        """Pause the agent loop."""
        self._paused = True
        self.state.status = "paused"
        self.state.save()
    
    def resume(self):
        """Resume the agent loop."""
        self._paused = False
        self.state.status = "running"
        self.state.save()
    
    def stop(self):
        """Stop the agent loop."""
        self._running = False

    def restart(self, prompt: Optional[str] = None, keep_context: bool = False):
        """
        Restart the agent loop.

        Args:
            prompt: Optional prompt to inject at start of new loop
            keep_context: If False, resets context to initial state
        """
        # Stop current loop
        self._running = False
        self._paused = False

        # Reset loop counter
        self.state.loop_count = 0

        if not keep_context:
            # Reset context but rebuild system prompt
            self.context.reset()
            self._build_system_prompt()

        # If there's a restart prompt, inject it
        if prompt:
            self.context.append_system_notification(
                f"[USER RESTART MESSAGE]\nThe user has restarted the agent with the following message:\n\n{prompt}"
            )

        self.state.status = "stopped"
        self.state.save()
        logger.info(f"Agent restart initiated with prompt: {prompt[:50] if prompt else 'None'}...")

    def queue_prompt(self, prompt: str, priority: str = "normal") -> str:
        """
        Queue a prompt to be injected at the start of the next loop iteration.

        Args:
            prompt: The prompt text
            priority: "high" (inject first) or "normal"

        Returns:
            prompt_id for tracking
        """
        prompt_id = f"prompt_{uuid.uuid4().hex[:8]}"
        prompt_data = {
            "id": prompt_id,
            "prompt": prompt,
            "priority": priority,
            "queued_at": datetime.now().isoformat()
        }

        if priority == "high":
            self._prompt_queue.appendleft(prompt_data)
        else:
            self._prompt_queue.append(prompt_data)

        logger.info(f"Prompt queued: {prompt_id}")
        return prompt_id

    def get_queued_prompts(self) -> list[dict]:
        """Get list of queued prompts."""
        return list(self._prompt_queue)

    def remove_queued_prompt(self, prompt_id: str) -> bool:
        """Remove a specific prompt from queue."""
        for i, p in enumerate(self._prompt_queue):
            if p["id"] == prompt_id:
                del self._prompt_queue[i]
                return True
        return False

    def clear_prompt_queue(self):
        """Clear all queued prompts."""
        self._prompt_queue.clear()

    def get_status(self) -> dict:
        """Get current agent status."""
        return {
            **self.state.to_dict(),
            "context": self.context.get_status(),
            "journal": self.journal.get_stats(),
            "pending_questions": len(self.questions.get_pending()),
            "tools_count": len(self.tools.list_tools())
        }


# For running directly
async def main():
    agent = CuriosityAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
