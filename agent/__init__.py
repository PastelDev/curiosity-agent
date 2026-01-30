"""Curiosity Agent - Autonomous self-improving agent.

New modular architecture with BaseAgent class that all agent types inherit from:
- BaseAgent: Core agent functionality (context, tools, lifecycle)
- MainAgent: Main autonomous agent (continuous loop, meta tools)
- TournamentAgent: Agent for tournament containers
- SubAgent: Agent for one-off tasks
- WebSearchAgent: SubAgent with web search enabled
- CodeExecutionAgent: SubAgent with code execution enabled
"""

# Core components
from .openrouter_client import OpenRouterClient
from .context_manager import ContextManager
from .tool_registry import ToolRegistry

# Base agent (new architecture)
from .base_agent import BaseAgent, AgentTool, AgentState, AgentConfig

# Specialized agents
from .main_agent import MainAgent, CuriosityAgent  # CuriosityAgent is alias for MainAgent
from .tournament_agent import TournamentAgent
from .sub_agent import SubAgent, WebSearchAgent, CodeExecutionAgent

# Tournament engine (new version using agent classes)
from .tournament_engine import TournamentEngine, Tournament, TournamentStatus, RevealedFile

# Managers
from .questions_manager import QuestionsManager
from .journal_manager import JournalManager
from .todo_manager import TodoManager

# Logging
from .enhanced_logger import LogManager, MainAgentLogger, EnhancedLogger

# Backward compatibility - import old tournament module
from . import tournament as tournament_legacy

__all__ = [
    # Core
    "OpenRouterClient",
    "ContextManager",
    "ToolRegistry",

    # Base agent architecture
    "BaseAgent",
    "AgentTool",
    "AgentState",
    "AgentConfig",

    # Specialized agents
    "MainAgent",
    "CuriosityAgent",  # Backward compatible alias
    "TournamentAgent",
    "SubAgent",
    "WebSearchAgent",
    "CodeExecutionAgent",

    # Tournament system
    "TournamentEngine",
    "Tournament",
    "TournamentStatus",
    "RevealedFile",

    # Managers
    "QuestionsManager",
    "JournalManager",
    "TodoManager",

    # Logging
    "LogManager",
    "MainAgentLogger",
    "EnhancedLogger",

    # Legacy
    "tournament_legacy"
]
