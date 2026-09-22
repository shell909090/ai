import importlib.util
import json
import io
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "codex" / "codex_logbook.py"
SPEC = importlib.util.spec_from_file_location("codex_logbook", MODULE_PATH)
assert SPEC and SPEC.loader
logbook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(logbook)


class CodexLogbookTest(unittest.TestCase):
    def test_failure_command_runs_only_for_failed_summaries(self):
        for backend in ("opencode", "codex"):
            for summary in ("summary", ""):
                with self.subTest(backend=backend, summary=summary), \
                        patch.object(logbook, "SUMMARY_BACKEND", backend), \
                        patch.object(logbook, f"summarize_with_{backend}", return_value=(summary, None)), \
                        patch.object(logbook, "run_summary_failure_command") as command:
                    result = logbook.summarize("activity", None)
                    if summary:
                        self.assertEqual(result, summary)
                        command.assert_not_called()
                    else:
                        self.assertIn("empty summary", result)
                        self.assertIn("activity", result)
                        command.assert_called_once_with()

    def test_failure_command_configuration(self):
        for value in (None, "", "  ", ["unexpected"]):
            with self.subTest(value=value), \
                    patch.object(logbook, "CONFIG", {"on_summary_failure_command": value}), \
                    patch.object(logbook.subprocess, "run") as run, \
                    patch.object(logbook.sys, "stderr", io.StringIO()):
                logbook.run_summary_failure_command()
                run.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "notification"
            command = f"printf failure > {shlex.quote(str(output))}"
            with patch.object(logbook, "CONFIG", {"on_summary_failure_command": command}):
                logbook.run_summary_failure_command()
            self.assertEqual(output.read_text(), "failure")

    def test_failure_command_errors_do_not_prevent_logbook_writes(self):
        errors = (
            OSError("cannot start"),
            subprocess.TimeoutExpired("notify", 30),
            subprocess.CalledProcessError(1, "notify"),
        )
        for error in errors:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                transcript = root / "session.jsonl"
                transcript.write_text(json.dumps({
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "activity"},
                }) + "\n")
                payload = {"session_id": "test", "transcript_path": str(transcript)}
                with patch.object(logbook, "LOG_ROOT", root), \
                        patch.object(logbook, "CONFIG", {"on_summary_failure_command": "notify"}), \
                        patch.object(logbook, "SUMMARY_BACKEND", "opencode"), \
                        patch.object(logbook, "summarize_with_opencode", return_value=("", "backend failed")), \
                        patch.object(logbook.subprocess, "run", side_effect=error) as run, \
                        patch.object(logbook.sys, "stderr", io.StringIO()) as stderr:
                    self.assertEqual(logbook.process(payload), 0)
                    self.assertEqual(logbook.process(payload), 0)
                    run.assert_called_once_with(
                        ["/bin/sh", "-c", "notify"],
                        stdin=subprocess.DEVNULL, timeout=30, check=True,
                    )
                    self.assertIn("failure command failed", stderr.getvalue())
                saved = (root / "codex_test.md").read_text()
                self.assertIn("backend failed", saved)
                self.assertIn("activity", saved)
                self.assertEqual(logbook.latest_source_line(root / "codex_test.md"), 1)

    def test_postcompact_and_session_end_enqueue_without_processing_in_hook(self):
        for event in ("PostCompact", "SessionEnd"):
            payload = {"hook_event_name": event, "session_id": "session"}
            with self.subTest(event=event), \
                    patch.object(logbook.sys, "argv", ["codex_logbook.py"]), \
                    patch.object(logbook.sys, "stdin") as stdin, \
                    patch.object(logbook, "enqueue", return_value=0) as enqueue, \
                    patch.object(logbook, "process") as process:
                stdin.read.return_value = json.dumps(payload)
                self.assertEqual(logbook.main(), 0)
                enqueue.assert_called_once_with(payload)
                process.assert_not_called()

    def test_worker_processes_payload_without_reenqueuing(self):
        import base64

        payload = {"hook_event_name": "PostCompact", "session_id": "session"}
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        with patch.object(logbook.sys, "argv", ["codex_logbook.py", "--worker", encoded]), \
                patch.object(logbook, "process", return_value=0) as process, \
                patch.object(logbook, "enqueue") as enqueue:
            self.assertEqual(logbook.main(), 0)
            process.assert_called_once_with(payload)
            enqueue.assert_not_called()

    def test_safe_name(self):
        self.assertEqual(logbook.safe_name("../session id"), "session_id")
        self.assertEqual(logbook.safe_name("..."), "unknown-session")

    def test_extract_activity_is_incremental_and_deduplicates_messages(self):
        records = [
            {"type": "event_msg", "payload": {"type": "user_message", "message": "旧消息"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "目标"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "目标"}]}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "shell", "arguments": "pwd"}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "完成"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "session.jsonl"
            transcript.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8")
            activity, end = logbook.extract_activity(transcript, 1)

        self.assertEqual(end, 5)
        self.assertNotIn("旧消息", activity)
        self.assertEqual(activity.count("[用户] 目标"), 1)
        self.assertIn("[工具] shell: pwd", activity)
        self.assertIn("[助手] 完成", activity)

    def test_latest_source_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "log.md"
            path.write_text(
                "<!-- logbook-source-lines: 1-12; event: PostCompact -->\n"
                "<!-- logbook-source-lines: 13-40; event: SessionEnd -->\n",
                encoding="utf-8",
            )
            self.assertEqual(logbook.latest_source_line(path), 40)


if __name__ == "__main__":
    unittest.main()
