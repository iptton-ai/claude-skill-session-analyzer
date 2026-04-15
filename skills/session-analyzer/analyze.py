#!/usr/bin/env python3
"""
Claude Code Session JSONL 数据提取器。

从 JSONL session 文件中提取原始数据，供 LLM prompt 进行语义分析。
不包含任何关键词匹配或语义分析逻辑。

用法：
  python3 analyze.py --session-dir <path> --project-root <path> [--since <ISO>] [--previous-state <path>] [--output <path>]

输出：JSON 格式的原始数据。
"""

import argparse
import json
import glob
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime


# === 数据过滤常量（用于数据清洗，非语义分析）===

SYSTEM_MESSAGE_PREFIXES = [
    "<system-reminder>",
    "<command-name>",
    "<command-message>",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<task-notification>",
    "This session is being continued",
]

BUILD_TOOL_PREFIXES = [
    "/Applications/DevEco", "hvigor", "gradle", "npm run",
    "cargo build", "xcodebuild", "dotnet build", "make",
    "mvn ", "ant ",
]

GENERIC_BUILD_ERROR_PATTERNS = [
    r"ERROR:\s*\d+\s+\w+",
    r"error\s+\w{2}\d{5,}",
    r"BUILD FAILED",
    r"Compilation failed",
    r"(\w+)-no-\w+",
    r"is not assignable to type",
    r"cannot find (?:symbol|module|name)",
    r"Type .* is not assignable",
    r"undefined (?:reference|symbol)",
    r"No such file or directory",
]

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
    """提取有效的用户消息（过滤系统消息和过短消息）。"""
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
    """提取 assistant 的工具使用和构建信息。"""
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


def analyze_session_metrics(entries: list[dict]) -> dict:
    """计算每个 session 的度量指标。"""
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


def analyze_file_hotspots(file_edits: Counter, file_reads: Counter, threshold: int = 5) -> dict:
    """分析高频编辑文件。"""
    high, medium, low = [], [], []

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


def run_analysis(args) -> dict:
    """提取原始数据，供后续 prompt 分析使用。"""
    # 1. 加载 sessions
    entries = load_sessions(args.session_dir, args.since)
    total_files = len(set(e.get("_source_file", "") for e in entries))

    # 2. 过滤项目相关
    entries = filter_project_sessions(entries, args.project_root)
    kept_files = len(set(e.get("_source_file", "") for e in entries))

    # 3. 提取用户消息
    user_messages = extract_user_messages(entries)

    # 4. 提取 assistant 操作
    assistant_actions = extract_assistant_actions(entries, args.project_root)

    # 5. Session 指标
    session_metrics = analyze_session_metrics(entries)

    # 6. 文件热点
    file_hotspots = analyze_file_hotspots(
        assistant_actions["file_edits"], assistant_actions["file_reads"]
    )

    # 7. 概览指标
    build_success = sum(1 for b in assistant_actions["build_results"] if b["result"] == "SUCCESS")
    build_error = sum(1 for b in assistant_actions["build_results"] if b["result"] == "ERROR")
    total_builds = build_success + build_error
    build_success_rate = round(build_success / total_builds, 4) if total_builds > 0 else None

    turns_list = [v["turns"] for v in session_metrics.values()]

    overview = {
        "total_sessions": len(session_metrics),
        "user_messages": len(user_messages),
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
        "correction_rate": 0,  # 由 prompt 分析填充
        "build_success_rate": build_success_rate or 0,
        "avg_session_turns": overview["avg_session_turns"],
        "total_sessions": len(session_metrics),
        "corrections_count": 0,  # 由 prompt 分析填充
    }

    # 8. 趋势对比
    previous_state = None
    if args.previous_state and os.path.exists(args.previous_state):
        with open(args.previous_state, encoding="utf-8") as f:
            previous_state = json.load(f)

    trends = compute_trends(current_metrics, previous_state)

    # 9. Session 详情
    session_details = []
    for sid, info in sorted(session_metrics.items(), key=lambda x: x[1]["turns"], reverse=True)[:20]:
        session_details.append({
            "session_id": sid[:8],
            "user_msgs": info["user_msgs"],
            "turns": info["turns"],
            "tools": info["tools_used"],
            "slash_cmds": info["slash_cmds"][:5],
        })

    # 生成原始数据报告
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
        "user_messages": [
            {
                "index": i,
                "content": m["content"][:500],
                "timestamp": m["timestamp"],
                "session_id": m["session_id"][:8],
            }
            for i, m in enumerate(user_messages)
        ],
        "assistant_summary": {
            "tool_usage": [
                {"tool": t, "count": c}
                for t, c in assistant_actions["tool_counts"].most_common(20)
            ],
            "file_hotspots": file_hotspots,
            "build_results": assistant_actions["build_results"][:20],
            "build_errors": [
                {"pattern": p, "count": c}
                for p, c in assistant_actions["build_errors"].most_common(10)
            ],
            "websearch_topics": [
                {"query": q, "count": c}
                for q, c in Counter(assistant_actions["websearch_topics"]).most_common(15)
            ],
        },
        "session_metrics": session_details,
        "previous_state": previous_state,
        "_new_state": {
            "last_analysis": datetime.now().isoformat(),
            "metrics_snapshot": current_metrics,
        },
    }

    return report


def main():
    parser = argparse.ArgumentParser(description="Claude Code Session JSONL 数据提取器")
    parser.add_argument("--session-dir", required=True, help="JSONL 文件目录")
    parser.add_argument("--project-root", required=True, help="项目根目录绝对路径")
    parser.add_argument("--since", default=None, help="增量分析起点（ISO 8601 时间戳）")
    parser.add_argument("--previous-state", default=None, help="上次分析状态文件路径")
    parser.add_argument("--output", default=None, help="输出文件路径（默认 stdout）")

    args = parser.parse_args()

    report = run_analysis(args)

    new_state = report.pop("_new_state", None)

    output_json = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)

        # 保存状态文件
        if new_state:
            state_path = args.output.replace(".json", ".state.json")
            history = []
            if args.previous_state and os.path.exists(args.previous_state):
                with open(args.previous_state, encoding="utf-8") as f:
                    old = json.load(f)
                    history = old.get("analysis_history", [])
            history.append({
                "date": new_state["last_analysis"],
                **new_state["metrics_snapshot"],
            })
            new_state["analysis_history"] = history[-20:]
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(new_state, f, ensure_ascii=False, indent=2)

        print(f"Raw data written to: {args.output}", file=sys.stderr)
        if new_state:
            print(f"State saved to: {args.output.replace('.json', '.state.json')}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
