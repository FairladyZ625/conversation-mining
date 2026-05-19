import json
import tempfile
import unittest
from pathlib import Path

import export_all
import lib.extract_claude as extract_claude


class ClaudeResumeExportTest(unittest.TestCase):
    def test_existing_resumed_session_is_updated_with_full_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            project_dir = tmp_path / "projects" / "-Users-lizeyu-Projects-coding-agent-harness"
            project_dir.mkdir(parents=True)
            session_id = "resume-session"
            session_file = project_dir / f"{session_id}.jsonl"
            rows = [
                {
                    "type": "user",
                    "timestamp": "2026-05-18T10:00:00.000Z",
                    "message": {"role": "user", "content": "first day prompt"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-05-18T10:01:00.000Z",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "first day answer"}]},
                },
                {
                    "type": "user",
                    "timestamp": "2026-05-19T10:00:00.000Z",
                    "message": {"role": "user", "content": "resumed prompt"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-05-19T10:01:00.000Z",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "resumed answer"}]},
                },
            ]
            session_file.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            original_projects_dir = extract_claude.PROJECTS_DIR
            extract_claude.PROJECTS_DIR = tmp_path / "projects"
            try:
                index = {
                    "conversations": [
                        {
                            "id": "claude-20260518-existing",
                            "source": "claude",
                            "date": "2026-05-18",
                            "session_id": session_id,
                            "title": "old title",
                            "messages": [{"role": "user", "text": "first day prompt"}],
                            "_content_hash": "old",
                        }
                    ]
                }
                existing_ids = export_all.get_existing_ids(index)

                exported = export_all.export_claude("2026-05-19", existing_ids, index)

                self.assertEqual(exported, 1)
                self.assertEqual(len(index["conversations"]), 1)
                conversation = index["conversations"][0]
                self.assertEqual(conversation["id"], "claude-20260518-existing")
                self.assertEqual(conversation["date"], "2026-05-18")
                self.assertEqual(conversation["created_at"], "2026-05-18T10:00:00.000Z")
                self.assertEqual(conversation["last_active_at"], "2026-05-19T10:01:00.000Z")
                self.assertEqual(conversation["user_msg_count"], 2)
                self.assertEqual(conversation["assistant_msg_count"], 2)
                self.assertTrue(conversation["_dirty"])
                self.assertIn("resumed prompt", [message["text"] for message in conversation["messages"]])
            finally:
                extract_claude.PROJECTS_DIR = original_projects_dir


if __name__ == "__main__":
    unittest.main()
