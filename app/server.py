"""
FastAPI Server for Curiosity Agent Control Interface.
"""

import asyncio
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import json

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import CuriosityAgent, TournamentStatus
from agent.chat_session import ChatSessionManager


# Global agent instance
agent: Optional[CuriosityAgent] = None
agent_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize agent on startup."""
    global agent
    agent = CuriosityAgent()
    yield
    # Cleanup
    if agent:
        agent.stop()


app = FastAPI(
    title="Curiosity Agent",
    description="Control interface for the autonomous self-improving agent",
    lifespan=lifespan
)

# Serve static files
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# ==================== API Models ====================

class StartRequest(BaseModel):
    max_iterations: Optional[int] = None


class AnswerRequest(BaseModel):
    question_id: str
    answer: str
    answer_text: Optional[str] = None


class GoalUpdate(BaseModel):
    content: str


class TodoRequest(BaseModel):
    action: str  # add, update, delete, add_subtask
    item_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    parent_id: Optional[str] = None


class RestartRequest(BaseModel):
    prompt: Optional[str] = None
    keep_context: bool = False


class QueuePromptRequest(BaseModel):
    prompt: str
    priority: str = "normal"  # "normal" or "high"


class TournamentCreateRequest(BaseModel):
    topic: str
    stages: Optional[List[int]] = None
    debate_rounds: int = 2
    auto_start: bool = True


class SubagentRequest(BaseModel):
    task: str
    model: Optional[str] = None
    timeout: int = 300


# ==================== API Routes ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text())
    return HTMLResponse(content="<h1>Curiosity Agent</h1><p>Template not found.</p>")


@app.get("/api/status")
async def get_status():
    """Get current agent status."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    return agent.get_status()


@app.post("/api/start")
async def start_agent(request: StartRequest):
    """Start the agent loop."""
    global agent_task
    
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    if agent_task and not agent_task.done():
        return {"status": "already_running"}
    
    agent_task = asyncio.create_task(agent.run(max_iterations=request.max_iterations))
    return {"status": "started"}


@app.post("/api/stop")
async def stop_agent():
    """Stop the agent loop."""
    if agent:
        agent.stop()
    return {"status": "stopped"}


@app.post("/api/pause")
async def pause_agent():
    """Pause the agent loop."""
    if agent:
        agent.pause()
    return {"status": "paused"}


@app.post("/api/resume")
async def resume_agent():
    """Resume the agent loop."""
    if agent:
        agent.resume()
    return {"status": "resumed"}


@app.post("/api/restart")
async def restart_agent(request: RestartRequest):
    """Restart the agent with optional prompt."""
    global agent_task

    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    # Stop current task if running
    if agent_task and not agent_task.done():
        agent.stop()
        # Give it a moment to stop
        await asyncio.sleep(0.5)

    # Perform restart
    agent.restart(prompt=request.prompt, keep_context=request.keep_context)

    # Start new loop
    agent_task = asyncio.create_task(agent.run())

    return {"status": "restarted", "prompt_injected": bool(request.prompt)}


# ==================== Prompt Queue ====================

@app.post("/api/prompts/queue")
async def queue_prompt(request: QueuePromptRequest):
    """Queue a prompt for the next loop iteration."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    prompt_id = agent.queue_prompt(request.prompt, request.priority)
    return {"status": "queued", "prompt_id": prompt_id}


@app.get("/api/prompts/queue")
async def get_prompt_queue():
    """Get all queued prompts."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    return {"prompts": agent.get_queued_prompts()}


@app.delete("/api/prompts/queue/{prompt_id}")
async def remove_queued_prompt(prompt_id: str):
    """Remove a prompt from the queue."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    success = agent.remove_queued_prompt(prompt_id)
    if not success:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"status": "removed"}


@app.delete("/api/prompts/queue")
async def clear_prompt_queue():
    """Clear all queued prompts."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    agent.clear_prompt_queue()
    return {"status": "cleared"}


@app.post("/api/compact")
async def force_compact():
    """Force context compaction."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    summary = await agent.context.compact(
        agent.client,
        archive_path=agent.config["journal"]["freeform_path"]
    )
    return {"status": "compacted", "summary_length": len(summary)}


# ==================== Questions ====================

@app.get("/api/questions")
async def get_questions():
    """Get all questions."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    pending = agent.questions.get_pending()
    answered = agent.questions.get_answered()
    
    return {
        "pending": [
            {
                "id": q.id,
                "question_text": q.question_text,
                "question_type": q.question_type,
                "options": q.options,
                "priority": q.priority,
                "context": q.context,
                "created_at": q.created_at
            }
            for q in pending
        ],
        "answered": [
            {
                "id": q.id,
                "question_text": q.question_text,
                "answer": q.answer,
                "answer_text": q.answer_text,
                "answered_at": q.answered_at
            }
            for q in answered
        ]
    }


@app.post("/api/questions/answer")
async def answer_question(request: AnswerRequest):
    """Answer a question."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    success = agent.questions.answer(
        request.question_id,
        request.answer,
        request.answer_text
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Question not found")
    
    return {"status": "answered"}


# ==================== Journal ====================

@app.get("/api/journal")
async def get_journal(
    query: Optional[str] = None,
    entry_type: Optional[str] = None,
    limit: int = 20
):
    """Search/list journal entries."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    entries = agent.journal.read(query=query, entry_type=entry_type, limit=limit)
    stats = agent.journal.get_stats()
    
    return {"entries": entries, "stats": stats}


@app.get("/api/journal/{entry_id}")
async def get_journal_entry(entry_id: str):
    """Get a specific journal entry."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    entry = agent.journal.get_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return entry


# ==================== Goal ====================

@app.get("/api/goal")
async def get_goal():
    """Get current goal."""
    goal_path = Path("config/goal.md")
    if goal_path.exists():
        return {"content": goal_path.read_text()}
    return {"content": ""}


@app.post("/api/goal")
async def update_goal(request: GoalUpdate):
    """Update the goal."""
    goal_path = Path("config/goal.md")
    goal_path.write_text(request.content)
    
    # Reload agent's goal
    if agent:
        agent.goal = request.content
        agent._build_system_prompt()
    
    return {"status": "updated"}


# ==================== Tools ====================

@app.get("/api/tools")
async def get_tools():
    """List all tools."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    tools = []
    for name in agent.tools.list_tools():
        tool = agent.tools.get(name)
        tools.append({
            "name": tool.name,
            "description": tool.description,
            "category": tool.category,
            "protected": tool.protected
        })
    
    return {"tools": tools}


# ==================== Logs ====================

@app.get("/api/logs")
async def get_logs(
    lines: int = 200,
    level: Optional[str] = None
):
    """Fetch agent logs."""
    log_path = Path("logs/agent.log")

    if not log_path.exists():
        return {"logs": [], "total_lines": 0, "returned_lines": 0}

    try:
        with open(log_path, "r") as f:
            all_lines = f.readlines()

        # Filter by level if specified
        if level:
            all_lines = [line for line in all_lines if f"[{level.upper()}]" in line]

        # Get last N lines
        recent_lines = all_lines[-lines:]

        return {
            "logs": [line.strip() for line in recent_lines],
            "total_lines": len(all_lines),
            "returned_lines": len(recent_lines)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Todos ====================

@app.get("/api/todos")
async def get_todos():
    """Get the todo list."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    items = agent.todos.list_all()
    return {
        "items": items,
        "stats": {
            "total": len(items),
            "in_progress": len([i for i in items if i.get("status") == "in_progress"]),
            "pending": len([i for i in items if i.get("status") == "pending"]),
            "done": len([i for i in items if i.get("status") == "done"])
        }
    }


@app.post("/api/todos")
async def manage_todo(request: TodoRequest):
    """Create, update, or delete todos."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    if request.action == "add":
        item_id = agent.todos.add(
            title=request.title or "Untitled",
            description=request.description or "",
            priority=request.priority or "medium"
        )
        return {"success": True, "item_id": item_id}

    elif request.action == "update":
        if not request.item_id:
            raise HTTPException(status_code=400, detail="item_id required")
        success = agent.todos.update(
            item_id=request.item_id,
            title=request.title,
            description=request.description,
            status=request.status,
            priority=request.priority
        )
        return {"success": success}

    elif request.action == "delete":
        if not request.item_id:
            raise HTTPException(status_code=400, detail="item_id required")
        success = agent.todos.delete(request.item_id)
        return {"success": success}

    elif request.action == "add_subtask":
        if not request.parent_id:
            raise HTTPException(status_code=400, detail="parent_id required")
        subtask_id = agent.todos.add_subtask(
            parent_id=request.parent_id,
            title=request.title or "Subtask",
            description=request.description or ""
        )
        return {"success": subtask_id is not None, "subtask_id": subtask_id}

    raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")


# ==================== Tournament ====================

@app.get("/api/tournaments")
async def list_tournaments():
    """List all tournaments."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    tournaments = agent.tournament_engine.list_tournaments()
    return {"tournaments": tournaments, "count": len(tournaments)}


@app.post("/api/tournaments")
async def create_tournament(request: TournamentCreateRequest):
    """Create a new tournament."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    tournament = agent.tournament_engine.create_tournament(
        topic=request.topic,
        stages=request.stages,
        debate_rounds=request.debate_rounds
    )

    if request.auto_start:
        asyncio.create_task(agent.tournament_engine.run_tournament(tournament.id))

    return {
        "success": True,
        "tournament_id": tournament.id,
        "topic": request.topic,
        "stages": tournament.stages,
        "status": tournament.status.value,
        "auto_started": request.auto_start
    }


@app.get("/api/tournaments/{tournament_id}")
async def get_tournament(tournament_id: str):
    """Get tournament details."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    tournament = agent.tournament_engine.get_tournament(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    return tournament.to_dict()


@app.post("/api/tournaments/{tournament_id}/start")
async def start_tournament(tournament_id: str):
    """Start a tournament."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    tournament = agent.tournament_engine.get_tournament(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if tournament.status != TournamentStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Tournament already {tournament.status.value}"
        )

    asyncio.create_task(agent.tournament_engine.run_tournament(tournament_id))
    return {"status": "started", "tournament_id": tournament_id}


@app.get("/api/tournaments/{tournament_id}/containers")
async def get_tournament_containers(tournament_id: str):
    """Get all containers for a tournament."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    tournament = agent.tournament_engine.get_tournament(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    containers = tournament.get_all_containers()
    return {
        "containers": [c.to_dict() for c in containers],
        "count": len(containers)
    }


@app.get("/api/tournaments/{tournament_id}/containers/{container_id}")
async def get_container(tournament_id: str, container_id: str):
    """Get a specific container."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    container = agent.tournament_engine.get_container(tournament_id, container_id)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")

    return container.to_dict()


@app.get("/api/tournaments/{tournament_id}/containers/{container_id}/logs")
async def get_container_logs(tournament_id: str, container_id: str, limit: int = 100):
    """Get logs for a container."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    logs = agent.tournament_engine.get_container_logs(tournament_id, container_id)
    return {"logs": logs[-limit:], "total": len(logs)}


@app.get("/api/tournaments/{tournament_id}/containers/{container_id}/files")
async def get_container_files(tournament_id: str, container_id: str):
    """Get files from a container."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    files = agent.tournament_engine.get_container_files(tournament_id, container_id)
    return {"files": files, "count": len(files)}


@app.get("/api/tournaments/{tournament_id}/results")
async def get_tournament_results(tournament_id: str):
    """Get tournament results (final files)."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    tournament = agent.tournament_engine.get_tournament(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    return {
        "status": tournament.status.value,
        "final_files": [
            {
                "filename": f.filename,
                "content": f.content,
                "file_type": f.file_type,
                "description": f.description,
                "agent_id": f.agent_id
            }
            for f in tournament.final_files
        ],
        "count": len(tournament.final_files)
    }


# ==================== Subagent ====================

@app.post("/api/subagent")
async def call_subagent(request: SubagentRequest):
    """Call a subagent to perform a task."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    result = await agent.tournament_engine.call_subagent(
        task=request.task,
        model=request.model,
        timeout=request.timeout
    )

    return result


# ==================== Enhanced Logs ====================

@app.get("/api/logs/enhanced")
async def get_enhanced_logs(
    limit: int = 100,
    offset: int = 0,
    category: Optional[str] = None,
    level: Optional[str] = None
):
    """Get enhanced logs with descriptions."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    entries = agent.enhanced_logger.get_entries(
        limit=limit,
        offset=offset,
        category=category,
        level=level
    )

    return {"logs": entries, "count": len(entries)}


@app.get("/api/logs/tools")
async def get_tool_logs(limit: int = 50):
    """Get tool execution history."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    entries = agent.enhanced_logger.get_tool_history(limit=limit)
    return {"logs": entries, "count": len(entries)}


# ==================== File Preview ====================

@app.get("/api/files/main")
async def get_main_agent_files():
    """Get files from main agent's sandbox."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    files = agent.log_manager.get_main_agent_files(
        sandbox_path=agent.config.get("sandbox", {}).get("root", "agent_sandbox")
    )

    return {"files": files, "count": len(files)}


@app.get("/api/files/main/{file_path:path}")
async def get_main_agent_file(file_path: str):
    """Get a specific file from main agent's sandbox."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    sandbox_root = Path(agent.config.get("sandbox", {}).get("root", "agent_sandbox"))
    full_path = sandbox_root / file_path

    # Security check - ensure path is within sandbox
    try:
        full_path.resolve().relative_to(sandbox_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = full_path.read_text()
        return {
            "path": file_path,
            "content": content,
            "size": full_path.stat().st_size,
            "extension": full_path.suffix
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Container Logs via Log Manager ====================

@app.get("/api/container-logs")
async def list_container_logs():
    """List all containers that have logs."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    container_ids = agent.log_manager.get_all_container_ids()
    return {"container_ids": container_ids, "count": len(container_ids)}


@app.get("/api/container-logs/{tournament_id}/{container_id}")
async def get_container_logs_by_id(tournament_id: str, container_id: str, limit: int = 100):
    """Get logs for a specific container from log manager."""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    logs = agent.log_manager.get_container_logs(tournament_id, container_id, limit)
    return {"logs": logs, "count": len(logs)}


# ==================== WebSocket for real-time updates ====================

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time status updates."""
    await manager.connect(websocket)

    try:
        while True:
            # Send status updates every second
            if agent:
                status = agent.get_status()
                todos = agent.todos.list_all()
                queued_prompts = agent.get_queued_prompts()

                # Get active tournaments
                tournaments = agent.tournament_engine.list_tournaments()
                active_tournaments = [
                    t for t in tournaments
                    if t.get("status") in ["running", "synthesis"]
                ]

                # Get recent enhanced logs
                recent_logs = agent.enhanced_logger.get_entries(limit=10)

                await websocket.send_json({
                    "type": "status",
                    "data": status,
                    "todos": todos,
                    "queued_prompts": queued_prompts,
                    "tournaments": {
                        "active": active_tournaments,
                        "total": len(tournaments)
                    },
                    "recent_logs": recent_logs
                })

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ==================== Run ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
