# Context Management Skill

Guidelines for managing and compacting the agent's context window.

## When to Compact

- Automatic: When context usage exceeds threshold (default 85%)
- Manual: When switching to a new major task
- Strategic: Before starting a tournament to give sub-agents clean context

## What to Preserve

Always preserve these in summaries:
1. **Current goal** - What we're trying to achieve
2. **Key decisions** - Important choices made and rationale
3. **Pending tasks** - What still needs to be done
4. **File paths** - Exact paths to created files, tools, artifacts
5. **Important facts** - Names, configurations, measurements
6. **Failed attempts** - What didn't work (to avoid repeating)

## What to Compress

Aggressively compress:
- Tool outputs → Just the outcomes
- Step-by-step processes → Final results
- Repetitive attempts → What finally worked
- Verbose explanations → Key points only

## Summary Format

```
[CONTEXT SUMMARY - Compaction #N]

## Current Goal
[Main objective and sub-goals]

## Key Decisions
- Decision 1: [what] because [why]
- Decision 2: [what] because [why]

## Created Files
- /path/to/file1 - [description]
- /path/to/file2 - [description]

## Pending Tasks
1. [ ] Task description
2. [ ] Task description

## Important Facts
- Fact 1
- Fact 2

## What Didn't Work
- Approach X failed because Y

## Current Status
[Where we are in the workflow]
```

## Adjusting Threshold

The agent can adjust the compaction threshold:
- Lower (e.g., 0.7) for tasks requiring more working memory
- Higher (e.g., 0.9) for simpler tasks or when context is precious

Use `manage_context(action="set_threshold", threshold=0.8)` to adjust.
