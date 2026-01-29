# Curiosity Agent

An autonomous, self-improving AI agent that runs continuously via OpenRouter, exploring problems, building tools, and improving its own workflows.

## Features

- **Multi-Agent Tournaments**: Spawn parallel agents that debate and synthesize solutions
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

## Project Structure

```
curiosity-agent/
├── agent/                    # Core agent logic
│   ├── loop.py               # Main autonomous loop
│   ├── context_manager.py    # Context tracking & compaction
│   ├── tool_registry.py      # Tool loading & execution
│   ├── questions_manager.py  # Async user Q&A
│   ├── journal_manager.py    # Knowledge base
│   └── openrouter_client.py  # LLM API client
│
├── app/                      # Web interface
│   ├── server.py             # FastAPI backend
│   ├── templates/            # HTML templates
│   └── static/               # CSS/JS assets
│
├── tools/                    # Tool definitions
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

### Core Tools (Protected)
- `read_file`, `write_file`, `list_directory` - File operations
- `run_code` - Execute Python/Bash/JavaScript
- `internet_search` - Web search via DuckDuckGo
- `fetch_url` - Fetch URL content (via Jina Reader)

### Meta Tools (Self-Modification)
- `manage_context` - Compact context, adjust threshold
- `create_tool` - Create new custom tools
- `delete_tool` - Remove custom tools
- `write_journal` - Log ideas, experiments, failures
- `read_journal` - Search knowledge base
- `ask_user` - Post questions (non-blocking)
- `manage_questions` - View/delete questions

### Output Tools
- `create_html` - HTML artifacts with Tailwind
- `create_markdown` - Markdown documents
- `create_latex` - LaTeX papers with citations
- `create_python` - Python scripts

## Tournament System

For complex problems, the agent can spawn tournaments:

```python
create_tournament(
    prompt="Design a CLI tool for managing TODO lists",
    stages=[4, 3, 2],      # 4 agents → 3 agents → 2 agents
    debate_rounds=2         # Each stage has 2 rounds of critique/response
)
```

**Flow:**
1. Stage 1: 4 agents generate independent proposals
2. Debate: Agents critique each other, then respond/refine
3. Stage 2: 3 agents synthesize from Stage 1 + debates
4. Stage 3: 2 agents produce final versions
5. Assessor: Evaluates and merges best features

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
