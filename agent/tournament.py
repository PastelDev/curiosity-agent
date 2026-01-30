"""
Tournament Engine for Curiosity Agent.

Implements multi-agent tournaments with:
- Container management (isolated sandboxes per agent)
- Parallel agent execution
- Synthesis loops for collaborative refinement
- Enhanced logging with descriptions
- File reveal system for agents to share outputs
"""

import asyncio
import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any
import logging

from .openrouter_client import OpenRouterClient


logger = logging.getLogger(__name__)


class TournamentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SYNTHESIS = "synthesis"
    COMPLETED = "completed"
    FAILED = "failed"


class ContainerStatus(Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class LogEntry:
    """Enhanced log entry with description."""
    timestamp: str
    level: str
    message: str
    description: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_result: Optional[Any] = None
    container_id: Optional[str] = None
    agent_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_result": self.tool_result,
            "container_id": self.container_id,
            "agent_id": self.agent_id
        }


@dataclass
class RevealedFile:
    """A file revealed by an agent for sharing."""
    filename: str
    content: str
    file_type: str  # md, py, js, json, etc.
    agent_id: str
    container_id: str
    revealed_at: str
    description: Optional[str] = None


@dataclass
class AgentContainer:
    """An isolated container/sandbox for an agent."""
    id: str
    tournament_id: str
    agent_model: str
    round_number: int
    container_path: Path
    status: ContainerStatus = ContainerStatus.INITIALIZING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    logs: list[LogEntry] = field(default_factory=list)
    revealed_files: list[RevealedFile] = field(default_factory=list)
    output_md: Optional[str] = None
    error: Optional[str] = None

    def log(self, level: str, message: str, description: Optional[str] = None, **kwargs):
        """Add a log entry with optional description."""
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            message=message,
            description=description,
            container_id=self.id,
            **kwargs
        )
        self.logs.append(entry)
        logger.log(
            getattr(logging, level.upper(), logging.INFO),
            f"[Container:{self.id[:8]}] {message}" + (f" | {description}" if description else "")
        )
        return entry

    def reveal_file(self, filename: str, content: str, file_type: str,
                    agent_id: str, description: Optional[str] = None) -> RevealedFile:
        """Reveal a file from this container."""
        revealed = RevealedFile(
            filename=filename,
            content=content,
            file_type=file_type,
            agent_id=agent_id,
            container_id=self.id,
            revealed_at=datetime.now().isoformat(),
            description=description
        )
        self.revealed_files.append(revealed)

        # Also write to container path
        file_path = self.container_path / "revealed" / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        self.log("INFO", f"Revealed file: {filename}", description=description)
        return revealed

    def get_files(self) -> list[dict]:
        """Get all files in this container."""
        files = []
        if self.container_path.exists():
            for path in self.container_path.rglob("*"):
                if path.is_file():
                    rel_path = path.relative_to(self.container_path)
                    try:
                        content = path.read_text()
                    except Exception:
                        content = "[Binary or unreadable file]"
                    files.append({
                        "path": str(rel_path),
                        "content": content,
                        "size": path.stat().st_size
                    })
        return files

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "agent_model": self.agent_model,
            "round_number": self.round_number,
            "container_path": str(self.container_path),
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "logs": [log.to_dict() for log in self.logs],
            "revealed_files": [
                {
                    "filename": f.filename,
                    "file_type": f.file_type,
                    "agent_id": f.agent_id,
                    "revealed_at": f.revealed_at,
                    "description": f.description
                }
                for f in self.revealed_files
            ],
            "output_md": self.output_md,
            "error": self.error
        }


@dataclass
class SynthesisRound:
    """A synthesis round where agents collaborate."""
    round_number: int
    agent_count: int
    containers: list[AgentContainer] = field(default_factory=list)
    input_files: list[RevealedFile] = field(default_factory=list)
    status: str = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "round_number": self.round_number,
            "agent_count": self.agent_count,
            "containers": [c.to_dict() for c in self.containers],
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
    stages: list[int]  # e.g., [4, 3, 2] = 4 agents -> 3 agents -> 2 agents
    debate_rounds: int
    model: str
    base_path: Path
    status: TournamentStatus = TournamentStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    synthesis_rounds: list[SynthesisRound] = field(default_factory=list)
    final_files: list[RevealedFile] = field(default_factory=list)
    logs: list[LogEntry] = field(default_factory=list)
    error: Optional[str] = None

    def log(self, level: str, message: str, description: Optional[str] = None, **kwargs):
        """Add a tournament-level log entry."""
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            message=message,
            description=description,
            **kwargs
        )
        self.logs.append(entry)
        logger.log(
            getattr(logging, level.upper(), logging.INFO),
            f"[Tournament:{self.id[:8]}] {message}" + (f" | {description}" if description else "")
        )
        return entry

    def get_all_containers(self) -> list[AgentContainer]:
        """Get all containers across all rounds."""
        containers = []
        for round in self.synthesis_rounds:
            containers.extend(round.containers)
        return containers

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
            "logs": [log.to_dict() for log in self.logs],
            "error": self.error,
            "container_count": len(self.get_all_containers())
        }


class TournamentEngine:
    """
    Manages tournament execution with parallel agents and synthesis loops.
    """

    def __init__(
        self,
        client: OpenRouterClient,
        base_path: str = "tournaments",
        model: str = "x-ai/grok-4.1-fast",
        max_parallel: int = 8,
        timeout_per_agent: int = 300
    ):
        self.client = client
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.max_parallel = max_parallel
        self.timeout_per_agent = timeout_per_agent

        self.tournaments: dict[str, Tournament] = {}
        self._load_tournaments()

    def _load_tournaments(self):
        """Load existing tournaments from disk."""
        state_file = self.base_path / "tournaments_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                # Reconstruct tournaments from saved state
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
        """Reconstruct a Tournament from saved dict data."""
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
        tournament.log("INFO", f"Tournament created: {topic}",
                      description="Initialized tournament structure with specified stages")
        self._save_tournaments()

        return tournament

    def _create_container(
        self,
        tournament: Tournament,
        round_number: int,
        agent_index: int
    ) -> AgentContainer:
        """Create an isolated container for an agent."""
        container_id = f"container_{uuid.uuid4().hex[:8]}"
        container_path = tournament.base_path / f"round_{round_number}" / container_id
        container_path.mkdir(parents=True, exist_ok=True)

        # Create standard directories
        (container_path / "workspace").mkdir(exist_ok=True)
        (container_path / "revealed").mkdir(exist_ok=True)
        (container_path / "logs").mkdir(exist_ok=True)

        container = AgentContainer(
            id=container_id,
            tournament_id=tournament.id,
            agent_model=tournament.model,
            round_number=round_number,
            container_path=container_path
        )

        container.log("INFO", f"Container initialized for round {round_number}, agent {agent_index}",
                     description="Created isolated workspace with standard directories")

        return container

    def _build_agent_prompt(
        self,
        tournament: Tournament,
        container: AgentContainer,
        input_files: list[RevealedFile],
        is_initial_round: bool
    ) -> str:
        """Build the prompt for an agent in a container."""

        if is_initial_round:
            prompt = f"""You are an autonomous agent participating in a collaborative tournament.

## Your Task
{tournament.topic}

## Instructions
1. Analyze the topic and develop your approach
2. Create files to document your work:
   - Create a main .md file explaining your reasoning and approach
   - Create any code files or additional documentation as needed
3. Use the 'reveal' tool to share files you want to contribute to the synthesis

## Available Tools
- write_file: Write content to a file in your workspace
- read_file: Read a file from your workspace
- list_files: List files in your workspace
- reveal: Share a file with other agents for synthesis

## Guidelines
- Think carefully about the topic before starting
- Document your reasoning clearly
- Focus on quality over quantity
- Be creative but practical

Begin your work now.
"""
        else:
            # Synthesis round - include input files from previous round
            files_summary = "\n".join([
                f"- {f.filename} (from agent {f.agent_id[:8]}): {f.description or 'No description'}"
                for f in input_files
            ])

            files_content = "\n\n---\n\n".join([
                f"### {f.filename}\n```{f.file_type}\n{f.content}\n```"
                for f in input_files
            ])

            prompt = f"""You are an autonomous agent in a synthesis round of a collaborative tournament.

## Original Topic
{tournament.topic}

## Your Task
Review the contributions from the previous round and synthesize the best ideas into improved outputs.

## Input Files from Previous Round
{files_summary}

## File Contents
{files_content}

## Instructions
1. Review all input files carefully
2. Identify the strongest ideas and approaches
3. Synthesize and improve upon them
4. Create new files that combine the best elements
5. Add your own insights and improvements
6. Use the 'reveal' tool to share your synthesized outputs

## Guidelines
- Build on what works, improve what doesn't
- Explain your synthesis reasoning in your main .md file
- Be constructive and collaborative
- Focus on creating the best possible outcome

Begin your synthesis now.
"""

        return prompt

    def _get_container_tools(self, container: AgentContainer) -> list[dict]:
        """Get the tools available to an agent in a container."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write content to a file in your workspace",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of the file to write"},
                            "content": {"type": "string", "description": "Content to write to the file"},
                            "description": {"type": "string", "description": "Brief description of the file"}
                        },
                        "required": ["filename", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file from your workspace",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of the file to read"}
                        },
                        "required": ["filename"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List all files in your workspace",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reveal",
                    "description": "Reveal/share a file from your workspace for synthesis with other agents",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of the file to reveal"},
                            "description": {"type": "string", "description": "Description of what this file contributes"}
                        },
                        "required": ["filename"]
                    }
                }
            }
        ]

    async def _execute_container_tool(
        self,
        container: AgentContainer,
        tool_name: str,
        tool_args: dict
    ) -> dict:
        """Execute a tool within a container."""
        workspace = container.container_path / "workspace"

        if tool_name == "write_file":
            filename = tool_args.get("filename", "untitled.txt")
            content = tool_args.get("content", "")
            description = tool_args.get("description")

            file_path = workspace / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

            container.log(
                "INFO",
                f"Wrote file: {filename} ({len(content)} chars)",
                description=description,
                tool_name=tool_name,
                tool_args=tool_args
            )

            return {"success": True, "filename": filename, "size": len(content)}

        elif tool_name == "read_file":
            filename = tool_args.get("filename", "")
            file_path = workspace / filename

            if not file_path.exists():
                return {"success": False, "error": f"File not found: {filename}"}

            try:
                content = file_path.read_text()
                container.log(
                    "INFO",
                    f"Read file: {filename}",
                    description=f"Retrieved {len(content)} characters",
                    tool_name=tool_name
                )
                return {"success": True, "content": content}
            except Exception as e:
                return {"success": False, "error": str(e)}

        elif tool_name == "list_files":
            files = []
            for path in workspace.rglob("*"):
                if path.is_file():
                    rel_path = path.relative_to(workspace)
                    files.append({
                        "path": str(rel_path),
                        "size": path.stat().st_size
                    })

            container.log(
                "INFO",
                f"Listed {len(files)} files",
                description="Retrieved workspace file listing",
                tool_name=tool_name
            )
            return {"success": True, "files": files}

        elif tool_name == "reveal":
            filename = tool_args.get("filename", "")
            description = tool_args.get("description")

            file_path = workspace / filename
            if not file_path.exists():
                return {"success": False, "error": f"File not found: {filename}"}

            try:
                content = file_path.read_text()
                file_type = filename.split(".")[-1] if "." in filename else "txt"

                container.reveal_file(
                    filename=filename,
                    content=content,
                    file_type=file_type,
                    agent_id=container.id,
                    description=description
                )

                return {"success": True, "revealed": filename, "description": description}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    async def _run_agent_in_container(
        self,
        tournament: Tournament,
        container: AgentContainer,
        input_files: list[RevealedFile],
        is_initial_round: bool
    ) -> bool:
        """Run an agent within its container."""
        container.status = ContainerStatus.RUNNING
        container.log("INFO", "Agent starting execution",
                     description="Beginning autonomous work on assigned task")

        try:
            prompt = self._build_agent_prompt(tournament, container, input_files, is_initial_round)
            tools = self._get_container_tools(container)

            messages = [{"role": "user", "content": prompt}]
            max_turns = 20

            for turn in range(max_turns):
                response = await self.client.chat(
                    messages=messages,
                    tools=tools,
                    temperature=0.7,
                    max_tokens=4096,
                    model=tournament.model
                )

                if response.tool_calls:
                    # Process tool calls
                    assistant_msg = {"role": "assistant", "content": response.content or "", "tool_calls": []}

                    for tool_call in response.tool_calls:
                        container.log(
                            "INFO",
                            f"Tool call: {tool_call.name}",
                            description=f"Executing {tool_call.name} with provided arguments",
                            tool_name=tool_call.name,
                            tool_args=tool_call.arguments
                        )

                        result = await self._execute_container_tool(
                            container, tool_call.name, tool_call.arguments
                        )

                        assistant_msg["tool_calls"].append({
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.name,
                                "arguments": json.dumps(tool_call.arguments)
                            }
                        })

                        messages.append(assistant_msg)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result)
                        })
                        assistant_msg = {"role": "assistant", "content": "", "tool_calls": []}

                elif response.content:
                    # Agent finished with a message
                    container.output_md = response.content
                    container.log(
                        "INFO",
                        "Agent completed with final output",
                        description="Generated final response and revealed files"
                    )
                    break
                else:
                    break

            container.status = ContainerStatus.COMPLETED
            container.completed_at = datetime.now().isoformat()
            container.log("INFO", "Container execution completed",
                         description=f"Revealed {len(container.revealed_files)} files")
            return True

        except Exception as e:
            container.status = ContainerStatus.FAILED
            container.error = str(e)
            container.completed_at = datetime.now().isoformat()
            container.log("ERROR", f"Container execution failed: {e}",
                         description="Agent encountered an error during execution")
            return False

    async def run_tournament(self, tournament_id: str) -> Tournament:
        """Run a complete tournament with all synthesis rounds."""
        tournament = self.tournaments.get(tournament_id)
        if not tournament:
            raise ValueError(f"Tournament not found: {tournament_id}")

        tournament.status = TournamentStatus.RUNNING
        tournament.started_at = datetime.now().isoformat()
        tournament.log("INFO", "Tournament started",
                      description=f"Beginning {len(tournament.stages)} rounds with stages {tournament.stages}")
        self._save_tournaments()

        try:
            current_files: list[RevealedFile] = []

            for round_idx, agent_count in enumerate(tournament.stages):
                round_number = round_idx + 1
                is_initial_round = round_idx == 0

                tournament.log(
                    "INFO",
                    f"Starting round {round_number} with {agent_count} agents",
                    description=f"{'Initial brainstorming' if is_initial_round else 'Synthesis'} round"
                )

                # Create synthesis round
                synthesis_round = SynthesisRound(
                    round_number=round_number,
                    agent_count=agent_count,
                    input_files=current_files.copy()
                )
                synthesis_round.status = "running"
                synthesis_round.started_at = datetime.now().isoformat()
                tournament.synthesis_rounds.append(synthesis_round)

                # Create containers for this round
                containers = []
                for i in range(agent_count):
                    container = self._create_container(tournament, round_number, i)
                    containers.append(container)
                    synthesis_round.containers.append(container)

                # Run agents in parallel (respecting max_parallel)
                semaphore = asyncio.Semaphore(self.max_parallel)

                async def run_with_semaphore(container: AgentContainer):
                    async with semaphore:
                        return await asyncio.wait_for(
                            self._run_agent_in_container(
                                tournament, container, current_files, is_initial_round
                            ),
                            timeout=self.timeout_per_agent
                        )

                tasks = [run_with_semaphore(c) for c in containers]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Collect revealed files for next round
                current_files = []
                for container in containers:
                    current_files.extend(container.revealed_files)

                synthesis_round.status = "completed"
                synthesis_round.completed_at = datetime.now().isoformat()

                tournament.log(
                    "INFO",
                    f"Round {round_number} completed",
                    description=f"Collected {len(current_files)} files for next round"
                )

                self._save_tournaments()

            # Store final files
            tournament.final_files = current_files

            # Copy final files to output directory
            output_dir = tournament.base_path / "final_output"
            output_dir.mkdir(exist_ok=True)

            for revealed_file in current_files:
                output_path = output_dir / revealed_file.filename
                output_path.write_text(revealed_file.content)

            tournament.status = TournamentStatus.COMPLETED
            tournament.completed_at = datetime.now().isoformat()
            tournament.log(
                "INFO",
                "Tournament completed successfully",
                description=f"Generated {len(current_files)} final files"
            )

        except Exception as e:
            tournament.status = TournamentStatus.FAILED
            tournament.error = str(e)
            tournament.completed_at = datetime.now().isoformat()
            tournament.log("ERROR", f"Tournament failed: {e}",
                          description="Tournament encountered a fatal error")

        self._save_tournaments()
        return tournament

    async def call_subagent(
        self,
        task: str,
        model: Optional[str] = None,
        timeout: int = 300
    ) -> dict:
        """
        Call a single subagent with a task and get results.
        Creates a temporary container for the agent.
        """
        # Create a mini-tournament for single agent
        container_id = f"subagent_{uuid.uuid4().hex[:8]}"
        container_path = self.base_path / "subagents" / container_id
        container_path.mkdir(parents=True, exist_ok=True)

        container = AgentContainer(
            id=container_id,
            tournament_id="subagent",
            agent_model=model or self.model,
            round_number=0,
            container_path=container_path
        )

        container.log("INFO", "Subagent initialized",
                     description=f"Task: {task[:100]}...")

        # Build simple prompt
        prompt = f"""You are an autonomous agent. Complete the following task:

{task}

## Available Tools
- write_file: Write content to a file
- read_file: Read a file
- list_files: List files
- reveal: Share a file as output

When finished, use 'reveal' to share your output files.
"""

        try:
            # Run the agent
            await asyncio.wait_for(
                self._run_agent_in_container(
                    Tournament(
                        id="subagent",
                        topic=task,
                        stages=[1],
                        debate_rounds=0,
                        model=model or self.model,
                        base_path=container_path.parent
                    ),
                    container,
                    [],
                    True
                ),
                timeout=timeout
            )

            return {
                "success": True,
                "container_id": container_id,
                "revealed_files": [
                    {
                        "filename": f.filename,
                        "content": f.content,
                        "file_type": f.file_type,
                        "description": f.description
                    }
                    for f in container.revealed_files
                ],
                "output": container.output_md,
                "logs": [log.to_dict() for log in container.logs]
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Subagent timed out",
                "container_id": container_id,
                "logs": [log.to_dict() for log in container.logs]
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "container_id": container_id,
                "logs": [log.to_dict() for log in container.logs]
            }

    def get_tournament(self, tournament_id: str) -> Optional[Tournament]:
        """Get a tournament by ID."""
        return self.tournaments.get(tournament_id)

    def list_tournaments(self) -> list[dict]:
        """List all tournaments."""
        return [t.to_dict() for t in self.tournaments.values()]

    def get_container(self, tournament_id: str, container_id: str) -> Optional[AgentContainer]:
        """Get a specific container."""
        tournament = self.tournaments.get(tournament_id)
        if tournament:
            for container in tournament.get_all_containers():
                if container.id == container_id:
                    return container
        return None

    def get_container_logs(self, tournament_id: str, container_id: str) -> list[dict]:
        """Get logs for a specific container."""
        container = self.get_container(tournament_id, container_id)
        if container:
            return [log.to_dict() for log in container.logs]
        return []

    def get_container_files(self, tournament_id: str, container_id: str) -> list[dict]:
        """Get files from a specific container."""
        container = self.get_container(tournament_id, container_id)
        if container:
            return container.get_files()
        return []
