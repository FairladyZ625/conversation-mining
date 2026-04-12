#!/usr/bin/env python3
"""
conversation_mining.cli - export local AI conversations and build a static viewer
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
EXPORT_ALL = REPO_ROOT / "export_all.py"
VIEWER_TEMPLATE = PACKAGE_ROOT / "viewer.html"
DEFAULT_OUTPUT_BASE = REPO_ROOT / "exported_conversations"


def _json_for_html_script(value) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text.replace("</", "<\\/")


def run_export(days: int, date: str | None, output_dir: Path, markdown_dir: str | None) -> bool:
    cmd = [sys.executable, str(EXPORT_ALL), "--output-dir", str(output_dir)]
    if date:
        cmd += ["--date", date]
    if days > 1:
        cmd += ["--days", str(days)]
    if markdown_dir:
        cmd += ["--markdown-dir", markdown_dir]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return result.returncode == 0


def _content_fingerprint(conv: dict) -> str:
    """Generate a fingerprint for dedup: title + first user messages."""
    title = (conv.get("title") or "").strip().lower()[:120]
    msgs = conv.get("messages", [])
    user_texts = []
    for m in msgs:
        if m.get("role") == "user":
            text = (m.get("text") or m.get("content") or "").strip()[:150]
            if text:
                user_texts.append(text)
        if len(user_texts) >= 3:
            break
    payload = title + "|" + "|".join(user_texts)
    return payload


def dedup_conversations(conversations: list) -> list:
    """Remove content-duplicate conversations, keeping the most complete version.

    Dedup criteria: conversations with the same content fingerprint
    (title + first 3 user messages) are considered duplicates.
    Keep the version with the most messages (most complete transcript).
    """
    groups: dict[str, list[dict]] = {}
    for conv in conversations:
        fp = _content_fingerprint(conv)
        if not fp or fp == "|":
            # No meaningful content — keep as-is (unique)
            continue
        groups.setdefault(fp, []).append(conv)

    # Build set of IDs to remove
    remove_ids: set[str] = set()
    for fp, group in groups.items():
        if len(group) <= 1:
            continue
        # Sort by completeness: most messages first, then longest title
        group.sort(
            key=lambda c: (
                (c.get("user_msg_count") or 0) + (c.get("assistant_msg_count") or 0),
                len(c.get("title") or ""),
            ),
            reverse=True,
        )
        # Keep the first (most complete), mark rest for removal
        for dup in group[1:]:
            remove_ids.add(dup.get("id", ""))

    if remove_ids:
        print(f"  去重: 移除 {len(remove_ids)} 条重复会话")

    return [c for c in conversations if c.get("id", "") not in remove_ids]


def build_html(output_dir: Path) -> bool:
    conversations_json = output_dir / "conversations.json"
    index_html = output_dir / "index.html"
    if not VIEWER_TEMPLATE.exists():
        print(f"Error: viewer template not found at {VIEWER_TEMPLATE}")
        return False
    if not conversations_json.exists():
        print(f"Error: conversations.json not found at {conversations_json}")
        return False

    html = VIEWER_TEMPLATE.read_text(encoding="utf-8")
    data = json.loads(conversations_json.read_text(encoding="utf-8"))

    # conversations.json is already deduped by export_all.py --dedup.
    # Apply viewer-level dedup as a safety net for any remaining duplicates.
    all_convs = data.get("conversations", [])
    deduped = dedup_conversations(all_convs)

    # Only embed the conversation index (metadata without messages) inline.
    # Messages are loaded on-demand per conversation to avoid bloating the HTML.
    index = []
    for conv in deduped:
        index.append({key: value for key, value in conv.items() if key != "messages"})

    html = html.replace(
        '<script type="application/json" id="conv-index">[]</script>',
        f'<script type="application/json" id="conv-index">{_json_for_html_script(index)}</script>',
    )
    # Leave conv-messages empty — viewer loads messages on demand via fetch

    output_dir.mkdir(parents=True, exist_ok=True)
    index_html.write_text(html, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description="Export AI conversations and build the static viewer")
    parser.add_argument("--days", type=int, default=1, help="Number of past days to export (default: 1)")
    parser.add_argument("--date", help="Specific date to export (YYYY-MM-DD)")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_BASE),
        help=f"Directory for exported data (default: {DEFAULT_OUTPUT_BASE})",
    )
    parser.add_argument("--markdown-dir", help="Directory for human-readable markdown transcripts")
    parser.add_argument("--no-open", action="store_true", help="Build the viewer without opening it")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()

    print("Exporting conversations...")
    ok = run_export(args.days, args.date, output_dir, args.markdown_dir)
    if not ok:
        print("Export finished with errors; continuing to build the viewer.")

    print("Building viewer...")
    if not build_html(output_dir):
        sys.exit(1)

    conversations_json = output_dir / "conversations.json"
    total = 0
    if conversations_json.exists():
        total = len(json.loads(conversations_json.read_text(encoding="utf-8")).get("conversations", []))

    index_html = output_dir / "index.html"
    print(f"Done: {total} conversations -> {index_html}")

    if not args.no_open:
        # Start a local HTTP server so the viewer can fetch conversations.json
        # (browsers block fetch from file:// due to CORS)
        import http.server
        import socket

        def _find_free_port():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                return s.getsockname()[1]

        port = _find_free_port()
        # Start server in background process
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=str(output_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}/index.html"
        print(f"Serving at {url}  (PID {server_proc.pid})")
        os.system(f'open "{url}"')
