# Install With Another AI

This file contains copy-paste prompts you can give to another AI agent so it installs `conversation-mining` for you.

Repository:

- SSH: `git@github.com:FairladyZ625/conversation-mining.git`
- HTTPS: `https://github.com/FairladyZ625/conversation-mining.git`

## Prompt for Claude Code / Codex

Copy this block to another coding agent:

```text
Please install the open-source tool `conversation-mining` on this machine from:

git@github.com:FairladyZ625/conversation-mining.git

Requirements:
1. Clone the repository into a reasonable local tools/workspace directory if it is not already present.
2. If it already exists, pull the latest changes instead of creating a duplicate.
3. Install it in editable mode with Python:
   python3 -m pip install -e .
4. Verify the installation by running:
   conversation-mining --no-open --days 1
5. Tell me:
   - where you cloned it
   - whether installation succeeded
   - where the generated viewer is located

Important constraints:
- Keep everything local on this machine.
- Do not upload or publish any exported conversation data.
- If SSH clone fails, fall back to:
  https://github.com/FairladyZ625/conversation-mining.git
```

## Prompt for Skill-Capable Agents

Use this when the target agent supports installing skills from git repositories or from a `SKILL.md` entry point:

```text
Please install the repository below as a local skill and also make the CLI available if possible:

git@github.com:FairladyZ625/conversation-mining.git

Skill entry point:
- SKILL.md

CLI entry point after install:
- conversation-mining

What I want:
1. Clone or update the repo locally.
2. Register/install the skill using SKILL.md if your runtime supports repo-based skill installation.
3. Also install the Python CLI in editable mode if supported:
   python3 -m pip install -e .
4. Verify by running:
   conversation-mining --no-open --days 1
5. Report back with:
   - install location
   - skill install status
   - CLI install status
   - output viewer path

Important:
- This is a local-only install.
- Do not export or upload any private conversation data anywhere.
```

## Prompt for a Generic Terminal AI

```text
Install `conversation-mining` locally from:

https://github.com/FairladyZ625/conversation-mining.git

Please:
1. Clone it to a sensible local directory.
2. Run:
   python3 -m pip install -e .
3. Verify with:
   conversation-mining --no-open --days 1
4. Tell me the install path and the generated viewer path.

Do not publish or upload any exported conversation data.
```
