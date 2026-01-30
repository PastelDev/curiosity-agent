"""
Tournament Engine - Manages tournament execution with the new agent architecture.

Uses TournamentAgent and SubAgent classes, waiting for agents to signal
completion via complete_task rather than timeout-based execution.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Callable
import logging

from .base_agent import AgentConfig
from .tournament_agent import TournamentAgent
from .sub_agent import SubAgent, WebSearchAgent, CodeExecutionAgent
from .openrouter_client import OpenRouterClient


logger = logging.getLogger(__name__)


class TournamentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SYNTHESIS = "synthesis"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class RevealedFile:
    """A file revealed by an agent for sharing."""
    filename: str
    content: str
    file_type: str
    agent_id: str
    revealed_at: str
    description: Optional[str] = None


@dataclass
class SynthesisRound:
    """A synthesis round where agents collaborate."""
    round_number: int
    agent_count: int
    agents: list[TournamentAgent] = field(default_factory=list)
    input_files: list[dict] = field(default_factory=list)
    status: str = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "round_number": self.round_number,
            "agent_count": self.agent_count,
            "agents": [a.get_status() for a in self.agents],
            "input_files_count": len(self.input_files),
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }


@dataclass
class Tournament:
    """A complete tournament with multiple rounds."""
    id: str
    topic: str
    stages: list[int]
    debate_rounds: int
    model: str
    base_path: Path
    status: TournamentStatus = TournamentStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    synthesis_rounds: list[SynthesisRound] = field(default_factory=list)
    final_files: list[RevealedFile] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "stages": self.stages,
            "debate_rounds": self.debate_rounds,
            "model": self.model,
            "base_path": str(self.base_path),
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "synthesis_rounds": [r.to_dict() for r in self.synthesis_rounds],
            "final_files": [
                {
                    "filename": f.filename,
                    "file_type": f.file_type,
                    "description": f.description
                }
                for f in self.final_files
            ],
            "error": self.error
        }


class TournamentEngine:
    """
    Manages tournament execution with agent-controlled completion.

    Agents signal when they're done via complete_task, rather than
    being terminated by timeout. Timeouts are now safety limits.
    """

    def __init__(
        self,
        client: OpenRouterClient,
        base_path: str = "tournaments",
        model: str = "x-ai/grok-4.1-fast",
        max_parallel: int = 8,
        default_timeout: int = 600,  # Safety timeout (10 min)
        default_max_turns: int = 50
    ):
        self.client = client
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.max_parallel = max_parallel
        self.default_timeout = default_timeout
        self.default_max_turns = default_max_turns

        self.tournaments: dict[str, Tournament] = {}
        self._load_tournaments()

    def _load_tournaments(self):
        """Load existing tournaments from disk."""
        state_file = self.base_path / "tournaments_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                for t_data in data.get("tournaments", []):
                    tournament = self._reconstruct_tournament(t_data)
                    if tournament:
                        self.tournaments[tournament.id] = tournament
            except Exception as e:
                logger.error(f"Failed to load tournaments: {e}")

    def _save_tournaments(self):
        """Save tournaments state to disk."""
        state_file = self.base_path / "tournaments_state.json"
        data = {
            "saved_at": datetime.now().isoformat(),
            "tournaments": [t.to_dict() for t in self.tournaments.values()]
        }
        with open(state_file, "w") as f:
            json.dump(data, f, indent=2)

    def _reconstruct_tournament(self, data: dict) -> Optional[Tournament]:
        """Reconstruct a Tournament from saved data."""
        try:
            tournament = Tournament(
                id=data["id"],
                topic=data["topic"],
                stages=data["stages"],
                debate_rounds=data["debate_rounds"],
                model=data["model"],
                base_path=Path(data["base_path"]),
                status=TournamentStatus(data["status"]),
                created_at=data["created_at"]
            )
            tournament.started_at = data.get("started_at")
            tournament.completed_at = data.get("completed_at")
            tournament.error = data.get("error")
            return tournament
        except Exception as e:
            logger.error(f"Failed to reconstruct tournament: {e}")
            return None

    def create_tournament(
        self,
        topic: str,
        stages: Optional[list[int]] = None,
        debate_rounds: int = 2,
        model: Optional[str] = None
    ) -> Tournament:
        """Create a new tournament."""
        tournament_id = f"tournament_{uuid.uuid4().hex[:12]}"
        tournament_path = self.base_path / tournament_id
        tournament_path.mkdir(parents=True, exist_ok=True)

        tournament = Tournament(
            id=tournament_id,
            topic=topic,
            stages=stages or [4, 3, 2],
            debate_rounds=debate_rounds,
            model=model or self.model,
            base_path=tournament_path
        )

        self.tournaments[tournament_id] = tournament
        self._save_tournaments()

        logger.info(f"Created tournament: {tournament_id}, topic: {topic}")
        return tournament

    async def run_tournament(self, tournament_id: str) -> Tournament:
        """Run a complete tournament with all synthesis rounds."""
        tournament = self.tournaments.get(tournament_id)
        if not tournament:
            raise ValueError(f"Tournament not found: {tournament_id}")

        tournament.status = TournamentStatus.RUNNING
        tournament.started_at = datetime.now().isoformat()
        self._save_tournaments()

        logger.info(f"Starting tournament {tournament_id} with stages {tournament.stages}")

        try:
            current_files: list[dict] = []

            for round_idx, agent_count in enumerate(tournament.stages):
                round_number = round_idx + 1
                is_initial_round = round_idx == 0

                logger.info(f"Starting round {round_number} with {agent_count} agents")

                # Create synthesis round
                synthesis_round = SynthesisRound(
                    round_number=round_number,
                    agent_count=agent_count,
                    input_files=current_files.copy()
                )
                synthesis_round.status = "running"
                synthesis_round.started_at = datetime.now().isoformat()
                tournament.synthesis_rounds.append(synthesis_round)

                # Create agents for this round
                agents = []
                for i in range(agent_count):
                    agent = self._create_tournament_agent(
                        tournament=tournament,
                        round_number=round_number,
                        agent_index=i,
                        input_files=current_files,
                        is_initial_round=is_initial_round
                    )
                    agents.append(agent)
                    synthesis_round.agents.append(agent)

                # Run agents in parallel (respecting max_parallel)
                semaphore = asyncio.Semaphore(self.max_parallel)

                async def run_agent_with_semaphore(agent: TournamentAgent):
                    async with semaphore:
                        try:
                            # Agent controls its own completion via complete_task
                            # Timeout is just a safety limit
                            state = await agent.run()
                            return state
                        except Exception as e:
                            logger.error(f"Agent {agent.agent_id} failed: {e}")
                            return None

                tasks = [run_agent_with_semaphore(a) for a in agents]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Collect revealed files for next round
                current_files = []
                for agent in agents:
                    for revealed in agent.get_revealed_files():
                        current_files.append(revealed)

                synthesis_round.status = "completed"
                synthesis_round.completed_at = datetime.now().isoformat()

                logger.info(f"Round {round_number} completed with {len(current_files)} files")
                self._save_tournaments()

            # Store final files
            tournament.final_files = [
                RevealedFile(
                    filename=f["filename"],
                    content=f["content"],
                    file_type=f["file_type"],
                    agent_id=f["agent_id"],
                    revealed_at=f["revealed_at"],
                    description=f.get("description")
                )
                for f in current_files
            ]

            # Copy final files to output directory
            output_dir = tournament.base_path / "final_output"
            output_dir.mkdir(exist_ok=True)
            for rf in tournament.final_files:
                output_path = output_dir / rf.filename
                output_path.write_text(rf.content)

            tournament.status = TournamentStatus.COMPLETED
            tournament.completed_at = datetime.now().isoformat()
            logger.info(f"Tournament {tournament_id} completed with {len(tournament.final_files)} files")

        except Exception as e:
            tournament.status = TournamentStatus.FAILED
            tournament.error = str(e)
            tournament.completed_at = datetime.now().isoformat()
            logger.error(f"Tournament {tournament_id} failed: {e}")

        self._save_tournaments()
        return tournament

    def _create_tournament_agent(
        self,
        tournament: Tournament,
        round_number: int,
        agent_index: int,
        input_files: list[dict],
        is_initial_round: bool
    ) -> TournamentAgent:
        """Create a tournament agent for a specific round."""
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        container_path = tournament.base_path / f"round_{round_number}" / agent_id
        container_path.mkdir(parents=True, exist_ok=True)

        config = AgentConfig(
            model=tournament.model,
            max_turns=self.default_max_turns,
            timeout=self.default_timeout,
            compaction_threshold=0.85
        )

        agent = TournamentAgent(
            container_path=container_path,
            tournament_id=tournament.id,
            round_number=round_number,
            topic=tournament.topic,
            input_files=input_files,
            is_initial_round=is_initial_round,
            agent_id=agent_id,
            client=self.client,
            config=config
        )

        logger.info(f"Created tournament agent {agent_id} for round {round_number}")
        return agent

    async def call_subagent(
        self,
        task: str,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_turns: Optional[int] = None,
        enable_web_search: bool = False,
        enable_code_execution: bool = False,
        summarizer_fn: Optional[Callable] = None
    ) -> dict:
        """
        Call a single subagent with a task and get results.

        The agent runs until it calls complete_task.
        """
        agent_id = f"subagent_{uuid.uuid4().hex[:8]}"
        workspace_path = self.base_path / "subagents" / agent_id
        workspace_path.mkdir(parents=True, exist_ok=True)

        config = AgentConfig(
            model=model or self.model,
            max_turns=max_turns or 30,
            timeout=timeout or 300,
            compaction_threshold=0.85
        )

        # Choose agent type based on capabilities
        if enable_web_search:
            agent = WebSearchAgent(
                task=task,
                workspace_path=workspace_path,
                agent_id=agent_id,
                client=self.client,
                config=config,
                summarizer_fn=summarizer_fn
            )
        elif enable_code_execution:
            agent = CodeExecutionAgent(
                task=task,
                workspace_path=workspace_path,
                agent_id=agent_id,
                client=self.client,
                config=config
            )
        else:
            agent = SubAgent(
                task=task,
                workspace_path=workspace_path,
                agent_id=agent_id,
                client=self.client,
                config=config
            )

        logger.info(f"Starting subagent {agent_id} for task: {task[:100]}...")

        try:
            state = await agent.run()

            return {
                "success": state.status == "completed",
                "agent_id": agent_id,
                "status": state.status,
                "completion_reason": state.completion_reason,
                "output_files": agent.get_output_files() if hasattr(agent, 'get_output_files') else [],
                "workspace_files": agent.get_workspace_files() if hasattr(agent, 'get_workspace_files') else [],
                "turns": state.turn_count,
                "logs": agent.get_logs(limit=50)
            }

        except Exception as e:
            logger.error(f"Subagent {agent_id} failed: {e}")
            return {
                "success": False,
                "agent_id": agent_id,
                "error": str(e),
                "logs": agent.get_logs(limit=50) if agent else []
            }

    def get_tournament(self, tournament_id: str) -> Optional[Tournament]:
        """Get a tournament by ID."""
        return self.tournaments.get(tournament_id)

    def list_tournaments(self) -> list[dict]:
        """List all tournaments."""
        return [t.to_dict() for t in self.tournaments.values()]

    def get_container_logs(self, tournament_id: str, agent_id: str) -> list[dict]:
        """Get logs for a specific agent in a tournament."""
        tournament = self.tournaments.get(tournament_id)
        if tournament:
            for round in tournament.synthesis_rounds:
                for agent in round.agents:
                    if agent.agent_id == agent_id:
                        return agent.get_logs()
        return []

    def get_container_files(self, tournament_id: str, agent_id: str) -> list[dict]:
        """Get files from a specific agent container."""
        tournament = self.tournaments.get(tournament_id)
        if tournament:
            for round in tournament.synthesis_rounds:
                for agent in round.agents:
                    if agent.agent_id == agent_id:
                        return agent.get_container_files()
        return []
