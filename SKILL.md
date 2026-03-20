---
name: conversation-mining
description: Use when exporting, browsing, locating, or summarizing local Claude Code, Codex, or Antigravity conversation history from the current machine.
---

# Conversation Mining

## Overview

This skill helps recover and browse local AI conversation history from multiple local runtimes on the same machine.

It is best for:

- finding the original transcript behind a remembered conversation
- exporting conversations by date or recent-day window
- browsing conversations in a static local viewer
- generating a stable conversation reference for handoff to another AI
- inspecting AG task artifacts when Antigravity only leaves summaries plus local output files

## What It Reads

- Claude Code: `~/.claude/projects`, `~/.claude/history.jsonl`
- Codex: `~/.codex/sessions`, `~/.codex/history.jsonl`, `~/.codex/state_5.sqlite`
- Antigravity: `~/Library/Application Support/Antigravity/.../state.vscdb`
- Optional AG artifacts: `~/.gemini/antigravity/brain/<uuid>/`

## Quick Use

From this repository:

```bash
python3 convs.py
python3 convs.py --no-open
python3 convs.py --days 7
python3 convs.py --date 2026-03-19
```

Installed CLI:

```bash
conversation-mining --no-open
python3 -m conversation_mining --days 7
```

## Output

The tool writes:

- `exported_conversations/conversations.json`
- `exported_conversations/index.html`
- per-day Markdown transcript files

## Recommended Workflow

1. Export or refresh conversations with `python3 convs.py --no-open`
2. Open `exported_conversations/index.html`
3. Locate the target conversation
4. Use the viewer’s `Copy ref` or `Copy prompt`
5. Hand that reference to another AI if you want summarization or continuation

## AG Notes

Antigravity is currently summary-first, not guaranteed full-transcript-first.

When AG has local output artifacts, the viewer surfaces:

- brain workspace path
- `task.md`
- `implementation_plan.md`
- `walkthrough.md`
- `handoff.md`

## Known Limits

- AG transcript reconstruction is partial
- bookmark/tag/collection state lives in browser `localStorage`
- exported Markdown and references may contain absolute local paths
