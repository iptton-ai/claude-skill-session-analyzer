# Claude Skill: Session Analyzer

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-blue)](https://claude.ai/code)

Analyze your Claude Code session history to identify pain points, track improvement trends, detect knowledge gaps, and generate actionable CLAUDE.md update suggestions.

## Features

- **Pain Point Detection** — Automatically identifies recurring user corrections and categorizes them (state management, build errors, logic errors, publishing, etc.)
- **Trend Tracking** — Incremental analysis with ↑↓→ trend arrows comparing current metrics to previous runs
- **Knowledge Gap Detection** — Identifies topics that triggered excessive web searches or required user-provided documentation
- **CLAUDE.md Suggestions** — Generates ready-to-paste rule text, checklists, and error reference tables
- **File Hotspot Analysis** — Highlights files edited most frequently, indicating potential architectural issues
- **Bilingual Support** — Analyzes both Chinese and English session content
- **Zero Dependencies** — Pure Python 3.10+ standard library, no external packages needed

## Installation

### Option 1: Plugin Marketplace (Recommended)

```bash
/plugin marketplace add iptton-ai/claude-skill-session-analyzer
/plugin install session-analyzer
```

### Option 2: Git Clone & Copy

```bash
git clone https://github.com/iptton-ai/claude-skill-session-analyzer.git
cp -r claude-skill-session-analyzer/skills/* ~/.claude/skills/
```

## Usage

### In Claude Code

```
/session-analyzer
```

The skill will automatically:
1. Detect the current project's session directory from `~/.claude/projects/`
2. Check for previous analysis state (enables incremental mode + trends)
3. Run the analysis engine
4. Present a structured report with pain points, trends, and suggestions
5. Offer to apply CLAUDE.md updates

### Standalone (CLI)

```bash
# Full analysis
python3 ~/.claude/skills/session-analyzer/analyze.py \
  --session-dir ~/.claude/projects/<your-project-hash> \
  --project-root /path/to/your/project \
  --output .claude/session-analysis-report.json

# Incremental analysis (only new sessions since last run)
python3 ~/.claude/skills/session-analyzer/analyze.py \
  --session-dir ~/.claude/projects/<your-project-hash> \
  --project-root /path/to/your/project \
  --since "2026-04-01T00:00:00" \
  --previous-state .claude/session-analysis-report.state.json \
  --output .claude/session-analysis-report.json
```

## Report Output

The skill generates a structured report with:

### Top Pain Points
| # | Pain Point | Evidence | Trend |
|---|-----------|----------|-------|
| 1 | Build errors | 14 corrections | → |
| 2 | Business logic errors | 7 corrections | ↑ |
| 3 | Cross-page state sync | 6 corrections | ↓ |

### CLAUDE.md Suggestions
Copyable text blocks for:
- State management checklists
- Build error reference tables
- Publishing pre-flight checklists

### Knowledge Gaps
Topics where Claude needed excessive web searches or user-provided documentation.

### Detailed Metrics
Tool usage, file hotspots, session breakdowns, message classifications.

## CLI Options

| Flag | Required | Description |
|------|----------|-------------|
| `--session-dir` | Yes | Path to JSONL session directory |
| `--project-root` | Yes | Absolute path to project root |
| `--since` | No | ISO 8601 timestamp for incremental analysis |
| `--previous-state` | No | Path to previous state JSON for trend comparison |
| `--output` | No | Output file path (defaults to stdout) |

## How It Works

1. **Session Loading** — Reads JSONL files from `~/.claude/projects/<hash>/`
2. **Project Filtering** — Filters sessions by checking file paths in tool calls against your project name
3. **Correction Detection** — Bilingual keyword matching for frustration/correction signals
4. **Classification** — Categorizes corrections into: state_stale, build_error, logic_error, permission, sizing, publish, knowledge_gap
5. **Trend Computation** — Compares current metrics against previous analysis snapshot
6. **Suggestion Generation** — Data-driven CLAUDE.md improvement recommendations

## State File

Located at `<project-root>/.claude/session-analysis-report.state.json`:

```json
{
  "last_analysis": "2026-04-15T14:30:00",
  "metrics_snapshot": {
    "correction_rate": 0.228,
    "build_success_rate": 0.965,
    "total_sessions": 50
  },
  "analysis_history": [
    {"date": "2026-04-01", "correction_rate": 0.25, "total_sessions": 30},
    {"date": "2026-04-15", "correction_rate": 0.228, "total_sessions": 50}
  ]
}
```

## Example Results

From a 50-session HarmonyOS project analysis:

| Metric | Value |
|--------|-------|
| Total sessions | 50 |
| User messages | 195 |
| Corrections | 45 (23.1%) |
| Build success rate | 96.5% (28/29) |
| Top pain point | Build errors (14 corrections) |
| Knowledge gaps | HarmonyOS API (13 searches), ArkTS (10 searches) |

## License

MIT
