# Claude Skill: Session Analyzer

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-blue)](https://claude.ai/code)

Analyze your Claude Code session history to identify pain points, track improvement trends, detect knowledge gaps, and generate actionable CLAUDE.md update suggestions.

[中文文档](README_CN.md)

## Installation

### Option 1: Claude Code Plugin Marketplace (Recommended)

```
/plugin marketplace add iptton-ai/claude-skill-session-analyzer
/plugin install session-analyzer
```

### Option 2: npx skills

```
npx skills add iptton-ai/claude-skill-session-analyzer
```

### Option 3: Clone & Copy

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
3. Run the analysis engine (direct mode for small datasets, parallel subagent mode for large)
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

## Features

### Pain Point Detection

Automatically identifies recurring user corrections using LLM-based semantic analysis and categorizes them:

| Category | Description |
|----------|-------------|
| `state_stale` | State synchronization issues |
| `build_error` | Build/compilation failures |
| `logic_error` | Business logic errors |
| `permission` | Permission issues |
| `knowledge_gap` | Claude lacking domain knowledge |
| `ui_issue` | UI/layout/sizing problems |
| `wrong_assumption` | Claude making wrong assumptions |
| `incomplete` | Incomplete implementations |

### Trend Tracking

Incremental analysis with trend arrows comparing current metrics to previous runs:

| Metric | Trend Meaning |
|--------|--------------|
| Correction rate | Down is good (fewer corrections) |
| Build success rate | Up is good |
| Avg session turns | Down is good (more efficient) |

### CLAUDE.md Suggestions

Generates ready-to-paste rule text, checklists, and error reference tables based on identified pain points.

### Knowledge Gap Detection

Identifies topics that triggered excessive web searches or required user-provided documentation.

### File Hotspot Analysis

Highlights files edited most frequently, indicating potential architectural issues.

### Bilingual Support

Analyzes both Chinese and English session content.

### Zero Dependencies

Pure Python 3.10+ standard library, no external packages needed.

## Report Output

The skill generates a structured report:

```
## Session Analysis Report: <project-name>

> Period: <date-range> | Sessions: <N> | Mode: <incremental/full> | Analysis: <direct/subagent>

### Overview
| Metric | Value | Trend |
|--------|-------|-------|
| Total sessions | N | - |
| User corrections | N (rate%) | ↑↓→ |
| Build success rate | N% | ↑↓→ |

### Top Pain Points
| # | Pain Point | Evidence | Trend |
|---|-----------|----------|-------|
| 1 | Build errors | 14 corrections | → |

### CLAUDE.md Update Suggestions
<Copyable code blocks>

### Knowledge Gaps
| Topic | Searches | User-provided docs |

### Action Items (Prioritized)
1. **[HIGH]** ...
2. **[MEDIUM]** ...
```

## Analysis Modes

| Mode | Trigger | Description |
|------|---------|-------------|
| Direct | Sessions <= 40 and Messages <= 150 | Single-pass analysis |
| Subagent | Sessions > 40 or Messages > 150 | 3 parallel subagents, then merge |

## CLI Options

| Flag | Required | Description |
|------|----------|-------------|
| `--session-dir` | Yes | Path to JSONL session directory |
| `--project-root` | Yes | Absolute path to project root |
| `--since` | No | ISO 8601 timestamp for incremental analysis |
| `--previous-state` | No | Path to previous state JSON for trend comparison |
| `--output` | No | Output file path (defaults to stdout) |

## Directory Structure

```
claude-skill-session-analyzer/
├── README.md
├── README_CN.md
├── LICENSE
├── .claude-plugin/
│   ├── marketplace.json
│   └── plugin.json
└── skills/
    └── session-analyzer/
        ├── SKILL.md
        └── analyze.py
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

## Contributing

Issues and Pull Requests welcome.

## License

MIT
