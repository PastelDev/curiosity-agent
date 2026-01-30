"""Curiosity Agent - Autonomous self-improving agent.

Modular architecture with BaseAgent class that all agent types inherit from:
- BaseAgent: Core agent functionality (context, tools, lifecycle)
- MainAgent: Main autonomous agent (continuous loop, meta tools)
- TournamentAgent: Agent for tournament containers
- SubAgent: Agent for one-off tasks
"""

from .openrouter_client import OpenRouterClient
from .context_manager import ContextManager
from .tool_registry import ToolRegistry
from .base_agent import BaseAgent, AgentTool, AgentState, AgentConfig
from .main_agent import MainAgent, CuriosityAgent
from .tournament_agent import TournamentAgent
from .sub_agent import SubAgent, WebSearchAgent, CodeExecutionAgent
from .tournament_engine import TournamentEngine, Tournament, TournamentStatus, RevealedFile
from .questions_manager import QuestionsManager
from .journal_manager import JournalManager
from .todo_manager import TodoManager
from .enhanced_logger import LogManager, MainAgentLogger, EnhancedLogger

__all__ = [
    "OpenRouterClient",
    "ContextManager",
    "ToolRegistry",
    "BaseAgent",
    "AgentTool",
    "AgentState",
    "AgentConfig",
    "MainAgent",
    "CuriosityAgent",
    "TournamentAgent",
    "SubAgent",
    "WebSearchAgent",
    "CodeExecutionAgent",
    "TournamentEngine",
    "Tournament",
    "TournamentStatus",
    "RevealedFile",
    "QuestionsManager",
    "JournalManager",
    "TodoManager",
    "LogManager",
    "MainAgentLogger",
    "EnhancedLogger",
]
