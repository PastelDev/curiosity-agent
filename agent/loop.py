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
from .tournament import TournamentEngine, Tournament, TournamentStatus
from .enhanced_logger import LogManager, MainAgentLogger


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

        # Initialize enhanced logging
        self.log_manager = LogManager(base_log_path="logs")
        self.enhanced_logger = self.log_manager.get_main_logger()

        # Initialize tournament engine
        tournament_config = self.config.get("tournament", {})
        self.tournament_engine = TournamentEngine(
            client=self.client,
            base_path="tournaments",
            model=self.config["openrouter"]["models"].get("tournament",
                   self.config["openrouter"]["models"]["main"]),
            max_parallel=tournament_config.get("max_parallel_agents", 8),
            timeout_per_agent=tournament_config.get("timeout_per_agent_seconds", 300)
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

        # Tournament creation tool
        self.tools.register(Tool(
            name="create_tournament",
            description="Create a multi-agent tournament for collaborative problem solving. Agents work in parallel, then synthesize their outputs in rounds.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic/task for agents to work on"},
                    "stages": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Number of agents per round, e.g., [4, 3, 2] means 4 agents in round 1, 3 in round 2, 2 in final"
                    },
                    "debate_rounds": {"type": "integer", "default": 2, "description": "Number of debate rounds per stage"},
                    "auto_start": {"type": "boolean", "default": True, "description": "Whether to start the tournament immediately"}
                },
                "required": ["topic"]
            },
            execute=self._execute_create_tournament,
            category="meta",
            protected=True
        ))

        # Tournament management tool
        self.tools.register(Tool(
            name="manage_tournament",
            description="Manage tournaments: start, get_status, list_all, get_results",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "get_status", "list_all", "get_results", "get_container_logs"]
                    },
                    "tournament_id": {"type": "string", "description": "Tournament ID for specific operations"},
                    "container_id": {"type": "string", "description": "Container ID for get_container_logs"}
                },
                "required": ["action"]
            },
            execute=self._execute_manage_tournament,
            category="meta",
            protected=True
        ))

        # Subagent calling tool
        self.tools.register(Tool(
            name="call_subagent",
            description="Call a single subagent to perform a task. The subagent runs in an isolated container and returns its output files.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task for the subagent to perform"},
                    "model": {"type": "string", "description": "Optional model to use (defaults to tournament model)"},
                    "timeout": {"type": "integer", "default": 300, "description": "Timeout in seconds"}
                },
                "required": ["task"]
            },
            execute=self._execute_call_subagent,
            category="meta",
            protected=True
        ))

        # Action description tool
        self.tools.register(Tool(
            name="describe_action",
            description="Provide a brief description of the action you just performed. Use this after completing tasks to help with logging.",
            parameters={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "A brief (1-2 sentence) description of what you just did"}
                },
                "required": ["description"]
            },
            execute=self._execute_describe_action,
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

    async def _execute_create_tournament(self, params: dict) -> dict:
        """Create and optionally start a tournament."""
        topic = params.get("topic", "")
        stages = params.get("stages")
        debate_rounds = params.get("debate_rounds", 2)
        auto_start = params.get("auto_start", True)

        if not topic:
            return {"success": False, "error": "Topic is required"}

        # Use default stages from config if not provided
        if not stages:
            stages = self.config.get("tournament", {}).get("default_stages", [4, 3, 2])

        tournament = self.tournament_engine.create_tournament(
            topic=topic,
            stages=stages,
            debate_rounds=debate_rounds
        )

        self.enhanced_logger.log_system(
            f"Created tournament: {tournament.id}",
            description=f"Topic: {topic}, Stages: {stages}"
        )

        result = {
            "success": True,
            "tournament_id": tournament.id,
            "topic": topic,
            "stages": stages,
            "status": tournament.status.value
        }

        if auto_start:
            # Start tournament in background
            asyncio.create_task(self._run_tournament_background(tournament.id))
            result["message"] = "Tournament created and started"
        else:
            result["message"] = "Tournament created (use manage_tournament to start)"

        return result

    async def _run_tournament_background(self, tournament_id: str):
        """Run a tournament in the background."""
        try:
            tournament = await self.tournament_engine.run_tournament(tournament_id)
            self.enhanced_logger.log_system(
                f"Tournament completed: {tournament_id}",
                description=f"Status: {tournament.status.value}, Files: {len(tournament.final_files)}"
            )
        except Exception as e:
            self.enhanced_logger.log_error(
                f"Tournament failed: {tournament_id}",
                description=str(e)
            )

    async def _execute_manage_tournament(self, params: dict) -> dict:
        """Manage tournaments."""
        action = params.get("action")
        tournament_id = params.get("tournament_id")

        if action == "list_all":
            tournaments = self.tournament_engine.list_tournaments()
            return {
                "success": True,
                "tournaments": tournaments,
                "count": len(tournaments)
            }

        elif action == "get_status":
            if not tournament_id:
                return {"success": False, "error": "tournament_id required"}
            tournament = self.tournament_engine.get_tournament(tournament_id)
            if not tournament:
                return {"success": False, "error": "Tournament not found"}
            return {
                "success": True,
                "tournament": tournament.to_dict()
            }

        elif action == "start":
            if not tournament_id:
                return {"success": False, "error": "tournament_id required"}
            tournament = self.tournament_engine.get_tournament(tournament_id)
            if not tournament:
                return {"success": False, "error": "Tournament not found"}
            if tournament.status != TournamentStatus.PENDING:
                return {"success": False, "error": f"Tournament already {tournament.status.value}"}

            asyncio.create_task(self._run_tournament_background(tournament_id))
            return {"success": True, "message": "Tournament started"}

        elif action == "get_results":
            if not tournament_id:
                return {"success": False, "error": "tournament_id required"}
            tournament = self.tournament_engine.get_tournament(tournament_id)
            if not tournament:
                return {"success": False, "error": "Tournament not found"}

            return {
                "success": True,
                "status": tournament.status.value,
                "final_files": [
                    {
                        "filename": f.filename,
                        "content": f.content[:2000],  # Truncate for response
                        "file_type": f.file_type,
                        "description": f.description
                    }
                    for f in tournament.final_files
                ]
            }

        elif action == "get_container_logs":
            if not tournament_id:
                return {"success": False, "error": "tournament_id required"}
            container_id = params.get("container_id")
            if not container_id:
                return {"success": False, "error": "container_id required"}

            logs = self.tournament_engine.get_container_logs(tournament_id, container_id)
            return {
                "success": True,
                "logs": logs
            }

        return {"success": False, "error": f"Unknown action: {action}"}

    async def _execute_call_subagent(self, params: dict) -> dict:
        """Call a subagent to perform a task."""
        task = params.get("task", "")
        model = params.get("model")
        timeout = params.get("timeout", 300)

        if not task:
            return {"success": False, "error": "Task is required"}

        self.enhanced_logger.log_system(
            f"Calling subagent",
            description=f"Task: {task[:100]}..."
        )

        result = await self.tournament_engine.call_subagent(
            task=task,
            model=model,
            timeout=timeout
        )

        self.enhanced_logger.log_system(
            f"Subagent completed: {result.get('container_id', 'unknown')}",
            description=f"Success: {result.get('success')}, Files: {len(result.get('revealed_files', []))}"
        )

        return result

    def _execute_describe_action(self, params: dict) -> dict:
        """Add a description to the last action."""
        description = params.get("description", "")

        if not description:
            return {"success": False, "error": "Description is required"}

        self.enhanced_logger.add_description_to_last_action(description)

        return {"success": True, "message": "Description added to last action"}

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
                    # Extract the agent's description of what they're doing
                    tool_description = tool_call.arguments.get("tool_description", "")
                    logger.info(f"Tool call: {tool_call.name} | {tool_description}")

                    # Enhanced logging for tool call with agent's description
                    self.enhanced_logger.log_action_start(
                        action_type="tool_call",
                        details=tool_call.name,
                        tool_name=tool_call.name,
                        tool_args=tool_call.arguments
                    )
                    # Add the description immediately
                    if tool_description:
                        self.enhanced_logger.add_description_to_last_action(tool_description)

                    # Add tool call to context
                    self.context.append_tool_call(
                        tool_call.id,
                        tool_call.name,
                        tool_call.arguments
                    )

                    # Execute tool (description is extracted inside execute)
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)

                    # Get description from result if not already set
                    result_description = result.get("description", tool_description)

                    # Remove description from result for cleaner output
                    result_for_context = {k: v for k, v in result.items() if k != "description"}
                    result_str = json.dumps(result_for_context, indent=2, default=str)

                    # Enhanced logging for tool result with description
                    files_affected = []
                    if tool_call.name in ["write_file", "read_file"]:
                        files_affected = [tool_call.arguments.get("path", tool_call.arguments.get("filename", ""))]
                    self.enhanced_logger.log_tool_result(
                        tool_name=tool_call.name,
                        result=result_for_context,
                        description=result_description,
                        files_affected=files_affected
                    )

                    # Add result to context
                    self.context.append_tool_result(tool_call.id, result_str)

                    step_info["actions"].append({
                        "type": "tool_call",
                        "tool": tool_call.name,
                        "description": result_description,
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
