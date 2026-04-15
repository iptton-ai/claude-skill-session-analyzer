#!/usr/bin/env python3
"""
Claude Code Session JSONL 分析引擎（通用版）。

用法：
  python3 analyze.py --session-dir <path> --project-root <path> [--since <ISO>] [--previous-state <path>] [--output <path>]

输出：JSON 格式的分析报告。
"""

import argparse
import json
import glob
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


# === 双语关键词配置 ===

FRUSTRATION_KEYWORDS_ZH = [
    "还是失败", "还是不行", "不对", "修复", "没响应", "没找到",
    "失败了", "没有申请", "尺寸不对", "没变", "没更新", "还是没",
    "并没有", "你还是", "你再搜索", "你仔细检查", "检查下是不是",
    "空包", "再试下", "并没有", "不一致", "不对", "错误",
    "再检查下", "还是没有", "是不是", "并没有弹出来", "没有能够",
    "是不是没", "还是没更新", "不刷新", "数据不对", "逻辑错误",
    "硬编码", "hardcode",
]

FRUSTRATION_KEYWORDS_EN = [
    "still broken", "still failing", "wrong", "not working",
    "didn't work", "didn't update", "try again", "look more carefully",
    "still not fixed", "empty", "incorrect", "error", "fail",
    "not updating", "not refreshing", "doesn't work", "doesn't respond",
    "crash", "bug", "fix this",
]

BUG_KEYWORDS_ZH = [
    "修复", "没响应", "不更新", "没有更新", "没变", "不一致",
    "错误", "crash", "失败", "不对", "尺寸不对", "hardcode",
    "还是失败", "还是不行", "空包", "不刷新", "硬编码",
]

BUG_KEYWORDS_EN = [
    "fix", "bug", "crash", "error", "broken", "wrong",
    "not working", "not updating", "incorrect", "fail",
]

FEATURE_KEYWORDS_ZH = ["帮我实现", "添加", "创建", "帮我检查", "帮我修复", "帮我编译", "帮我调研"]
FEATURE_KEYWORDS_EN = ["implement", "add ", "create", "build", "help me"]

RESEARCH_KEYWORDS_ZH = ["调研", "搜索", "参考", "搜索下"]
RESEARCH_KEYWORDS_EN = ["research", "search", "investigate", "look up"]

PUBLISH_KEYWORDS = [
    "google play", "appgallery", "app store", "upload", "publish",
    "fastlane", "发布", "上传", "签名", "release",
    "deploy", "上架", "提交审核",
]

BUILD_TOOL_PREFIXES = [
    "/Applications/DevEco", "hvigor", "gradle", "npm run",
    "cargo build", "xcodebuild", "dotnet build", "make",
    "mvn ", "ant ",
]

SYSTEM_MESSAGE_PREFIXES = [
    "<system-reminder>",
    "<command-name>",
    "<command-message>",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<task-notification>",
    "This session is being continued",
]

# 通用编译错误模式
GENERIC_BUILD_ERROR_PATTERNS = [
    r"ERROR:\s*\d+\s+\w+",
    r"error\s+\w{2}\d{5,}",
    r"BUILD FAILED",
    r"Compilation failed",
    r"(\w+)-no-\w+",  # e.g., arkts-no-*, ts-no-*, etc.
    r"is not assignable to type",
    r"cannot find (?:symbol|module|name)",
    r"Type .* is not assignable",
    r"undefined (?:reference|symbol)",
    r"No such file or directory",
]

# WebSearch 工具名变体
WEBSEARCH_TOOLS = {
    "WebSearch",
    "mcp__web-search-prime__web_search_prime",
    "mcp__web-reader__webReader",
    "mcp__web_reader__webReader",
}


def load_sessions(session_dir: str, since: str | None = None) -> list[dict]:
    """加载 JSONL session 文件，可选按时间增量过滤。"""
    files = sorted(glob.glob(os.path.join(session_dir, "*.jsonl")))
    entries = []
    since_ts = None
    if since:
        try:
            since_ts = datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            since_ts = None

    for f in files:
        # 增量模式：按文件修改时间过滤
        if since_ts:
            file_mtime = os.path.getmtime(f)
            if file_mtime < since_ts:
                continue
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line.strip())
                    obj["_source_file"] = os.path.basename(f)
                    entries.append(obj)
                except (json.JSONDecodeError, Exception):
                    pass
    return entries


def filter_project_sessions(entries: list[dict], project_root: str) -> list[dict]:
    """过滤与当前项目相关的 session。

    判定规则（满足任一即保留）：
    1. assistant 工具调用中 file_path 包含项目目录名
    2. Bash 命令中包含项目路径
    3. 用户消息中提及项目名
    4. 短 session（≤3 条用户消息）保留
    """
    project_keyword = os.path.basename(project_root.rstrip("/"))

    session_entries = defaultdict(list)
    for e in entries:
        session_entries[e.get("sessionId", "unknown")].append(e)

    kept_session_ids = set()

    for sid, s_entries in session_entries.items():
        has_project_ref = False
        user_msg_count = 0

        for e in s_entries:
            if e.get("type") == "assistant":
                content = e.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            inp = block.get("input", {})
                            fp = inp.get("file_path", "")
                            cmd = inp.get("command", "")
                            if project_keyword in fp or project_keyword in cmd:
                                has_project_ref = True
                                break
                            if f"/{project_keyword}" in cmd:
                                has_project_ref = True
                                break
                if has_project_ref:
                    break

            if e.get("type") == "user" and e.get("message", {}).get("role") == "user":
                user_msg_count += 1
                text = e["message"].get("content", "")
                if isinstance(text, str) and project_keyword in text:
                    has_project_ref = True
                    break

        if has_project_ref:
            kept_session_ids.add(sid)
        elif user_msg_count <= 3:
            kept_session_ids.add(sid)

    return [e for e in entries if e.get("sessionId", "unknown") in kept_session_ids]


def extract_user_messages(entries: list[dict]) -> list[dict]:
    """提取有效的用户消息。"""
    messages = []
    for e in entries:
        if e.get("type") != "user":
            continue
        msg = e.get("message", {})
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str) or len(content) <= 5:
            continue
        if any(content.startswith(p) for p in SYSTEM_MESSAGE_PREFIXES):
            continue
        messages.append({
            "content": content,
            "timestamp": e.get("timestamp", ""),
            "session_id": e.get("sessionId", ""),
        })
    return messages


def extract_assistant_actions(entries: list[dict], project_root: str) -> dict:
    """提取 assistant 的工具使用和编译信息。"""
    tool_counts = Counter()
    file_edits = Counter()
    file_reads = Counter()
    build_results = []
    build_errors = []
    websearch_topics = []

    for e in entries:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message", {})
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue

            if block.get("type") == "tool_use":
                name = block.get("name", "unknown")
                tool_counts[name] += 1
                inp = block.get("input", {})

                if name in ("Edit", "Write") and inp.get("file_path"):
                    fp = inp["file_path"].replace(project_root + "/", "")
                    file_edits[fp] += 1
                elif name == "Read" and inp.get("file_path"):
                    fp = inp["file_path"].replace(project_root + "/", "")
                    file_reads[fp] += 1

                # WebSearch 主题收集
                if name in WEBSEARCH_TOOLS:
                    query = inp.get("query", inp.get("search_query", ""))
                    if query:
                        websearch_topics.append(query)

            elif block.get("type") == "text":
                text = block.get("text", "")

                if "BUILD SUCCESSFUL" in text or "BUILD SUCCESS" in text:
                    build_results.append({"result": "SUCCESS", "snippet": text[:200]})
                elif any(kw in text for kw in ["hvigor ERROR", "ERROR:", "ArkTS Compiler Error",
                                                "BUILD FAILED", "Compilation failed"]):
                    build_results.append({"result": "ERROR", "snippet": text[:200]})

                for pat in GENERIC_BUILD_ERROR_PATTERNS:
                    for m in re.findall(pat, text):
                        build_errors.append(m)

    return {
        "tool_counts": tool_counts,
        "file_edits": file_edits,
        "file_reads": file_reads,
        "build_results": build_results,
        "build_errors": Counter(build_errors),
        "websearch_topics": websearch_topics,
    }


def classify_user_message(content: str) -> str:
    """分类用户消息类型（双语）。"""
    content_lower = content.lower()

    if any(content.strip().startswith(p) for p in BUILD_TOOL_PREFIXES):
        return "build_command"

    if any(kw in content for kw in PUBLISH_KEYWORDS):
        return "publish"

    if "<teammate-message" in content or "team-lead" in content:
        return "agent_team"

    all_bug_kw = BUG_KEYWORDS_ZH + BUG_KEYWORDS_EN
    if any(kw.lower() in content_lower for kw in all_bug_kw):
        return "bug_report"

    all_feature_kw = FEATURE_KEYWORDS_ZH + FEATURE_KEYWORDS_EN
    if any(kw.lower() in content_lower for kw in all_feature_kw):
        return "feature_request"

    all_research_kw = RESEARCH_KEYWORDS_ZH + RESEARCH_KEYWORDS_EN
    if any(kw.lower() in content_lower for kw in all_research_kw):
        return "research"

    return "other"


def analyze_corrections(user_messages: list[dict]) -> list[dict]:
    """提取用户纠正/挫折事件（双语）。

    排除 teammate-message（agent team 内部通信）和纯构建命令。
    """
    all_keywords = FRUSTRATION_KEYWORDS_ZH + FRUSTRATION_KEYWORDS_EN
    corrections = []
    for msg in user_messages:
        content = msg["content"]
        # 跳过 teammate 内部消息
        if content.strip().startswith("<teammate-message"):
            continue
        # 跳过纯构建命令
        if any(content.strip().startswith(p) for p in BUILD_TOOL_PREFIXES):
            continue

        content_lower = content.lower()
        if any(kw.lower() in content_lower for kw in all_keywords):
            corrections.append({
                "content": content[:200],
                "timestamp": msg["timestamp"],
                "session_id": msg["session_id"][:8],
                "type": _classify_correction(content),
            })
    return corrections


def _classify_correction(content: str) -> str:
    """将纠正分类到具体问题类型。"""
    content_lower = content.lower()
    if any(kw in content_lower for kw in ["不更新", "没更新", "没变", "不刷新", "没响应",
                                           "not updating", "not refreshing"]):
        return "state_stale"
    if any(kw in content_lower for kw in ["编译", "compiler", "build", "error"]):
        return "build_error"
    if any(kw in content_lower for kw in ["权限", "permission"]):
        return "permission"
    if any(kw in content_lower for kw in ["尺寸", "size", "分辨率"]):
        return "sizing"
    if any(kw in content_lower for kw in ["发布", "上传", "upload", "publish", "deploy"]):
        return "publish"
    if any(kw in content_lower for kw in ["搜索", "调研", "search", "文档"]):
        return "knowledge_gap"
    if any(kw in content_lower for kw in ["逻辑", "跳到", "点", "点击"]):
        return "logic_error"
    return "other"


def analyze_session_metrics(entries: list[dict]) -> dict:
    """分析每个 session 的度量指标。"""
    sessions = defaultdict(lambda: {
        "turns": 0,
        "user_msgs": 0,
        "assistant_msgs": 0,
        "tools_used": 0,
        "slash_cmds": [],
        "first_ts": None,
        "last_ts": None,
    })

    for e in entries:
        sid = e.get("sessionId", "unknown")
        ts = e.get("timestamp", "")
        s = sessions[sid]
        if s["first_ts"] is None:
            s["first_ts"] = ts
        s["last_ts"] = ts

        if e.get("type") == "user" and e.get("message", {}).get("role") == "user":
            content = e["message"].get("content", "")
            if isinstance(content, str):
                s["user_msgs"] += 1
                s["turns"] += 1
                cmd_match = re.search(r"<command-name>(.*?)</command-name>", content)
                if cmd_match:
                    s["slash_cmds"].append(cmd_match.group(1))
        elif e.get("type") == "assistant":
            s["assistant_msgs"] += 1
            s["turns"] += 1
            content = e.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        s["tools_used"] += 1

    return {k: v for k, v in sessions.items() if v["user_msgs"] > 0}


def detect_knowledge_gaps(entries: list[dict], assistant_actions: dict) -> list[dict]:
    """检测知识盲区：WebSearch 触发频次 + 用户主动提供文档。"""
    gaps = defaultdict(lambda: {"search_count": 0, "user_provided_docs": 0})

    # 按 WebSearch query 的主题归类
    for query in assistant_actions.get("websearch_topics", []):
        topic = _extract_topic(query)
        gaps[topic]["search_count"] += 1

    # 用户主动提供文档（URL 或 "参考"）
    for e in entries:
        if e.get("type") != "user":
            continue
        content = e.get("message", {}).get("content", "")
        if not isinstance(content, str):
            continue
        urls = re.findall(r"https?://[^\s<>\"']+", content)
        doc_refs = re.findall(r"参考[这这下面]?.*?(文档|链接|文章)", content)
        if urls or doc_refs:
            topic = _extract_topic(content)
            gaps[topic]["user_provided_docs"] += 1

    result = []
    for topic, data in sorted(gaps.items(), key=lambda x: x[1]["search_count"], reverse=True):
        if data["search_count"] > 0 or data["user_provided_docs"] > 0:
            result.append({"topic": topic, **data})
    return result[:10]


def _extract_topic(text: str) -> str:
    """从搜索 query 或消息中提取主题关键词。"""
    # 常见技术关键词
    tech_keywords = [
        r"arkts", r"arkui", r"harmonyos", r"flutter", r"react", r"swift",
        r"kotlin", r"rust", r"typescript", r"python",
        r"state\s*manage", r"状态管理",
        r"speech\s*recogni", r"语音识别", r"tts", r"语音",
        r"permission", r"权限",
        r"safe\s*area", r"避让", r"安全区域",
        r"publish", r"发布", r"upload", r"上传",
        r"build", r"编译",
        r"navigation", r"路由", r"导航",
        r"database", r"数据库",
        r"animation", r"动画",
        r"theme", r"主题",
    ]
    text_lower = text.lower()
    for kw in tech_keywords:
        m = re.search(kw, text_lower)
        if m:
            return m.group(0).strip()

    # fallback: 取前 3 个有意义的词
    words = re.findall(r"[\w\u4e00-\u9fff]+", text)
    return " ".join(words[:3]) if words else "general"


def analyze_file_hotspots(file_edits: Counter, file_reads: Counter, threshold: int = 5) -> dict:
    """分析高频编辑文件。"""
    high = []  # >20 edits
    medium = []  # >10
    low = []  # >threshold

    for fp, count in file_edits.most_common():
        reads = file_reads.get(fp, 0)
        entry = {"path": fp, "edits": count, "reads": reads}
        if count > 20:
            high.append(entry)
        elif count > 10:
            medium.append(entry)
        elif count > threshold:
            low.append(entry)

    return {"high_frequency": high, "medium_frequency": medium, "low_frequency": low}


def compute_trends(current: dict, previous_state: dict | None) -> dict:
    """对比当前指标与上次分析，计算趋势。"""
    if not previous_state:
        return {}

    prev = previous_state.get("metrics_snapshot", {})
    trends = {}

    def _trend(key: str, cur_val, prev_val):
        if prev_val is None or prev_val == 0:
            return
        diff = cur_val - prev_val
        if abs(diff) < 0.001:
            direction, arrow = "stable", "→"
        elif diff > 0:
            direction, arrow = "up", "↑"
        else:
            direction, arrow = "down", "↓"
        trends[key] = {
            "value": round(cur_val, 4),
            "previous": round(prev_val, 4),
            "direction": direction,
            "arrow": arrow,
        }

    _trend("correction_rate", current.get("correction_rate", 0), prev.get("correction_rate"))
    _trend("build_success_rate", current.get("build_success_rate", 0), prev.get("build_success_rate"))
    _trend("avg_session_turns", current.get("avg_session_turns", 0), prev.get("avg_session_turns"))

    return trends


def generate_pain_points(corrections: list[dict], trends: dict, file_hotspots: dict,
                         knowledge_gaps: list[dict], build_errors: Counter) -> list[dict]:
    """基于分析数据生成痛点排行。"""
    # 按纠正类型统计
    type_counts = Counter(c.get("type", "other") for c in corrections)
    pain_labels = {
        "state_stale": "跨页面/组件状态同步",
        "build_error": "编译错误",
        "permission": "权限管理",
        "sizing": "UI 尺寸/布局",
        "publish": "发布/部署流程",
        "knowledge_gap": "API/框架知识盲区",
        "logic_error": "业务逻辑错误",
        "other": "其他问题",
    }

    pain_points = []
    for corr_type, count in type_counts.most_common(5):
        label = pain_labels.get(corr_type, corr_type)
        trend = "stable"
        arrow = "→"
        # 简单的趋势推断
        if corr_type == "state_stale" and "correction_rate" in trends:
            t = trends["correction_rate"]
            trend, arrow = t["direction"], t["arrow"]

        action_items = _suggest_actions_for_type(corr_type, count)
        pain_points.append({
            "rank": len(pain_points) + 1,
            "title": label,
            "evidence": f"{count} 次用户纠正",
            "trend": trend,
            "arrow": arrow,
            "action_items": action_items,
        })

    # 高频编辑文件作为额外痛点
    if file_hotspots.get("high_frequency"):
        top_file = file_hotspots["high_frequency"][0]
        if top_file["edits"] > 30:
            pain_points.append({
                "rank": len(pain_points) + 1,
                "title": f"高频修改文件: {top_file['path']}",
                "evidence": f"编辑 {top_file['edits']} 次",
                "trend": "stable",
                "arrow": "→",
                "action_items": ["检查该文件是否职责过于集中，考虑拆分"],
            })

    return pain_points[:5]


def _suggest_actions_for_type(corr_type: str, count: int) -> list[str]:
    """为痛点类型生成行动建议。"""
    suggestions = {
        "state_stale": [
            "在 CLAUDE.md 中增加状态管理自检清单",
            "每次写操作后检查是否触发了全局状态更新",
        ],
        "build_error": [
            "在 CLAUDE.md 中添加编译错误速查表",
            "修改后自动运行编译验证",
        ],
        "permission": [
            "在 CLAUDE.md 中记录权限声明模板",
            "使用新 API 前检查权限需求",
        ],
        "publish": [
            "创建发布前自检清单",
            "标准化构建和上传流程",
        ],
        "knowledge_gap": [
            "在使用不熟悉的 API 前搜索官方文档",
            "将常用 API 参考保存到项目文档中",
        ],
        "logic_error": [
            "为复杂交互编写测试用例",
            "实现前先确认预期行为",
        ],
        "sizing": [
            "在 CLAUDE.md 中记录 UI 规格要求",
        ],
    }
    base = suggestions.get(corr_type, ["分析具体原因并记录到 CLAUDE.md"])
    if count > 10:
        base.append(f"⚠️ 该问题出现 {count} 次，属于高频问题，优先解决")
    return base


def generate_suggestions(corrections: list[dict], build_errors: Counter,
                         file_hotspots: dict, knowledge_gaps: list[dict]) -> dict:
    """生成可操作的改进建议。"""
    claude_md_updates = []

    # 基于纠正类型生成建议
    type_counts = Counter(c.get("type", "other") for c in corrections)
    if type_counts.get("state_stale", 0) > 3:
        claude_md_updates.append({
            "section": "状态管理",
            "action": "add_checklist",
            "text": (
                "### 状态管理自检清单（每次写操作后检查）\n\n"
                "- [ ] 写操作后是否通知了全局状态更新？\n"
                "- [ ] 关联页面是否监听了状态变化？\n"
                "- [ ] 列表渲染的 key 是否包含版本号？\n"
                "- [ ] 统计数据是否重新计算？"
            ),
        })

    if type_counts.get("build_error", 0) > 2:
        error_list = "\n".join(
            f"| `{pat}` | {cnt} 次 |"
            for pat, cnt in build_errors.most_common(5)
        )
        if error_list:
            claude_md_updates.append({
                "section": "编译规范",
                "action": "add_table",
                "text": (
                    "### 常见编译错误速查表\n\n"
                    "| 错误模式 | 出现次数 |\n"
                    "|---------|--------|\n"
                    f"{error_list}"
                ),
            })

    if type_counts.get("publish", 0) > 1:
        claude_md_updates.append({
            "section": "发布流程",
            "action": "add_checklist",
            "text": (
                "### 发布前自检清单\n\n"
                "- [ ] 使用 release 构建\n"
                "- [ ] 确认包大小 > 0MB\n"
                "- [ ] 设备类型配置正确\n"
                "- [ ] 图标和截图符合规范"
            ),
        })

    # 知识盲区建议
    knowledge_to_document = []
    for gap in knowledge_gaps[:5]:
        priority = "high" if gap["search_count"] > 3 or gap["user_provided_docs"] > 0 else "medium"
        knowledge_to_document.append({
            "topic": gap["topic"],
            "priority": priority,
            "search_count": gap["search_count"],
            "user_provided_docs": gap["user_provided_docs"],
        })

    # 工作流改进
    workflow_improvements = []
    if file_hotspots.get("high_frequency"):
        for f in file_hotspots["high_frequency"][:3]:
            if f["edits"] > 30:
                workflow_improvements.append({
                    "finding": f"`{f['path']}` 被编辑 {f['edits']} 次（读取 {f['reads']} 次），编辑/读取比 {f['edits']/max(f['reads'],1):.1f}",
                    "priority": "high" if f["edits"] > 50 else "medium",
                })

    return {
        "claude_md_updates": claude_md_updates,
        "knowledge_to_document": knowledge_to_document,
        "workflow_improvements": workflow_improvements,
    }


def run_analysis(args) -> dict:
    """执行完整分析流程。"""
    # 1. 加载 sessions
    entries = load_sessions(args.session_dir, args.since)
    total_files = len(set(e.get("_source_file", "") for e in entries))

    # 2. 过滤项目相关
    entries = filter_project_sessions(entries, args.project_root)
    kept_files = len(set(e.get("_source_file", "") for e in entries))

    # 3. 提取用户消息
    user_messages = extract_user_messages(entries)

    # 4. 分析 assistant 操作
    assistant_actions = extract_assistant_actions(entries, args.project_root)

    # 5. 分析纠正
    corrections = analyze_corrections(user_messages)

    # 6. 分析 session 指标
    session_metrics = analyze_session_metrics(entries)

    # 7. 文件热点
    file_hotspots = analyze_file_hotspots(
        assistant_actions["file_edits"], assistant_actions["file_reads"]
    )

    # 8. 知识盲区
    knowledge_gaps = detect_knowledge_gaps(entries, assistant_actions)

    # 9. 概览指标
    build_success = sum(1 for b in assistant_actions["build_results"] if b["result"] == "SUCCESS")
    build_error = sum(1 for b in assistant_actions["build_results"] if b["result"] == "ERROR")
    total_builds = build_success + build_error
    build_success_rate = round(build_success / total_builds, 4) if total_builds > 0 else None

    turns_list = [v["turns"] for v in session_metrics.values()]
    correction_rate = round(len(corrections) / len(user_messages), 4) if user_messages else 0

    overview = {
        "total_sessions": len(session_metrics),
        "user_messages": len(user_messages),
        "corrections_count": len(corrections),
        "correction_rate": correction_rate,
        "build_success_rate": build_success_rate,
        "build_total": total_builds,
        "build_success": build_success,
        "build_error": build_error,
        "avg_session_turns": round(sum(turns_list) / len(turns_list), 1) if turns_list else 0,
        "max_session_turns": max(turns_list) if turns_list else 0,
        "total_tool_calls": sum(assistant_actions["tool_counts"].values()),
        "total_file_edits": sum(assistant_actions["file_edits"].values()),
    }

    current_metrics = {
        "correction_rate": correction_rate,
        "build_success_rate": build_success_rate or 0,
        "avg_session_turns": overview["avg_session_turns"],
        "total_sessions": len(session_metrics),
        "corrections_count": len(corrections),
    }

    # 10. 趋势对比
    previous_state = None
    if args.previous_state and os.path.exists(args.previous_state):
        with open(args.previous_state, encoding="utf-8") as f:
            previous_state = json.load(f)
    trends = compute_trends(current_metrics, previous_state)

    # 11. 消息分类
    msg_types = Counter(classify_user_message(m["content"]) for m in user_messages)

    # 12. 痛点
    pain_points = generate_pain_points(
        corrections, trends, file_hotspots, knowledge_gaps,
        assistant_actions["build_errors"]
    )

    # 13. 建议
    suggestions = generate_suggestions(
        corrections, assistant_actions["build_errors"],
        file_hotspots, knowledge_gaps
    )

    # 14. Session 详情
    session_details = []
    for sid, info in sorted(session_metrics.items(), key=lambda x: x[1]["turns"], reverse=True)[:20]:
        session_details.append({
            "session_id": sid[:8],
            "user_msgs": info["user_msgs"],
            "turns": info["turns"],
            "tools": info["tools_used"],
            "slash_cmds": info["slash_cmds"][:5],
        })

    # 生成报告
    report = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "session_dir": args.session_dir,
            "project_root": args.project_root,
            "since": args.since,
            "total_jsonl_files": total_files,
            "analyzed_jsonl_files": kept_files,
            "incremental": args.since is not None,
        },
        "overview": overview,
        "trends": trends,
        "message_classifications": dict(msg_types.most_common()),
        "tool_usage": [
            {"tool": t, "count": c}
            for t, c in assistant_actions["tool_counts"].most_common(20)
        ],
        "file_hotspots": file_hotspots,
        "build_errors": [
            {"pattern": p, "count": c}
            for p, c in assistant_actions["build_errors"].most_common(10)
        ],
        "corrections": [
            {
                "content": c["content"][:150],
                "timestamp": c["timestamp"],
                "session_id": c["session_id"],
                "type": c["type"],
            }
            for c in corrections[:30]
        ],
        "session_metrics": session_details,
        "knowledge_gaps": knowledge_gaps,
        "pain_points": pain_points,
        "suggestions": suggestions,
        # 用于更新 state 文件
        "_new_state": {
            "last_analysis": datetime.now().isoformat(),
            "metrics_snapshot": current_metrics,
        },
    }

    return report


def main():
    parser = argparse.ArgumentParser(description="Claude Code Session JSONL 分析引擎")
    parser.add_argument("--session-dir", required=True, help="JSONL 文件目录")
    parser.add_argument("--project-root", required=True, help="项目根目录绝对路径")
    parser.add_argument("--since", default=None, help="增量分析起点（ISO 8601 时间戳）")
    parser.add_argument("--previous-state", default=None, help="上次分析状态文件路径")
    parser.add_argument("--output", default=None, help="输出文件路径（默认 stdout）")

    args = parser.parse_args()

    report = run_analysis(args)

    # 分离内部状态数据
    new_state = report.pop("_new_state", None)

    output_json = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)

        # 同时保存状态文件（同目录下 .state.json）
        if new_state:
            state_path = args.output.replace(".json", ".state.json")
            # 保留历史
            history = []
            if args.previous_state and os.path.exists(args.previous_state):
                with open(args.previous_state, encoding="utf-8") as f:
                    old = json.load(f)
                    history = old.get("analysis_history", [])
            history.append({
                "date": new_state["last_analysis"],
                **new_state["metrics_snapshot"],
            })
            new_state["analysis_history"] = history[-20:]  # 保留最近 20 次
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(new_state, f, ensure_ascii=False, indent=2)

        print(f"Report written to: {args.output}", file=sys.stderr)
        if new_state:
            print(f"State saved to: {args.output.replace('.json', '.state.json')}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
