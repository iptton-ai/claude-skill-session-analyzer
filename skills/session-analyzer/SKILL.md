---
name: session-analyzer
description: Analyze Claude Code session JSONL history using prompt-based semantic analysis. Identifies pain points, tracks improvement trends, detects knowledge gaps, and generates actionable CLAUDE.md update suggestions. Supports parallel subagent analysis for large datasets. Use /session-analyzer to run.
allowed-tools: Bash(python3:*), Read, Glob, Grep, Write, Agent
---

# Session Analyzer (Prompt-Based)

分析 Claude Code 会话历史，使用 LLM 语义理解替代硬编码关键词匹配，识别痛点、追踪改进趋势、生成可操作的 CLAUDE.md 改进建议。

当数据量较大时，自动启动 subagent 并行分析加速处理。

## Execution Steps

### Step 1: Detect Project Session Directory

当前工作目录映射到 `~/.claude/projects/` 下的 session 目录。计算路径：

1. 获取当前工作目录（如 `/Users/zxnap/code/MyWorks/yltech.apps/lineassistant`）
2. 转换为 hash：去掉前导 `/`，将所有 `/` 替换为 `-` → `-Users-zxnap-code-MyWorks-yltech-apps-lineassistant`
3. 组合路径：`~/.claude/projects/<hash>/`
4. 验证目录存在且包含 `*.jsonl` 文件

如果计算路径不匹配，使用备用方案：
```bash
ls ~/.claude/projects/ | head -20
```
然后找到 JSONL 文件中包含当前项目名的目录。

### Step 2: Check for Previous Analysis State

读取状态文件 `<project-root>/.claude/session-analysis-state.json`。

如果存在：
- 提取 `last_analysis` 时间戳用于增量模式
- 提取 `metrics_snapshot` 用于趋势对比

如果不存在：
- 首次运行 → 全量分析模式

### Step 3: Extract Raw Data

运行数据提取器（纯数据提取，不含语义分析）：

```bash
python3 ~/.claude/skills/session-analyzer/analyze.py \
  --session-dir "<detected-session-dir>" \
  --project-root "<cwd>" \
  --since "<last-analysis-timestamp-or-omit>" \
  --previous-state "<project-root>/.claude/session-analysis-state.json" \
  --output "<project-root>/.claude/session-analysis-raw.json"
```

参数说明：
- `--session-dir`：Step 1 检测到的路径
- `--project-root`：当前工作目录
- `--since`：仅在状态文件存在时使用（使用 `last_analysis` 值）
- `--previous-state`：仅在状态文件存在时使用
- `--output`：写入 `<project-root>/.claude/session-analysis-raw.json`

如果脚本失败：
- 检查 Python 版本（需要 3.10+）
- 验证 session 目录包含 JSONL 文件
- 尝试不带 `--since` 运行全量分析

### Step 4: Load Data & Assess Volume

读取生成的原始数据文件 `<project-root>/.claude/session-analysis-raw.json`。

提取关键数据：
- `overview`：概览指标
- `user_messages`：所有用户消息（含 index, content, timestamp, session_id）
- `assistant_summary`：工具使用、文件热点、构建结果、搜索主题
- `session_metrics`：每个 session 的指标
- `trends`：趋势数据
- `previous_state`：上次分析状态

**容量评估**：
- `overview.total_sessions` ≤ 40 **且** `overview.user_messages` ≤ 150 → **Direct Analysis Mode**（Step 5A）
- 否则 → **Subagent Analysis Mode**（Step 5B）

### Step 5A: Direct Analysis Mode（小数据量）

当数据量可控时，直接分析所有数据。

按照 **Appendix A: Analysis Framework** 中的框架，对所有 `user_messages` 进行分析。

将分析结果与 `assistant_summary`（工具使用、文件热点、构建错误）和 `trends` 结合，生成完整报告。

### Step 5B: Subagent Analysis Mode（大数据量，3 个 subagent 并行）

#### 5B.1: 准备批次

将 `user_messages` 数组按 index 分成 3 个大致相等的批次：
- Batch 1: messages[0 : N/3]
- Batch 2: messages[N/3 : 2*N/3]
- Batch 3: messages[2*N/3 : N]

同时准备共享上下文摘要（供每个 subagent 参考）：

```
项目概览:
- 总会话数: {overview.total_sessions}
- 总用户消息: {overview.user_messages}
- 构建成功率: {overview.build_success_rate}
- 平均会话轮次: {overview.avg_session_turns}

工具使用 Top 10:
{assistant_summary.tool_usage 前10条格式化为表格}

文件热点 Top 5:
{assistant_summary.file_hotspots 所有 high/medium 条目}

构建错误 Top 5:
{assistant_summary.build_errors 前5条}

搜索主题 Top 5:
{assistant_summary.websearch_topics 前5条}

趋势:
{trends 格式化摘要}
```

#### 5B.2: 启动 Subagents

**同时**启动最多 3 个 subagent，使用 Agent tool，每个 subagent 的 prompt 按 **Appendix B: Subagent Prompt Template** 填充：

- 每个 subagent 接收：一个批次的消息 + 共享上下文
- 每个 subagent 返回：JSON 格式的批次分析结果
- 所有 subagent 必须在**同一条消息中并行启动**（3 个 Agent tool calls）

```
Agent({description: "Analyze session batch 1/3", prompt: "<填充后的 subagent prompt>"})
Agent({description: "Analyze session batch 2/3", prompt: "<填充后的 subagent prompt>"})
Agent({description: "Analyze session batch 3/3", prompt: "<填充后的 subagent prompt>"})
```

#### 5B.3: 合并结果

所有 subagent 完成后，按照 **Appendix C: Merge Framework** 合并结果：

1. 汇总分类计数
2. 合并所有纠正记录
3. 综合生成整体痛点和建议
4. 结合工具使用和文件热点数据

### Step 6: Present the Report

将分析结果格式化为结构化报告：

```
## Session Analysis Report: <project-name>

> Period: <date-range> | Sessions: <N> | Mode: <incremental/full> | Analysis: <direct/subagent>

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

**格式规则**：
- 趋势箭头：↑（改善/恶化取决于指标），↓（改善/恶化），→（稳定）
- correction_rate：↓ 是好的（更少纠正）
- build_success_rate：↑ 是好的
- 痛点按纠正频率排序
- CLAUDE.md 建议必须可复制且具体

### Step 7: Offer to Apply Suggestions

报告呈现后，询问用户：

1. "是否要应用某些 CLAUDE.md 建议？"
2. "是否更新状态文件以追踪未来趋势？"

如果用户确认，使用 Edit tool 将选中的建议应用到 CLAUDE.md。

同时更新状态文件中的 `correction_rate` 和 `corrections_count`（从分析结果中获取实际值）。

---

## Appendix A: Analysis Framework

分析用户消息时，遵循以下框架。这替代了原先的硬编码关键词匹配，使用 LLM 的语义理解能力。

### A.1 消息分类

对每条用户消息，判断其主要意图：

| 类型 | 描述 | 识别线索 |
|------|------|---------|
| **correction** | 用户纠正 Claude 的错误或表达不满/挫折 | 否定语气、指出错误、要求重做、"不对"/"还是不行"/"再检查"/"wrong"/"still broken" |
| **bug_report** | 报告缺陷或异常行为 | 描述异常行为、crash、报错信息 |
| **feature_request** | 请求新功能或改进 | 明确的需求描述、"帮我实现"/"添加"/"implement"/"add" |
| **research** | 调研/搜索请求 | "调研"/"搜索"/"investigate"/"look up" |
| **publish** | 发布/部署相关 | "发布"/"deploy"/"upload"/"上架" |
| **build_command** | 纯构建命令 | 以构建工具前缀开头的命令 |
| **agent_team** | Agent team 内部通信 | `<teammate-message` 开头 |
| **other** | 其他 | 不属于以上类别 |

### A.2 纠正深度分析

对分类为 **correction** 的消息，进一步分析：

**纠正类型**：
- `state_stale`：状态不同步/未更新（如"没更新"、"没变"、"不刷新"、"没响应"）
- `build_error`：编译/构建失败（如"编译失败"、"BUILD FAILED"、"编译错误"）
- `logic_error`：业务逻辑错误（如"逻辑不对"、"跳转错了"、"顺序反了"）
- `permission`：权限问题（如"权限"、"permission"、"授权"）
- `knowledge_gap`：Claude 缺乏领域知识（如"你再搜索下"、"查下文档"、"参考下"）
- `ui_issue`：UI/布局/尺寸问题（如"尺寸不对"、"布局有问题"、"间距不对"）
- `wrong_assumption`：Claude 做了错误假设（如"我说的不是这个"、"你没理解"）
- `incomplete`：实现不完整（如"还差"、"没做完"、"缺少"）
- `other`：其他纠正类型

**严重程度**：
- `high`：阻塞进度，无法继续
- `medium`：有变通方法，但影响效率
- `low`：轻微困扰，不影响主要流程

**可预防性**：是否可以通过在 CLAUDE.md 中添加规则来避免？

### A.3 痛点排行

基于纠正分析，按以下标准排列前 5 个痛点：
1. 频率（纠正次数）
2. 严重程度（高严重度权重更大）
3. 可预防性（可通过 CLAUDE.md 预防的优先处理）

每个痛点包含：
- 标题和类型
- 证据（次数、代表性消息）
- 趋势箭头（↑↓→）
- 行动建议（具体步骤）

### A.4 CLAUDE.md 建议

为每个痛点生成具体的、可复制到 CLAUDE.md 的内容：
- 使用 markdown 格式
- 在适当处包含 checklist
- 根据项目技术栈（从文件热点和工具使用推断）给出具体建议

### A.5 知识盲区检测

从 websearch_topics 和消息中提及的文档：
- 识别需要频繁搜索的主题
- 注意用户主动提供外部文档的领域
- 建议哪些主题应记录到 CLAUDE.md

---

## Appendix B: Subagent Prompt Template

启动 subagent 时，使用以下 prompt 结构。将 `{占位符}` 替换为实际数据。

```
# 会话批次分析任务

你是 Claude Code 会话分析专家。请分析以下批次的消息数据，使用语义理解识别用户痛点。

## 共享上下文

项目概览:
- 总会话数: {total_sessions}
- 总用户消息: {total_messages}
- 构建成功率: {build_success_rate}
- 平均会话轮次: {avg_session_turns}

工具使用 Top 10:
{tool_usage_formatted_as_table}

文件热点:
{file_hotspots_formatted}

构建错误 Top 5:
{build_errors_formatted}

搜索主题 Top 5:
{websearch_topics_formatted}

## 本批次消息（批次 {batch_num}/3，共 {batch_count} 条）

{batch_messages_formatted_as_numbered_list}

## 分析任务

### 1. 消息分类
对每条消息判断其主要意图类型：
- **correction**: 用户纠正 Claude 的错误或表达不满/挫折（关键指标！）
- **bug_report**: 报告缺陷或异常行为
- **feature_request**: 请求新功能或改进
- **research**: 调研、搜索相关
- **publish**: 发布/部署相关
- **build_command**: 构建命令
- **agent_team**: Agent team 内部通信
- **other**: 其他

注意：要理解消息的语义上下文，不要只做字面匹配。例如"再试一下"可能只是指令，但"还是不行，再试一下"则表示挫折。

### 2. 纠正深度分析
对标记为 correction 的消息，分析：
- **类型**: state_stale / build_error / logic_error / permission / knowledge_gap / ui_issue / wrong_assumption / incomplete / other
- **严重程度**: high（阻塞进度）/ medium（有变通方法）/ low（轻微困扰）
- **一句话概括**: 简述用户在纠正什么
- **可预防**: 是否可以通过 CLAUDE.md 规则避免

### 3. 本批次模式
列出本批次中观察到的重复模式或突出问题

## 输出格式

以纯 JSON 格式输出（不要 markdown 代码块，不要其他文字）：

{
  "batch_num": {batch_num},
  "total_messages": {batch_count},
  "classifications": {
    "correction": 0,
    "bug_report": 0,
    "feature_request": 0,
    "research": 0,
    "publish": 0,
    "build_command": 0,
    "agent_team": 0,
    "other": 0
  },
  "corrections": [
    {
      "message_summary": "一句话概括消息内容",
      "type": "state_stale",
      "severity": "high",
      "preventable": true,
      "reasoning": "为什么这样判断"
    }
  ],
  "patterns_in_batch": [
    "观察到的模式描述"
  ]
}
```

---

## Appendix C: Merge Framework

收集所有 subagent 结果后，按以下流程合并：

### C.1 合并原始数据

1. **汇总分类计数**：将 3 个批次的 classifications 对应字段相加
2. **合并纠正记录**：将所有批次的 corrections 数组合并为一个列表
3. **收集模式**：从所有批次中收集唯一的 patterns_in_batch

### C.2 计算整体指标

- **correction_rate**：total_corrections / total_user_messages（来自 overview）
- **按纠正类型统计**：从合并的 corrections 中按 type 聚合计数

### C.3 生成痛点排行

基于合并后的纠正数据：
1. 按 type 分组
2. 按频率 × 严重程度权重（high=3, medium=2, low=1）排序
3. 取 Top 5
4. 为每个痛点生成行动建议
5. 添加趋势箭头（来自 trends 数据）

### C.4 生成 CLAUDE.md 建议

为每个 Top 痛点生成具体建议：

| 痛点类型 | 建议方向 |
|---------|---------|
| state_stale | 生成状态管理自检清单 |
| build_error | 生成常见编译错误速查表（使用 build_errors 数据） |
| logic_error | 生成实现前验证清单 |
| permission | 生成权限声明模板 |
| knowledge_gap | 建议记录相关主题到项目文档 |
| ui_issue | 生成 UI 规格检查清单 |
| wrong_assumption | 建议增加假设确认流程 |
| incomplete | 建议添加实现完成度检查 |
| other | 分析具体原因并生成针对性建议 |

### C.5 知识盲区

从共享上下文的 websearch_topics 和合并后的 knowledge_gap 类型纠正：
- 列出搜索频率最高的主题
- 交叉引用 knowledge_gap 类型的纠正
- 优先处理搜索频率和纠正频率都高的主题

### C.6 输出最终报告

将所有数据组合为 Step 6 中定义的报告格式呈现给用户。

---

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

状态文件由 analyze.py 在指定 `--output` 时**自动创建/更新**。分析完成后需要用实际的 correction_rate 和 corrections_count 更新状态文件。

## Usage Examples

### First run (full analysis)
```
/session-analyzer
```

### After applying CLAUDE.md changes
再次运行查看指标是否改善：
```
/session-analyzer
```
第二次运行将对比第一次的指标并显示趋势箭头。

## Notes

- 数据提取脚本为纯 Python（无外部依赖）
- JSONL 文件可能很大（50MB+），提取可能需要 10-30 秒
- 增量模式仅处理上次分析后的新/修改 JSONL 文件
- 状态文件按项目独立，不同项目有独立的追踪
- 所有分析在本地进行，不发送外部数据
- Subagent 模式在 sessions > 40 或 messages > 150 时自动启动
- Subagent 分析结果需要主 agent 合并和综合
