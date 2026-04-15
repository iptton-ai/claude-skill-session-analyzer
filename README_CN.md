# Claude Skill: Session Analyzer

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-blue)](https://claude.ai/code)

分析你的 Claude Code 会话历史，识别痛点、追踪改进趋势、发现知识盲区，并生成可操作的 CLAUDE.md 更新建议。

[English](README.md)

## 安装

### 方式 1: Claude Code 插件市场（推荐）

```
/plugin marketplace add iptton-ai/claude-skill-session-analyzer
/plugin install session-analyzer
```

### 方式 2: npx skills

```
npx skills add iptton-ai/claude-skill-session-analyzer
```

### 方式 3: Clone & Copy

```bash
git clone https://github.com/iptton-ai/claude-skill-session-analyzer.git
cp -r claude-skill-session-analyzer/skills/* ~/.claude/skills/
```

## 使用

### 在 Claude Code 中

```
/session-analyzer
```

技能会自动：

1. 检测当前项目的 session 目录（`~/.claude/projects/`）
2. 检查之前的分析状态（启用增量模式 + 趋势对比）
3. 运行分析引擎（小数据集直接分析，大数据集启动并行子代理）
4. 呈现包含痛点、趋势和建议的结构化报告
5. 提示是否应用 CLAUDE.md 更新

### 命令行独立使用

```bash
# 全量分析
python3 ~/.claude/skills/session-analyzer/analyze.py \
  --session-dir ~/.claude/projects/<your-project-hash> \
  --project-root /path/to/your/project \
  --output .claude/session-analysis-report.json

# 增量分析（仅处理上次分析后的新会话）
python3 ~/.claude/skills/session-analyzer/analyze.py \
  --session-dir ~/.claude/projects/<your-project-hash> \
  --project-root /path/to/your/project \
  --since "2026-04-01T00:00:00" \
  --previous-state .claude/session-analysis-report.state.json \
  --output .claude/session-analysis-report.json
```

## 功能特性

### 痛点检测

使用基于 LLM 的语义分析自动识别用户反复纠正的问题，并分类：

| 类别 | 描述 |
|------|------|
| `state_stale` | 状态同步问题 |
| `build_error` | 构建/编译失败 |
| `logic_error` | 业务逻辑错误 |
| `permission` | 权限问题 |
| `knowledge_gap` | Claude 缺乏领域知识 |
| `ui_issue` | UI/布局/尺寸问题 |
| `wrong_assumption` | Claude 做出错误假设 |
| `incomplete` | 实现不完整 |

### 趋势追踪

增量分析通过趋势箭头对比当前指标和上次运行结果：

| 指标 | 趋势含义 |
|------|---------|
| 纠正率 | 下降是好的（更少纠正） |
| 构建成功率 | 上升是好的 |
| 平均会话轮次 | 下降是好的（更高效） |

### CLAUDE.md 建议

根据识别的痛点生成可复制粘贴的规则文本、检查清单和错误速查表。

### 知识盲区检测

识别触发大量 Web 搜索或需要用户提供文档的主题。

### 文件热点分析

突出编辑频率最高的文件，提示潜在架构问题。

### 双语支持

同时支持中文和英文会话内容分析。

### 零依赖

纯 Python 3.10+ 标准库，无需安装外部包。

## 报告输出

技能生成结构化报告：

```
## Session Analysis Report: <项目名>

> 时间范围: <日期> | 会话数: <N> | 模式: <增量/全量> | 分析: <直接/子代理>

### 概览
| 指标 | 值 | 趋势 |
|------|-----|------|
| 总会话数 | N | - |
| 用户纠正 | N (比例%) | ↑↓→ |
| 构建成功率 | N% | ↑↓→ |

### 顶部痛点
| # | 痛点 | 证据 | 趋势 |
|---|------|------|------|
| 1 | 构建错误 | 14 次纠正 | → |

### CLAUDE.md 更新建议
<可复制的代码块>

### 知识盲区
| 主题 | 搜索次数 | 用户提供文档 |

### 行动项（按优先级）
1. **[高]** ...
2. **[中]** ...
```

## 分析模式

| 模式 | 触发条件 | 描述 |
|------|---------|------|
| 直接模式 | 会话数 <= 40 且消息数 <= 150 | 单次分析 |
| 子代理模式 | 会话数 > 40 或消息数 > 150 | 3 个并行子代理，然后合并结果 |

## 命令行参数

| 参数 | 必需 | 描述 |
|------|------|------|
| `--session-dir` | 是 | JSONL 会话目录路径 |
| `--project-root` | 是 | 项目根目录绝对路径 |
| `--since` | 否 | ISO 8601 时间戳，用于增量分析 |
| `--previous-state` | 否 | 上次状态 JSON 文件路径，用于趋势对比 |
| `--output` | 否 | 输出文件路径（默认输出到 stdout） |

## 目录结构

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

## 示例结果

来自一个 50 会话的 HarmonyOS 项目分析：

| 指标 | 值 |
|------|-----|
| 总会话数 | 50 |
| 用户消息 | 195 |
| 纠正 | 45 (23.1%) |
| 构建成功率 | 96.5% (28/29) |
| 顶部痛点 | 构建错误（14 次纠正） |
| 知识盲区 | HarmonyOS API（13 次搜索），ArkTS（10 次搜索） |

## 贡献

欢迎提交 Issue 和 Pull Request。

## 许可证

MIT
