# Curiosity Agent

An autonomous, self-improving AI agent that runs continuously via OpenRouter, exploring problems, building tools, and improving its own workflows.

## Features

- **Modular Agent Architecture**: BaseAgent provides core functionality inherited by all specialized agents
- **Multi-Agent Tournaments**: Spawn parallel agents that debate and synthesize solutions
- **Sandboxed Code Execution**: Run Python code safely in isolated workspaces
- **Agent-Controlled Completion**: Agents signal when they're done rather than relying on timeouts
- **Dynamic Tool Creation**: Agent can create, modify, and delete its own tools
- **Adaptive Context Management**: Automatic compaction when context fills up
- **Persistent Journal**: Structured + freeform knowledge base for learnings
- **Async User Interaction**: Non-blocking question panel for human input
- **Web Dashboard**: Real-time monitoring and control interface

## Quick Start

### 1. Install Dependencies

```bash
cd curiosity-agent
pip install -r requirements.txt
```

### 2. Set Your API Key

```bash
export OPENROUTER_API_KEY="your-key-here"
```

Get a free key at [openrouter.ai](https://openrouter.ai)

### 3. Run the Agent

```bash
# Start the web interface
python -m app.server

# Or run the agent directly
python -m agent.loop
```

### 4. Open the Dashboard

Navigate to `http://127.0.0.1:8000` in your browser.

## Architecture

Curiosity Agent uses a modular architecture centered around `BaseAgent`, an abstract base class that provides core functionality for all agent types:

### Agent Types

- **MainAgent** (`agent/main_agent.py`) - The continuous autonomous loop that runs indefinitely, working toward goals with access to meta-tools (journal, questions, tournaments)
- **TournamentAgent** (`agent/tournament_agent.py`) - Isolated agents that run in tournaments with dedicated workspaces and can share files via the `reveal` tool
- **SubAgent** (`agent/sub_agent.py`) - One-off task executors with optional web search or code execution capabilities
  - **WebSearchAgent** - SubAgent with internet search enabled
  - **CodeExecutionAgent** - SubAgent with sandboxed Python execution

### BaseAgent Features

All agents inherit from `BaseAgent` and include:

- **Automatic Context Management** - Auto-compaction when context reaches threshold
- **Tool Registration System** - Modular tool registration and execution
- **Agent-Controlled Completion** - Agents signal completion via `complete_task` tool rather than relying on timeouts
- **Built-in Logging** - Structured logging for each agent instance
- **Workspace Isolation** - Each agent operates in its own workspace directory

## Project Structure

```
curiosity-agent/
├── agent/                    # Core agent logic
│   ├── base_agent.py         # Abstract base class for all agents
│   ├── main_agent.py         # Main autonomous loop agent
│   ├── tournament_agent.py   # Tournament participant agent
│   ├── sub_agent.py          # One-off task agent (with variants)
│   ├── tournament_engine.py  # Tournament execution manager
│   ├── loop.py               # Agent loop runner
│   ├── context_manager.py    # Context tracking & compaction
│   ├── tool_registry.py      # Tool loading & execution (MainAgent)
│   ├── questions_manager.py  # Async user Q&A
│   ├── journal_manager.py    # Knowledge base
│   └── openrouter_client.py  # LLM API client
│
├── app/                      # Web interface
│   ├── server.py             # FastAPI backend
│   ├── templates/            # HTML templates
│   └── static/               # CSS/JS assets
│
├── tools/                    # Tool definitions (for MainAgent)
│   ├── core/                 # Protected core tools
│   ├── meta/                 # Self-modification tools
│   ├── output/               # Artifact creation
│   └── custom/               # Agent-created tools
│
├── skills/                   # Skill library (prompts, workflows)
├── journal/                  # Persistent knowledge base
│   ├── structured/           # JSON entries by type
│   └── freeform/             # Markdown exploration notes
│
├── workspace/                # Agent's working directory
├── questions/                # Pending user questions
├── config/                   # Configuration files
│   ├── settings.yaml         # Main config
│   └── goal.md               # Current mission
└── logs/                     # Execution logs
```

## Configuration

Edit `config/settings.yaml`:

```yaml
openrouter:
  models:
    main: "x-ai/grok-4.1-fast"      # Main agent model
    summarizer: "x-ai/grok-4.1-fast" # For context compaction
    tournament: "x-ai/grok-4.1-fast" # For sub-agents

context:
  max_tokens: 128000
  compaction_threshold: 0.85  # Auto-compact at 85%

agent:
  enable_code_execution: true   # Enable run_python tool
  code_timeout: 30              # Python execution timeout (seconds)
  max_turns: null               # Max agent turns (null = unlimited)
  timeout: null                 # Overall timeout (null = unlimited)

tournament:
  default_stages: [4, 3, 2]   # Agents per stage
  default_debate_rounds: 2
```

## Setting the Goal

Edit `config/goal.md` to change what the agent works on:

```markdown
# Current Mission

Build useful tools for code analysis and refactoring.

## Priorities
1. Create a Python linter tool
2. Experiment with tournament configurations
3. Document findings in the journal
```

Or update via the web dashboard's Goal Manager.

## Available Tools

Tools are categorized by which agent type has access to them:

### Base Tools (All Agents)
- `complete_task` - Signal task completion with reason, summary, and output
- `manage_context` - Compact context, adjust threshold, or check status

### MainAgent Tools
- **File Operations**: `read_file`, `write_file`, `list_directory`
- **Code Execution**: `run_code` - Execute Python/Bash/JavaScript (via tool registry)
- **Web Access**: `internet_search` (DuckDuckGo), `fetch_url` (Jina Reader)
- **Meta Tools**:
  - `create_tool`, `delete_tool` - Modify custom tools
  - `write_journal`, `read_journal` - Knowledge base management
  - `ask_user`, `manage_questions` - Async user interaction
  - `manage_todos` - Todo list management
- **Output Tools**: `create_html`, `create_markdown`, `create_latex`, `create_python`

### TournamentAgent Tools
- `read_file`, `write_file`, `list_files` - File operations in workspace
- `reveal` - Share files with other tournament agents for synthesis
- `run_python` - Sandboxed Python execution (always enabled)
- `complete_task` - Signal completion

### SubAgent Tools
- `read_file`, `write_file`, `list_files` - File operations in workspace
- `output` - Mark files as outputs
- `run_python` - Sandboxed Python execution (optional, via CodeExecutionAgent)
- `internet_search` - Web search (optional, via WebSearchAgent)
- `complete_task` - Signal completion

### The run_python Tool

**Available to**: TournamentAgent (always), CodeExecutionAgent (always), SubAgent (when enabled)

Executes Python code in a sandboxed environment:

```python
run_python(
    code="print('Hello, World!')",
    save_as="hello.py"  # Optional: save code to file
)
```

**Features**:
- Runs in isolated workspace directory
- Configurable timeout (default 30s)
- Captures stdout and stderr
- Can persist code to files
- All created files remain in workspace

**Returns**:
```json
{
    "success": true,
    "exit_code": 0,
    "stdout": "Hello, World!\n",
    "stderr": "",
    "saved_to": "workspace/hello.py"
}
```

## Tournament System

For complex problems, the MainAgent can spawn multi-agent tournaments using the `TournamentEngine`:

```python
create_tournament(
    prompt="Design a CLI tool for managing TODO lists",
    stages=[4, 3, 2],      # 4 agents → 3 agents → 2 agents
    debate_rounds=2         # Each stage has 2 rounds of critique/response
)
```

### Tournament Flow

1. **Stage 1**: N agents (`TournamentAgent` instances) work independently in isolated workspaces
2. **Debate Round(s)**: Agents critique each other's work, then respond/refine
3. **Synthesis**: Agents `reveal` files to share with the next stage
4. **Stage 2+**: Fewer agents synthesize from previous stages + debate outputs
5. **Final Synthesis**: Last stage produces the final solution

### Agent-Controlled Completion

Unlike the old timeout-based system, agents now signal completion themselves:

```python
complete_task(
    reason="finished",  # or "stuck", "blocked", "error"
    summary="Built a CLI tool with add/list/complete commands",
    output="cli_tool.py"  # Optional file reference
)
```

**Benefits**:
- Agents work at their own pace
- Clear success/failure signals
- Better quality outputs (not cut off mid-thought)
- Timeouts only act as safety limits

### Workspace Isolation

Each `TournamentAgent` runs in an isolated workspace:

```
tournaments/tournament_<id>/
├── stage_<N>_agent_<M>/
│   ├── workspace/        # Agent's working directory
│   ├── revealed/         # Files shared via reveal() tool
│   ├── logs/             # Agent execution logs
│   └── context_state.json
```

## Questions Panel

The agent can ask you questions without blocking:

```python
ask_user(
    question_text="Which API design do you prefer?",
    question_type="multiple_choice",
    options=["REST", "GraphQL", "gRPC"],
    priority="high",
    context="I'm designing a new tool..."
)
```

Answer via the web dashboard. The agent continues working and processes your answer when ready.

## Journal System

The agent maintains a persistent knowledge base:

**Structured entries** (JSON):
- `ideas` - Proposed improvements
- `empirical_results` - Experiment outcomes
- `tool_specs` - Created tool documentation
- `failed_attempts` - What didn't work and why

**Freeform entries** (Markdown):
- Date-prefixed exploration notes
- Semantic search supported

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Current agent status |
| `/api/start` | POST | Start agent loop |
| `/api/stop` | POST | Stop agent loop |
| `/api/pause` | POST | Pause agent |
| `/api/resume` | POST | Resume agent |
| `/api/compact` | POST | Force context compaction |
| `/api/questions` | GET | List all questions |
| `/api/questions/answer` | POST | Answer a question |
| `/api/journal` | GET | Search journal |
| `/api/goal` | GET/POST | View/update goal |
| `/api/tools` | GET | List all tools |
| `/ws` | WebSocket | Real-time status updates |

## Free Models on OpenRouter

These models support tool calling and have free tiers:

| Model | Context | Notes |
|-------|---------|-------|
| `x-ai/grok-4.1-fast` | 128k | Currently configured |
| `meta-llama/llama-4-maverick:free` | 128k | Recommended |
| `meta-llama/llama-4-scout:free` | 512k | Huge context |
| `mistralai/mistral-small-3.1-24b-instruct:free` | 96k | Fast |
| `mistralai/devstral-small:free` | 128k | Good for code |

## Development

### Running Tests

```bash
pytest tests/
```

### Using Different Agent Types

```python
from agent import MainAgent, SubAgent, WebSearchAgent, CodeExecutionAgent, TournamentEngine
from agent.base_agent import AgentConfig

# Create a one-off task agent
config = AgentConfig(
    model="x-ai/grok-4.1-fast",
    enable_code_execution=True,
    max_turns=10
)
agent = CodeExecutionAgent(config=config)
await agent.run("Analyze this dataset and create visualizations")

# Create a web search agent
search_agent = WebSearchAgent(config=config)
await search_agent.run("Research the latest in AI safety")

# Run a tournament (from MainAgent)
from agent.tournament_engine import TournamentEngine
engine = TournamentEngine(config)
result = await engine.run_tournament(
    prompt="Design a REST API for a task manager",
    stages=[3, 2],
    debate_rounds=1
)
```

### Adding a Custom Tool

Create `tools/custom/my_tool.json`:
```json
{
    "name": "my_tool",
    "description": "Does something useful",
    "parameters": {
        "type": "object",
        "properties": {
            "input": {"type": "string"}
        },
        "required": ["input"]
    }
}
```

Create `tools/custom/my_tool.py`:
```python
async def execute(params: dict) -> str:
    return f"Processed: {params['input']}"
```

The tool will be loaded automatically on next restart.

## Troubleshooting

**Agent not responding?**
- Check `logs/agent.log` for errors
- Verify `OPENROUTER_API_KEY` is set
- Check OpenRouter status at status.openrouter.ai

**Context filling too fast?**
- Lower `compaction_threshold` in settings
- Agent can also adjust this itself

**Tools not working?**
- Ensure `duckduckgo-search` is installed for internet search
- Check tool permissions in `tool_registry.py`

## License

MIT

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Submit a PR

---

Built with curiosity 🔍
