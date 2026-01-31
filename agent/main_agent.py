"""
Main Agent - The primary autonomous agent that runs continuously.

Inherits from BaseAgent and adds:
- Persistent state
- Meta tools (journal, questions, tournaments, etc.)
- Continuous loop with prompt injection
- Goal-driven execution
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
import logging.handlers

from .base_agent import BaseAgent, AgentTool, AgentConfig
from .openrouter_client import OpenRouterClient
from .context_manager import ContextManager
from .tool_registry import ToolRegistry
from .questions_manager import QuestionsManager
from .journal_manager import JournalManager
from .todo_manager import TodoManager
from .enhanced_logger import LogManager, MainAgentLogger


logger = logging.getLogger(__name__)


def setup_logging(log_path: str = "logs/agent.log", level: str = "INFO"):
    """Configure Python logging with file handler for persistent logging."""
    log_dir = Path(log_path).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler with rotation (10MB max, 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on re-init
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            root_logger.removeHandler(handler)

    root_logger.addHandler(file_handler)
    logger.info(f"Logging configured: {log_path} at level {level}")


# Tool usage guidance for the system prompt - tells the agent WHEN to use each tool
TOOL_GUIDANCE = {
    "write_journal": "Use FREQUENTLY to document ideas, experiments, and failures. Write to journal before moving on to new tasks. This is your persistent memory.",
    "read_journal": "Use to recall past learnings BEFORE starting new work. Check if similar experiments have been tried. Build on what you've learned.",
    "create_tournament": "Use for complex problems requiring multiple perspectives. Creates parallel agents that debate and synthesize their outputs into superior solutions.",
    "manage_tournament": "Check tournament progress, get results, view container logs. Use to monitor ongoing tournaments and retrieve final syntheses.",
    "call_subagent": "Use for isolated tasks that can run independently. Good for research, computation, or tasks that don't need your full context.",
    "ask_user": "Use when you need user input or clarification. Questions are answered asynchronously - continue working while waiting, don't block.",
    "manage_questions": "Check for answered questions, list pending questions, or delete old ones after processing.",
    "manage_todos": "Track your work. Add tasks as you discover them, update status as you progress, mark items done. Keep this current.",
    "complete_task": "Use ONLY when truly done or blocked. Requires 3+ improvement iterations and journal documentation. This PAUSES execution - prefer to keep improving.",
    "manage_context": "Compact context when full, adjust threshold, or check usage. Use to manage your memory when approaching limits.",
    "create_tool": "Create new custom tools when you need capabilities not already available. Tools persist across sessions.",
    "delete_tool": "Remove custom tools that are no longer needed or that have bugs.",
    "describe_action": "Add descriptions to your actions for logging. Helps track what you're doing and why.",
    "read_file": "Read files in your sandbox workspace. Use to examine your previous work or data files.",
    "write_file": "Create or modify files. Creates directories automatically. Use for persistent storage of work products.",
    "list_directory": "List files in a directory. Use to explore your workspace and find files.",
    "run_code": "Execute Python code for testing, experiments, or computations. Use for validation and exploration.",
    "internet_search": "Research topics or find current information. Use when you need external knowledge.",
    "fetch_url": "Read specific web pages for detailed content. Use after search to get full information from sources."
}


class MainAgentState:
    """Persistent state for the main agent."""

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


class MainAgent(BaseAgent):
    """
    The main autonomous agent.

    Features:
    - Continuous loop execution
    - Persistent state across restarts
    - Meta tools (journal, questions, todos, tournaments)
    - Prompt injection system
    - Goal-driven behavior
    - Enhanced logging
    """

    def __init__(self, config_path: str = "config/settings.yaml"):
        # Load configuration
        with open(config_path) as f:
            self.app_config = yaml.safe_load(f)

        # Setup logging from config
        log_config = self.app_config.get("logging", {})
        setup_logging(
            log_path=log_config.get("file", "logs/agent.log"),
            level=log_config.get("level", "INFO")
        )

        # Create agent config from app config
        agent_config = AgentConfig(
            model=self.app_config["openrouter"]["models"]["main"],
            summarizer_model=self.app_config["openrouter"]["models"].get("summarizer"),
            max_tokens=self.app_config["context"]["max_tokens"],
            compaction_threshold=self.app_config["context"]["compaction_threshold"],
            temperature=self.app_config["openrouter"]["temperature"],
            max_response_tokens=self.app_config["openrouter"]["max_tokens"],
            max_turns=None  # Main agent runs indefinitely
        )

        # Initialize base agent
        super().__init__(
            agent_id="main_agent",
            agent_type="main",
            config=agent_config,
            context_state_path="config/context_state.json"
        )

        # Initialize additional components
        sandbox_config = self.app_config.get("sandbox", {})

        # Todo manager
        self.todos = TodoManager(
            todo_path=sandbox_config.get("todo_path", "agent_sandbox/todo.json")
        )

        # Create summarizer function for web search
        async def search_summarizer(prompt: str) -> str:
            summarizer_model = self.app_config["openrouter"]["models"].get("summarizer")
            return await self.client.simple_completion(
                prompt=prompt,
                system="You are a search result analyzer. Extract and structure key information concisely.",
                model=summarizer_model,
                max_tokens=1024
            )

        # Tool registry (for core tools and custom tools)
        self.tool_registry = ToolRegistry(
            tools_dir=sandbox_config.get("tools_path", "agent_sandbox/tools"),
            sandbox_root=sandbox_config.get("root", "agent_sandbox"),
            sandbox_temp_path=sandbox_config.get("temp_path", "agent_sandbox/temp"),
            protected_paths=sandbox_config.get("protected_paths", ["agent/", "app/", "config/"]),
            summarizer_fn=search_summarizer
        )

        # Other managers
        self.questions = QuestionsManager(questions_path=self.app_config["questions"]["path"])
        self.journal = JournalManager(
            structured_path=self.app_config["journal"]["structured_path"],
            freeform_path=self.app_config["journal"]["freeform_path"]
        )

        # Enhanced logging
        self.log_manager = LogManager(base_log_path="logs")
        self.enhanced_logger = self.log_manager.get_main_logger()

        # Tournament engine (will be set up when needed)
        self._tournament_engine = None

        # Persistent state
        self.persistent_state = MainAgentState()

        # Load goal
        goal_path = Path("config/goal.md")
        self.goal = goal_path.read_text() if goal_path.exists() else "Explore and improve."

        # Prompt queue for user messages
        self._prompt_queue: deque = deque()

        # Register meta tools
        self._register_meta_tools()

        # Import core tools from tool registry
        self._import_core_tools()

    @property
    def tournament_engine(self):
        """Lazy initialization of tournament engine."""
        if self._tournament_engine is None:
            from .tournament_engine import TournamentEngine
            tournament_config = self.app_config.get("tournament", {})
            self._tournament_engine = TournamentEngine(
                client=self.client,
                base_path="tournaments",
                model=self.app_config["openrouter"]["models"].get(
                    "tournament",
                    self.app_config["openrouter"]["models"]["main"]
                ),
                max_parallel=tournament_config.get("max_parallel_agents", 8),
                default_timeout=tournament_config.get("timeout_per_agent_seconds", 300)
            )
        return self._tournament_engine

    def _import_core_tools(self):
        """Import core tools from tool registry into agent tools."""
        for tool in self.tool_registry.get_all_tools():
            self.register_tool(AgentTool(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                execute=tool.execute,
                category=tool.category,
                protected=tool.protected
            ))

    def _register_meta_tools(self):
        """Register meta tools for the main agent."""

        # Tool creation
        self.register_tool(AgentTool(
            name="create_tool",
            description="Create a new custom tool",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "parameters_schema": {"type": "object"},
                    "implementation": {
                        "type": "string",
                        "description": "Python code with async def execute(params):"
                    }
                },
                "required": ["name", "description", "parameters_schema", "implementation"]
            },
            execute=lambda p: self.tool_registry.create_tool(
                p["name"], p["description"], p["parameters_schema"], p["implementation"]
            ),
            category="meta",
            protected=True
        ))

        # Tool deletion
        self.register_tool(AgentTool(
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
            execute=lambda p: self.tool_registry.delete_tool(p["name"]) if p.get("confirm") else {"success": False, "error": "Must confirm deletion"},
            category="meta",
            protected=True
        ))

        # Journal tools
        self.register_tool(AgentTool(
            name="write_journal",
            description="Write to the knowledge base (idea, empirical_result, tool_spec, failed_attempt, freeform)",
            parameters={
                "type": "object",
                "properties": {
                    "entry_type": {
                        "type": "string",
                        "enum": ["idea", "empirical_result", "tool_spec", "failed_attempt", "freeform"]
                    },
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

        self.register_tool(AgentTool(
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
        self.register_tool(AgentTool(
            name="ask_user",
            description="Post a question for the user (non-blocking)",
            parameters={
                "type": "object",
                "properties": {
                    "question_text": {"type": "string"},
                    "question_type": {
                        "type": "string",
                        "enum": ["multiple_choice", "free_text", "yes_no", "rating"]
                    },
                    "options": {"type": "array", "items": {"type": "string"}},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "default": "medium"
                    },
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

        self.register_tool(AgentTool(
            name="manage_questions",
            description="View or manage questions (list_pending, list_answered, delete, check_new_answers)",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list_pending", "list_answered", "delete", "check_new_answers"]
                    },
                    "question_id": {"type": "string"}
                },
                "required": ["action"]
            },
            execute=self._execute_manage_questions,
            category="meta",
            protected=True
        ))

        # Todo management
        self.register_tool(AgentTool(
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

        # Tournament creation
        self.register_tool(AgentTool(
            name="create_tournament",
            description="Create a multi-agent tournament for collaborative problem solving. Agents work in parallel, then synthesize their outputs in rounds.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic/task for agents to work on"},
                    "stages": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Number of agents per round, e.g., [4, 3, 2]"
                    },
                    "debate_rounds": {"type": "integer", "default": 2},
                    "auto_start": {"type": "boolean", "default": True}
                },
                "required": ["topic"]
            },
            execute=self._execute_create_tournament,
            category="meta",
            protected=True
        ))

        # Tournament management
        self.register_tool(AgentTool(
            name="manage_tournament",
            description="Manage tournaments: start, get_status, list_all, get_results",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "get_status", "list_all", "get_results", "get_container_logs"]
                    },
                    "tournament_id": {"type": "string"},
                    "container_id": {"type": "string"}
                },
                "required": ["action"]
            },
            execute=self._execute_manage_tournament,
            category="meta",
            protected=True
        ))

        # Subagent calling
        self.register_tool(AgentTool(
            name="call_subagent",
            description="Call a single subagent to perform a task. The subagent runs in an isolated container and returns its output files.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task for the subagent"},
                    "model": {"type": "string", "description": "Optional model to use"},
                    "timeout": {"type": "integer", "default": 300, "description": "Timeout in seconds"},
                    "enable_web_search": {"type": "boolean", "default": False},
                    "enable_code_execution": {"type": "boolean", "default": False}
                },
                "required": ["task"]
            },
            execute=self._execute_call_subagent,
            category="meta",
            protected=True
        ))

        # Action description
        self.register_tool(AgentTool(
            name="describe_action",
            description="Provide a brief description of the action you just performed.",
            parameters={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "A brief description of what you just did"}
                },
                "required": ["description"]
            },
            execute=self._execute_describe_action,
            category="meta",
            protected=True
        ))

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
            stages = self.app_config.get("tournament", {}).get("default_stages", [4, 3, 2])

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
            return {"success": True, "tournaments": tournaments, "count": len(tournaments)}

        elif action == "get_status":
            if not tournament_id:
                return {"success": False, "error": "tournament_id required"}
            tournament = self.tournament_engine.get_tournament(tournament_id)
            if not tournament:
                return {"success": False, "error": "Tournament not found"}
            return {"success": True, "tournament": tournament.to_dict()}

        elif action == "start":
            if not tournament_id:
                return {"success": False, "error": "tournament_id required"}
            tournament = self.tournament_engine.get_tournament(tournament_id)
            if not tournament:
                return {"success": False, "error": "Tournament not found"}
            from .tournament_engine import TournamentStatus
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
                        "content": f.content[:2000],
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
            return {"success": True, "logs": logs}

        return {"success": False, "error": f"Unknown action: {action}"}

    async def _execute_call_subagent(self, params: dict) -> dict:
        """Call a subagent to perform a task."""
        task = params.get("task", "")
        model = params.get("model")
        timeout = params.get("timeout", 300)
        enable_web_search = params.get("enable_web_search", False)
        enable_code_execution = params.get("enable_code_execution", False)

        if not task:
            return {"success": False, "error": "Task is required"}

        self.enhanced_logger.log_system(
            f"Calling subagent",
            description=f"Task: {task[:100]}..."
        )

        result = await self.tournament_engine.call_subagent(
            task=task,
            model=model,
            timeout=timeout,
            enable_web_search=enable_web_search,
            enable_code_execution=enable_code_execution
        )

        self.enhanced_logger.log_system(
            f"Subagent completed: {result.get('agent_id', 'unknown')}",
            description=f"Success: {result.get('success')}, Files: {len(result.get('output_files', []))}"
        )

        return result

    def _execute_describe_action(self, params: dict) -> dict:
        """Add a description to the last action."""
        description = params.get("description", "")

        if not description:
            return {"success": False, "error": "Description is required"}

        self.enhanced_logger.add_description_to_last_action(description)

        return {"success": True, "message": "Description added to last action"}

    def _build_tool_documentation(self) -> str:
        """Build detailed tool documentation with usage guidance for the system prompt."""
        docs = []
        for tool_name in self.list_tools():
            tool = self.get_tool(tool_name)
            if tool:
                guidance = TOOL_GUIDANCE.get(tool_name, "")
                docs.append(f"- **{tool_name}**: {tool.description}")
                if guidance:
                    docs.append(f"  *When to use*: {guidance}")
        return "\n".join(docs)

    def build_system_prompt(self) -> str:
        """Build comprehensive system prompt with goal, tools, context, and philosophy."""

        # Get answered questions for context
        answered = self.questions.get_answered()
        answered_ctx = ""
        if answered:
            answered_ctx = "\n## Answers From User\nThese are answers to questions you asked:\n"
            for q in answered[-10:]:  # Last 10 answers
                answered_ctx += f"- Q: {q.question_text}\n  A: {q.answer}\n"

        # Todo context with progress
        todo_ctx = self.todos.get_context_summary()

        # Journal stats for awareness
        stats = self.journal.get_stats()
        journal_ctx = f"""## Your Knowledge Base (Journal)
You have recorded: {stats.get('ideas', 0)} ideas, {stats.get('empirical_results', 0)} experiments, {stats.get('failed_attempts', 0)} failed attempts, {stats.get('tool_specs', 0)} tool specs.
READ YOUR JOURNAL before starting new work to build on past learnings!"""

        # Tool documentation with usage guidance
        tool_docs = self._build_tool_documentation()

        return f"""You are Curiosity, an autonomous self-improving agent committed to continuous learning and improvement.

## Your Current Goal
{self.goal}

## CRITICAL: Continuous Improvement Philosophy
Your purpose is to run for as long as allowed, continuously adding details, improving structure, and making your work better. Follow these principles:
- NEVER consider yourself "done" - there is ALWAYS room for improvement
- Iterate on solutions AT LEAST 3 times before considering complete
- Use tournaments to get diverse perspectives on complex problems
- Document EVERYTHING in the journal - ideas, experiments, failures, learnings
- Learn from failed attempts - they are valuable data, not wasted effort
- Before completing, ask yourself: "Can this be improved? What's missing? What edge cases exist? Could a tournament help?"
- The goal is excellence through iteration, not speed to completion
{answered_ctx}
## Your Todo List
{todo_ctx}

{journal_ctx}

## Your Tools (with Usage Guidance)
{tool_docs}

## Guidelines for Effective Autonomous Work
1. **Start by reading**: Check your journal and todos before beginning new work - build on what you've learned
2. **Document as you go**: Write to journal frequently, not just at the end - capture insights while fresh
3. **Iterate relentlessly**: Don't settle for first attempts - refine, improve, enhance at least 3 times
4. **Use tournaments wisely**: For complex problems, spawn multiple agents to explore different approaches in parallel
5. **Ask questions**: When uncertain, ask the user (async - continue working, don't wait)
6. **Track progress meticulously**: Update todos as you work, mark items done, add new discoveries
7. **Learn from failures**: Log every failed attempt with analysis of what went wrong and why
8. **Manage context wisely**: Compact when needed, but preserve important information in journal first

## Context Management
Current usage: {self.context.usage_percent * 100:.1f}% | Threshold: {self.context.threshold * 100}%
Your context will auto-compact at threshold. Use manage_context to adjust or manually compact.

## IMPORTANT REMINDERS
- Think step by step before acting
- The complete_task tool PAUSES you - use sparingly, prefer to keep improving
- complete_task requires: 3+ improvement iterations, journal entries documenting work, clear justification
- Questions to users are asynchronous - continue working after asking, don't wait
- You can create new tools with create_tool if you need custom capabilities
- Your goal is to maximize the quality of your output through continuous iteration
"""

    def get_initial_prompt(self) -> Optional[str]:
        """Main agent doesn't need an initial prompt - it's goal-driven."""
        return None

    def _get_improvement_nudge(self) -> str:
        """Generate contextual improvement nudges based on current state."""
        nudges = []

        # Check journal activity
        stats = self.journal.get_stats()
        total_entries = sum([
            stats.get('ideas', 0),
            stats.get('empirical_results', 0),
            stats.get('failed_attempts', 0),
            stats.get('tool_specs', 0)
        ])

        if total_entries < 5:
            nudges.append("You haven't written much to the journal. Document your ideas and experiments!")

        # Check failed attempts - failure is valuable data
        if stats.get('failed_attempts', 0) == 0:
            nudges.append("No failed attempts logged. Are you trying bold experiments? Failure is valuable data!")

        # Check todos
        todos = self.todos.list_all()
        if todos:
            done_count = len([t for t in todos if t.get('status') == 'done'])
            in_progress = [t for t in todos if t.get('status') == 'in_progress']

            if done_count == len(todos):
                nudges.append("All todos are done! What's the next frontier to explore? Add new goals!")

            if not in_progress and len(todos) > done_count:
                nudges.append("Nothing in progress. Pick a task and start working on it!")

        # Tournament suggestion
        if stats.get('ideas', 0) > 3 and self.persistent_state.loop_count > 20:
            tournaments = self.tournament_engine.list_tournaments()
            if len(tournaments) == 0:
                nudges.append("You have ideas but no tournaments. Try spawning agents to explore them in parallel!")

        if nudges:
            return "\n".join([f"- {n}" for n in nudges])
        return ""

    async def pre_step(self):
        """Pre-step hook - inject queued prompts, check answers, and nudge improvement."""
        # Rebuild system prompt with updated todos
        system_prompt = self.build_system_prompt()
        self.context.set_system_prompt(system_prompt)

        # Every 10 loops, add an improvement nudge
        if self.persistent_state.loop_count > 0 and self.persistent_state.loop_count % 10 == 0:
            nudge = self._get_improvement_nudge()
            if nudge:
                self.context.append_system_notification(f"[IMPROVEMENT REMINDER]\n{nudge}")

        # Inject queued prompts
        while self._prompt_queue:
            prompt_data = self._prompt_queue.popleft()
            self.context.append_system_notification(
                f"[USER PROMPT]\nThe user has sent you the following message:\n\n{prompt_data['prompt']}"
            )
            logger.info(f"Injected queued prompt: {prompt_data['id']}")

        # Check for answered questions
        new_answers = self.questions.check_new_answers()
        if new_answers:
            notification = self.questions.format_for_notification(new_answers)
            self.context.append_system_notification(notification)

    async def post_step(self, step_info: dict):
        """Post-step hook - update persistent state."""
        self.persistent_state.loop_count += 1
        self.persistent_state.last_action = step_info.get("actions", [{}])[-1].get("type", "unknown")
        self.persistent_state.save()

    async def run_continuous(self, max_iterations: Optional[int] = None):
        """
        Run the agent loop continuously.

        Unlike base run(), this doesn't end when complete_task is called.
        Instead, it just pauses and can be resumed.
        """
        self._running = True
        self.persistent_state.status = "running"
        self.persistent_state.started_at = datetime.now().isoformat()
        self.persistent_state.save()

        self.log("INFO", "Main agent started")

        # Setup
        self.setup()

        # Build and set system prompt
        system_prompt = self.build_system_prompt()
        self.context.set_system_prompt(system_prompt)

        iteration = 0
        while self._running:
            if self._paused:
                await asyncio.sleep(1)
                continue

            step_info = await self.step()
            logger.info(f"Loop {self.persistent_state.loop_count}: {step_info.get('actions', [])}")

            # If agent signals completion, just pause (don't stop)
            if step_info.get("completed"):
                self.log("INFO", "Agent signaled pause",
                        description=f"Reason: {step_info.get('completion_reason')}")
                # Reset completion flag so it can continue
                self._completed = False
                self._completion_event.clear()

            iteration += 1
            if max_iterations and iteration >= max_iterations:
                logger.info(f"Reached max iterations ({max_iterations})")
                break

            await asyncio.sleep(0.5)

        self.persistent_state.status = "stopped"
        self.persistent_state.save()
        self.teardown()
        self.log("INFO", "Main agent stopped")

    def queue_prompt(self, prompt: str, priority: str = "normal") -> str:
        """Queue a prompt to be injected at the start of the next loop iteration."""
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

    def restart(self, prompt: Optional[str] = None, keep_context: bool = False):
        """Restart the agent loop."""
        self._running = False
        self._paused = False
        self.persistent_state.loop_count = 0

        if not keep_context:
            self.context.reset()

        if prompt:
            self.context.append_system_notification(
                f"[USER RESTART MESSAGE]\nThe user has restarted the agent with the following message:\n\n{prompt}"
            )

        self.persistent_state.status = "stopped"
        self.persistent_state.save()
        logger.info(f"Agent restart initiated with prompt: {prompt[:50] if prompt else 'None'}...")

    def pause(self):
        """Pause the agent loop and persist status."""
        super().pause()
        self.persistent_state.status = "paused"
        self.persistent_state.save()

    def resume(self):
        """Resume the agent loop and persist status."""
        super().resume()
        self.persistent_state.status = "running"
        self.persistent_state.save()

    def get_status(self) -> dict:
        """Get current agent status with loop count from persistent state."""
        base_status = super().get_status()
        # Override with persistent state values
        base_status["loop_count"] = self.persistent_state.loop_count
        base_status["status"] = self.persistent_state.status
        base_status["total_tokens"] = self.persistent_state.total_tokens
        base_status["total_cost"] = self.persistent_state.total_cost
        base_status["last_action"] = self.persistent_state.last_action
        base_status["started_at"] = self.persistent_state.started_at
        return base_status

    def get_full_status(self) -> dict:
        """Get comprehensive status including all components."""
        return {
            **self.persistent_state.to_dict(),
            "context": self.context.get_status(),
            "journal": self.journal.get_stats(),
            "pending_questions": len(self.questions.get_pending()),
            "tools_count": len(self.list_tools())
        }


# Alias for backward compatibility
CuriosityAgent = MainAgent


# For running directly
async def main():
    agent = MainAgent()
    await agent.run_continuous()


if __name__ == "__main__":
    asyncio.run(main())
