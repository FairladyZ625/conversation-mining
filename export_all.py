#!/usr/bin/env python3
"""
export_all.py - Unified AI conversation exporter
Usage: python3 export_all.py [--date YYYY-MM-DD] [--days N]
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OUTPUT_BASE = REPO_ROOT / "exported_conversations"
OUTPUT_BASE = DEFAULT_OUTPUT_BASE
INDEX_FILE = OUTPUT_BASE / "conversations.json"


def load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"generated_at": "", "conversations": []}


def save_index(index: dict):
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    index["generated_at"] = datetime.now().isoformat()
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def get_existing_ids(index: dict) -> set:
    return {c["session_id"] for c in index.get("conversations", [])}


def upsert_conversation(index: dict, conversation: dict):
    conversations = index.setdefault("conversations", [])
    for i, existing in enumerate(conversations):
        if existing.get("source") == conversation.get("source") and existing.get("session_id") == conversation.get("session_id"):
            conversations[i] = conversation
            return
    conversations.append(conversation)


def find_existing_conversation(index: dict, source: str, session_id: str) -> dict | None:
    for existing in index.get("conversations", []):
        if existing.get("source") == source and existing.get("session_id") == session_id:
            return existing
    return None


def make_conv_id(source: str, date: str, session_id: str) -> str:
    h = hashlib.md5(session_id.encode()).hexdigest()[:8]
    return f"{source}-{date.replace('-', '')}-{h}"


def sanitize_filename(s: str, max_len: int = 60) -> str:
    if not s:
        return "untitled"
    safe = ""
    for c in s:
        if c.isalnum() or c in ("-", "_", " ", ".", "，", "。"):
            safe += c
        elif c in ("/", "\\", ":", "*", "?", '"', "<", ">", "|", "\n"):
            safe += "_"
        else:
            safe += c
    return safe[:max_len].strip().rstrip(".")


def unique_path(out_dir: Path, fname_base: str) -> Path:
    fname = f"{fname_base}.md"
    out_path = out_dir / fname
    counter = 1
    while out_path.exists():
        fname = f"{fname_base}_{counter}.md"
        out_path = out_dir / fname
        counter += 1
    return out_path


def export_claude(date_str: str, existing_ids: set, index: dict) -> int:
    try:
        from lib.extract_claude import (
            find_sessions_by_date,
            extract_conversation,
            format_conversation,
            decode_project_name,
            _extract_subagent_summary,
        )
    except ImportError as e:
        print(f"  [Claude] Import error: {e}")
        return 0

    out_dir = OUTPUT_BASE / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = find_sessions_by_date(date_str)
    exported = 0

    for sess in sorted(sessions, key=lambda x: x.get("first_ts", "")):
        sid = sess["session_id"]
        messages = extract_conversation(sess["filepath"], target_date=date_str)
        if not messages:
            continue

        md = format_conversation(messages, sid, sess["project"], sess.get("first_ts", ""))
        first_user = next((m["text"][:40] for m in messages if m["role"] == "user"), "")
        first_user_full = next((m["text"] for m in messages if m["role"] == "user"), "")
        proj_abbr = sess["project"].split("-")[-1][:15] if sess.get("project") else "unknown"
        fname_base = sanitize_filename(f"claude_{proj_abbr}_{first_user}" if first_user else f"claude_{sid[:8]}")
        existing = find_existing_conversation(index, "claude", sid)
        if existing and existing.get("file"):
            out_path = OUTPUT_BASE / existing["file"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = unique_path(out_dir, fname_base)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)

        subagent_summary = _extract_subagent_summary(first_user_full) if sess.get("is_subagent") else ""
        title = subagent_summary or first_user or sid[:40]
        upsert_conversation(index, {
            "id": make_conv_id("claude", date_str, sid),
            "source": "claude",
            "date": date_str,
            "title": title,
            "project": decode_project_name(sess.get("project", "")),
            "session_id": sid,
            "file": f"{date_str}/{out_path.name}",
            "first_ts": sess.get("first_ts", ""),
            "is_subagent": bool(sess.get("is_subagent")),
            "parent_session_id": sess.get("parent_session_id", ""),
            "launch_prompt": first_user_full if sess.get("is_subagent") else "",
            "subagent_summary": subagent_summary,
            "user_msg_count": sum(1 for m in messages if m["role"] == "user"),
            "assistant_msg_count": sum(1 for m in messages if m["role"] == "assistant"),
            "messages": [
                {
                    "role": m["role"],
                    "text": m["text"],
                    **({"prompt": m.get("prompt", "")} if m.get("prompt") else {}),
                    **({"description": m.get("description", "")} if m.get("description") else {}),
                    **({"tool_use_id": m.get("tool_use_id", "")} if m.get("tool_use_id") else {}),
                }
                for m in messages
            ],
        })
        existing_ids.add(sid)
        exported += 1
        print(f"    ✓ [Claude] {title[:60]}")

    return exported


def export_codex(date_str: str, existing_ids: set, index: dict) -> int:
    try:
        from lib.extract_codex import (
            find_sessions_by_date,
            extract_conversation,
            format_conversation,
            load_thread_titles,
        )
    except ImportError as e:
        print(f"  [Codex] Import error: {e}")
        return 0

    out_dir = OUTPUT_BASE / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    titles = load_thread_titles()
    sessions = find_sessions_by_date(date_str)
    exported = 0

    for sid, fpath in sorted(sessions.items()):
        messages, meta = extract_conversation(fpath)
        if not messages:
            continue

        title = titles.get(sid, "")
        md = format_conversation(messages, sid, title, meta)
        safe_title = sanitize_filename(f"codex_{title}" if title else f"codex_{sid[:12]}")
        existing = find_existing_conversation(index, "codex", sid)
        if existing and existing.get("file"):
            out_path = OUTPUT_BASE / existing["file"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = unique_path(out_dir, safe_title)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)

        display_title = title or (messages[0]["text"][:50] if messages else sid[:40])
        upsert_conversation(index, {
            "id": make_conv_id("codex", date_str, sid),
            "source": "codex",
            "date": date_str,
            "title": display_title,
            "project": meta.get("cwd", "") if meta else "",
            "session_id": sid,
            "file": f"{date_str}/{out_path.name}",
            "user_msg_count": sum(1 for m in messages if m["role"] == "user"),
            "assistant_msg_count": sum(1 for m in messages if m["role"] == "assistant"),
            "messages": [{"role": m["role"], "text": m["text"]} for m in messages],
        })
        existing_ids.add(sid)
        exported += 1
        print(f"    ✓ [Codex] {display_title[:60]}")

    return exported


def export_antigravity(date_str: str, existing_ids: set, index: dict) -> int:
    try:
        from lib.extract_antigravity import find_sessions
    except ImportError as e:
        print(f"  [AG] Import error: {e}")
        return 0

    out_dir = OUTPUT_BASE / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = find_sessions(date_str)
    exported = 0

    for sess in sessions:
        sid = sess["session_id"]
        messages = sess.get("messages", [])
        title = sess.get("title", sid[:40])
        artifacts = sess.get("artifacts", [])
        brain_dir = sess.get("brain_dir", "")

        lines = [f"# {title}", "", f"- Session ID: `{sid}`", "- 来源: AntiGravity", f"- 日期: {date_str}"]
        if brain_dir:
            lines.append(f"- Brain dir: `{brain_dir}`")
        if artifacts:
            lines += ["", "## Artifacts", ""]
            for artifact in artifacts:
                artifact_title = artifact.get("title") or artifact.get("name") or "artifact"
                artifact_path = artifact.get("path", "")
                lines.append(f"- `{artifact.get('rel_path') or artifact.get('name')}`: {artifact_title}")
                if artifact_path:
                    lines.append(f"  - path: `{artifact_path}`")
        lines += ["", "---", ""]
        for msg in messages:
            label = "🧑 用户" if msg["role"] == "user" else "🤖 AntiGravity"
            lines += [f"## {label}", "", msg["text"], ""]
        md = "\n".join(lines)

        fname_base = sanitize_filename(f"ag_{title[:40]}")
        out_path = unique_path(out_dir, fname_base)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)

        upsert_conversation(index, {
            "id": make_conv_id("ag", date_str, sid),
            "source": "antigravity",
            "date": date_str,
            "title": title,
            "project": sess.get("project", ""),
            "session_id": sid,
            "file": f"{date_str}/{out_path.name}",
            "brain_dir": brain_dir,
            "artifacts": artifacts,
            "user_msg_count": sum(1 for m in messages if m["role"] == "user"),
            "assistant_msg_count": sum(1 for m in messages if m["role"] == "assistant"),
            "messages": messages,
        })
        exported += 1
        print(f"    ✓ [AG] {title[:60]}")

    return exported


def main():
    parser = argparse.ArgumentParser(description="Export AI conversations")
    parser.add_argument("--date", help="Date to export (YYYY-MM-DD), default: today")
    parser.add_argument("--days", type=int, default=1, help="Number of past days to export")
    parser.add_argument(
        "--output-dir",
        help=f"Directory for exported markdown/index data (default: {DEFAULT_OUTPUT_BASE})",
    )
    args = parser.parse_args()

    global OUTPUT_BASE, INDEX_FILE
    if args.output_dir:
        OUTPUT_BASE = Path(args.output_dir).expanduser().resolve()
        INDEX_FILE = OUTPUT_BASE / "conversations.json"

    if args.date:
        try:
            start_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"Invalid date: {args.date}")
            sys.exit(1)
    else:
        start_date = datetime.now()

    dates = [(start_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(args.days)]

    print("=" * 50)
    print("  Conversation Mining Exporter")
    print("=" * 50)

    index = load_index()
    existing_ids = get_existing_ids(index)
    print(f"  Existing conversations: {len(existing_ids)}\n")

    total = 0
    for index_pos, date_str in enumerate(dates):
        print(f"📅 {date_str}")
        total += export_claude(date_str, existing_ids, index)
        total += export_codex(date_str, existing_ids, index)
        # AntiGravity history currently comes from one unified local state snapshot,
        # not per-day archival folders. Export it once per run to avoid repeatedly
        # rewriting the same sessions across a multi-day backfill.
        if index_pos == 0:
            total += export_antigravity(date_str, existing_ids, index)

    save_index(index)
    print(f"\n{'=' * 40}")
    print(f"  Added: {total}")
    print(f"  Total: {len(index['conversations'])}")
    print(f"  Index: {INDEX_FILE}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    main()
