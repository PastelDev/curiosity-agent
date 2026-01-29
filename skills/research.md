# Research Methodology Skill

How to approach research and experimentation systematically.

## Research Process

1. **Define the Question**
   - What exactly are we trying to learn?
   - What would success look like?

2. **Search Existing Knowledge**
   - Check journal for prior work: `read_journal(query="...")`
   - Search the web: `internet_search(query="...")`
   - Read relevant sources: `fetch_url(url="...")`

3. **Form Hypothesis**
   - Based on findings, what do we expect?
   - Document in journal as an idea

4. **Design Experiment**
   - What will we test?
   - How will we measure success?
   - What are the controls?

5. **Execute**
   - Run the experiment
   - Capture all outputs

6. **Analyze**
   - Did results match hypothesis?
   - What did we learn?

7. **Document**
   - Write to journal with `write_journal(entry_type="empirical_result", ...)`
   - Include: hypothesis, methodology, results, conclusion

## When to Use Tournaments

Use tournaments when:
- Problem has multiple valid approaches
- You want diverse perspectives
- Solution requires synthesis of ideas
- Quality matters more than speed

Don't use tournaments for:
- Simple, well-defined tasks
- Time-critical operations
- Tasks with clear single solutions

## Documenting Failures

Always document failures:
```python
write_journal(
    entry_type="failed_attempt",
    title="What we tried",
    content="Detailed description of the attempt",
    metadata={
        "error_message": "...",
        "hypothesized_cause": "...",
        "lessons_learned": "..."
    }
)
```

Failures are valuable data for avoiding repeated mistakes.

## Building on Prior Work

Before starting any significant task:
1. Check journal for related entries
2. Review failed attempts to avoid pitfalls
3. Build on successful approaches
