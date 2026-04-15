---
name: session-analyzer
description: Analyze Claude Code session JSONL history to identify pain points, track improvement trends, detect knowledge gaps, and generate actionable CLAUDE.md update suggestions. Use /session-analyzer to run.
allowed-tools: Bash(python3:*), Read, Glob, Grep, Write
---

# Session Analyzer

Analyze your Claude Code conversation history to find patterns, measure improvement, and get concrete suggestions for your project's CLAUDE.md.

## Execution Steps

### Step 1: Detect Project Session Directory

The current working directory maps to a session directory under `~/.claude/projects/`. Compute the path:

1. Get the current working directory (e.g., `/Users/zxnap/code/MyWorks/yltech.apps/lineassistant`)
2. Convert to hash: strip leading `/`, replace all `/` with `-` → `-Users-zxnap-code-MyWorks-yltech-apps-lineassistant`
3. Form the path: `~/.claude/projects/<hash>/`
4. Verify it exists and contains `*.jsonl` files

If the computed path doesn't match, use this fallback:
```bash
ls ~/.claude/projects/ | head -20
```
Then find the directory whose JSONL files contain references to the current project name (basename of cwd).

### Step 2: Check for Previous Analysis State

Read the state file at `<project-root>/.claude/session-analysis-state.json`.

If it exists:
- Extract `last_analysis` timestamp for incremental mode
- Extract `metrics_snapshot` for trend comparison
- Note the `analysis_history` array

If it doesn't exist:
- This is the first run → full analysis mode
- No trend data will be available

### Step 3: Run Analysis Script

Execute the analysis engine:

```bash
python3 ~/.claude/skills/session-analyzer/analyze.py \
  --session-dir "<detected-session-dir>" \
  --project-root "<cwd>" \
  --since "<last-analysis-timestamp-or-omit>" \
  --previous-state "<project-root>/.claude/session-analysis-state.json" \
  --output "<project-root>/.claude/session-analysis-report.json"
```

Parameters:
- `--session-dir`: Path from Step 1
- `--project-root`: Current working directory
- `--since`: Only if state file exists (use `last_analysis` value)
- `--previous-state`: Only if state file exists
- `--output`: Write to `<project-root>/.claude/session-analysis-report.json`

If the script fails:
- Check Python version (requires 3.10+)
- Verify the session directory has JSONL files
- Try without `--since` for a full analysis

### Step 4: Read and Present the Report

Read the generated JSON report and present a structured analysis:

```
## Session Analysis Report: <project-name>

> Period: <date-range> | Sessions: <N> | Mode: <incremental/full>

### Overview

| Metric | Value | Trend |
|--------|-------|-------|
| Total sessions | N | - |
| User corrections | N (rate%) | ↑↓→ |
| Build success rate | N% | ↑↓→ |
| Avg session turns | N | ↑↓→ |

### Top Pain Points

| # | Pain Point | Evidence | Trend |
|---|-----------|----------|-------|
| 1 | ... | N corrections | ↑↓→ |

<For each pain point, list its action items>

### CLAUDE.md Update Suggestions

<Present each suggestion as a copyable code block with section header>

### Knowledge Gaps

| Topic | Searches | User-provided docs |
|-------|----------|-------------------|

### Action Items (Prioritized)

1. **[HIGH]** ...
2. **[MEDIUM]** ...
3. **[LOW]** ...

### File Hotspots

<Show high-frequency files with edit counts>

### Detailed Metrics

<Tool usage table, message classifications, top sessions>
```

**Important formatting rules:**
- Use trend arrows: ↑ (improving/worsening depending on metric), ↓ (improving/worsening), → (stable)
- For correction_rate: ↓ is good (fewer corrections)
- For build_success_rate: ↑ is good
- Prioritize pain points by correction count
- Make CLAUDE.md suggestions copyable and concrete

### Step 5: Offer to Apply Suggestions

After presenting the report, ask the user:

1. "Do you want me to apply any of the CLAUDE.md suggestions?"
2. "Should I update the state file for future trend tracking?"

If the user confirms, apply the selected suggestions to CLAUDE.md using the Edit tool.

## State File Format

Location: `<project-root>/.claude/session-analysis-state.json`

```json
{
  "last_analysis": "2026-04-15T14:30:00",
  "metrics_snapshot": {
    "correction_rate": 0.228,
    "build_success_rate": 1.0,
    "avg_session_turns": 105.6,
    "total_sessions": 50,
    "corrections_count": 44
  },
  "analysis_history": [
    {"date": "2026-04-01T10:00:00", "correction_rate": 0.25, "total_sessions": 30},
    {"date": "2026-04-15T14:30:00", "correction_rate": 0.228, "total_sessions": 50}
  ]
}
```

The state file is **automatically updated** by analyze.py when `--output` is specified. The script creates a companion `.state.json` file alongside the report.

## Usage Examples

### First run (full analysis)
```
/session-analyzer
```

### After applying CLAUDE.md changes
Run again to see if metrics improve:
```
/session-analyzer
```
The second run will compare against the first run's metrics and show trend arrows.

## Notes

- The analysis script is pure Python (no external dependencies)
- JSONL files can be large (50MB+); analysis may take 10-30 seconds
- Incremental mode only processes new/modified JSONL files since last analysis
- The state file is per-project; different projects have independent tracking
- All analysis runs locally; no data is sent externally
