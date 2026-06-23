#!/usr/bin/env python3
"""
zCode 会话提取工具
读取 ~/.zcode/cli/rollout/model-io-sess_*.jsonl，取 messageCount 最大的那一行作为完整会话还原。

zCode 的 rollout jsonl 每行是一个 model_io turn，每行都把历史消息完整重发一遍（messagesKind=full），
所以取 messageCount 最大的那一行就是整个会话的最终状态。
"""

import json
import re
from datetime import datetime
from pathlib import Path

ZCODE_DIR = Path.home() / ".zcode"
ROLLOUT_DIR = ZCODE_DIR / "cli" / "rollout"


def _content_to_text(content) -> str:
    """把 message.content 统一成纯文本字符串。

    zCode 消息 content 有两种形态：
    - str：直接是正文
    - list：[{type: "reasoning"|"text"|"tool_use"|"tool_result", ...}]，拼接各块文本
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "reasoning":
                # reasoning 块单独保留为 blockquote，不混入正文
                text = block.get("text", "").strip()
                if text:
                    parts.append(f"> [thinking] {text}")
            elif btype == "tool_use":
                name = block.get("name", "tool")
                raw_input = block.get("input", {})
                # 把 input 压成单行预览
                input_preview = json.dumps(raw_input, ensure_ascii=False)
                if len(input_preview) > 200:
                    input_preview = input_preview[:200] + "…"
                parts.append(f"[tool_use: {name}] {input_preview}")
            elif btype == "tool_result":
                rc = block.get("content", "")
                if isinstance(rc, list):
                    rc = " ".join(
                        b.get("text", "") for b in rc if isinstance(b, dict)
                    )
                parts.append(f"[tool_result] {rc}")
        return "\n".join(p for p in parts if p)
    # 其它类型退化为字符串
    return str(content)


def _extract_zcode_messages(raw_messages: list) -> list[dict]:
    """把 zCode 原始 messages 转成 conversation-mining 的 {role, text} schema。

    丢弃 system 消息（prompt），保留 user / assistant / tool。
    tool 角色保留 tool name 信息，方便 viewer 展示。
    """
    out = []
    for m in raw_messages:
        role = m.get("role", "")
        if role == "system":
            continue
        text = _content_to_text(m.get("content"))
        # 跳过注入的 system-reminder user 消息（不是真实用户输入）
        if role == "user" and text.lstrip().startswith("<system-reminder>"):
            continue
        entry = {"role": role, "text": text}
        if role == "tool":
            tool_name = m.get("toolName", "")
            if tool_name:
                entry["text"] = f"[{tool_name}]\n{text}"
        out.append(entry)
    return out


def _first_real_user_text(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") == "user" and m.get("text", "").strip():
            return m["text"]
    return ""


def _strip_system_reminder(text: str) -> str:
    """从用户消息里去掉嵌入的 <system-reminder>...</system-reminder> 段。"""
    return re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.DOTALL).strip()


def _reconstruct_messages(turns: list[dict]) -> tuple[list[dict], dict]:
    """从一组 turn 里重建完整消息序列。

    zCode rollout jsonl 用滚动上下文窗口（窗口固定 64 条）：
    - messagesKind=full, messageOffset=0：窗口 [0, 64)，但早期 messageCount<64 时窗口=实际长度
    - messagesKind=tail, messageOffset=k：窗口 [k, k+64)

    要重建完整 [0, messageCount) 历史，需要贪心地用多个窗口拼接覆盖：
    - 从 offset=0 的窗口取 [0, 64)
    - 再从 offset=64 的窗口取 [64, 128)
    - 再从 offset=128 的窗口取 [128, messageCount)
    每个 turn 的 messageOffset 决定它窗口的起点。

    返回 (merged_messages, last_turn)。last_turn 用于取时间戳。
    """
    if not turns:
        return [], {}

    last_turn = turns[-1]
    final_count = last_turn.get("request", {}).get("messageCount", 0)
    if final_count <= 0:
        final_count = max((t.get("request", {}).get("messageCount", 0) for t in turns), default=0)

    # 每个窗口：(offset, messages_list)。按 offset 升序。
    windows = []
    for turn in turns:
        req = turn.get("request", {})
        offset = req.get("messageOffset", 0)
        msgs = req.get("messages", [])
        if not msgs:
            continue
        windows.append((offset, msgs))
    windows.sort(key=lambda w: w[0])

    if not windows:
        return [], last_turn

    # 贪心覆盖 [0, final_count)
    merged = [None] * final_count
    covered = 0
    i = 0
    while covered < final_count and i < len(windows):
        offset, msgs = windows[i]
        # 这个窗口覆盖 [offset, offset+len(msgs))，取与尚未覆盖部分的重叠
        for j, m in enumerate(msgs):
            pos = offset + j
            if 0 <= pos < final_count and merged[pos] is None:
                merged[pos] = m
                covered += 1
        i += 1
        # 优化：如果当前窗口 offset 已经 > covered，说明有 gap，后面窗口也补不上
        # （理论上不该发生，因为窗口密集重叠）

    # 去掉 None（覆盖不到的空洞）
    result = [m for m in merged if m is not None]
    return result, last_turn


def _parse_turns(jsonl_path: Path) -> list[dict]:
    """读取 jsonl 的所有 turn。"""
    turns = []
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turns.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    except (OSError, IOError):
        pass
    return turns


def extract_session(jsonl_path) -> dict | None:
    """从单个 jsonl 文件提取一个 zCode 会话，返回 conversation-mining schema。

    返回 None 表示该文件无法解析或没有有效消息。
    """
    jsonl_path = Path(jsonl_path)
    turns = _parse_turns(jsonl_path)
    if not turns:
        return None

    raw_messages, last_turn = _reconstruct_messages(turns)
    if not raw_messages:
        return None

    messages = _extract_zcode_messages(raw_messages)
    if not messages:
        return None

    # sessionId / 时间从第一个 turn 取（更稳定，last_turn 可能是 tail）
    first_turn = turns[0]
    session_id = first_turn.get("sessionId", "") or jsonl_path.stem
    # 文件名形如 model-io-sess_<uuid>.jsonl，去掉前缀
    if session_id.startswith("model-io-"):
        session_id = session_id[len("model-io-"):]
    elif not session_id.startswith("sess_"):
        # 退回到从文件名提取
        m = re.search(r"(sess_[a-f0-9\-]+)", jsonl_path.stem)
        if m:
            session_id = m.group(1)

    started_at = first_turn.get("startedAt", "") or ""
    # 最后活动时间用最后一个 turn 的 completedAt
    completed_at = last_turn.get("completedAt", "") or last_turn.get("startedAt", "") or started_at
    # startedAt 是 ISO 带 Z，直接取前 10 位当日期
    date_str = (started_at[:10] if started_at else "") or datetime.now().strftime("%Y-%m-%d")

    # 模型信息从 last_turn 取（反映最新使用的模型）
    model_info = last_turn.get("model", {}) or {}
    model_id = model_info.get("modelId", "")
    provider = model_info.get("providerId", "")

    first_user_raw = _first_real_user_text(messages)
    first_user_clean = _strip_system_reminder(first_user_raw)
    title = (first_user_clean or session_id)[:60]

    # workspacePath：zCode rollout 没有直接字段，留空，让 viewer 按 source 分组
    return {
        "source": "zcode",
        "session_id": session_id,
        "date": date_str,
        "created_at": started_at,
        "updated_at": completed_at,
        "last_active_at": completed_at or started_at,
        "title": title,
        "project": "",
        "model": model_id,
        "provider": provider,
        "user_msg_count": sum(1 for m in messages if m["role"] == "user"),
        "assistant_msg_count": sum(1 for m in messages if m["role"] == "assistant"),
        "messages": messages,
    }


def find_sessions_by_date(target_date: str) -> dict:
    """找到某天活跃的所有 zCode 会话文件。

    target_date 格式: YYYY-MM-DD
    策略：jsonl 里每行的 startedAt 带 ISO 时间，匹配 target_date 即可。
    返回 {session_id: file_path}
    """
    found = {}
    if not ROLLOUT_DIR.exists():
        return found

    for jsonl_path in ROLLOUT_DIR.glob("model-io-sess_*.jsonl"):
        turns = _parse_turns(jsonl_path)
        if not turns:
            continue
        # 检查这个会话的任意 turn 是否落在目标日期
        hit = False
        for turn in turns:
            started = turn.get("startedAt", "") or ""
            if started.startswith(target_date):
                hit = True
                break
            completed = turn.get("completedAt", "") or ""
            if completed.startswith(target_date):
                hit = True
                break
        if not hit:
            continue
        session_id = turns[0].get("sessionId", "") or jsonl_path.stem
        if session_id.startswith("model-io-"):
            session_id = session_id[len("model-io-"):]
        found[session_id] = str(jsonl_path)

    return found


def find_all_sessions() -> dict:
    """返回所有 zCode 会话文件 {session_id: file_path}，不限日期。"""
    found = {}
    if not ROLLOUT_DIR.exists():
        return found
    for jsonl_path in ROLLOUT_DIR.glob("model-io-sess_*.jsonl"):
        turns = _parse_turns(jsonl_path)
        if not turns:
            continue
        session_id = turns[0].get("sessionId", "") or jsonl_path.stem
        if session_id.startswith("model-io-"):
            session_id = session_id[len("model-io-"):]
        found[session_id] = str(jsonl_path)
    return found
