"""Unit tests for tgbot helper functions and command flow."""

from __future__ import annotations

import configparser
import contextlib
import io
import json
import queue
import tempfile
import unittest
from collections import deque
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError, URLError

import tgbot


class FakeSessionLog:
    """Collect session log events in memory."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append(self, event: str, **fields) -> None:
        self.events.append((event, fields))


def make_config(text: str) -> configparser.ConfigParser:
    """Parse a config snippet into a ConfigParser."""
    cfg = configparser.ConfigParser()
    cfg.read_string(text)
    return cfg


class CommandHelpersTest(unittest.TestCase):
    """Cover Telegram command and prompt helper functions."""

    def test_normalize_and_build_tg_commands(self) -> None:
        commands = tgbot._build_tg_commands(
            [
                {"name": "/Deploy-App", "description": " Deploy now "},
                {"name": "Deploy-App", "description": "Duplicate should be skipped"},
                {"name": "bad command"},
                {"name": "status", "input": {"hint": " Show current status "}},
            ]
        )

        self.assertEqual(
            commands,
            [
                {"command": "deploy_app", "description": "Deploy now"},
                {"command": "status", "description": "Show current status"},
            ],
        )

    def test_prompt_record_and_log_fields(self) -> None:
        prompt = tgbot._prompt_record(
            text="hello",
            reply_chat_id=123,
            source="telegram",
            from_id=5,
            username="alice",
            chat_type="private",
            message_id=9,
            extra={"cron_expr": "* * * * *"},
        )

        self.assertEqual(prompt["cron_expr"], "* * * * *")
        self.assertEqual(
            tgbot._prompt_log_fields(prompt),
            {
                "text": "hello",
                "chat_id": 123,
                "source": "telegram",
                "from_id": 5,
                "username": "alice",
                "chat_type": "private",
                "message_id": 9,
            },
        )

    def test_state_dir_prefers_xdg_state_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(tgbot.os.environ, {"XDG_STATE_HOME": tmpdir}, clear=False):
                self.assertEqual(tgbot._state_dir(), Path(tmpdir) / "tgbot")


class ConfigAndApiTest(unittest.TestCase):
    """Cover config loading and Telegram API wrapper behavior."""

    def test_load_config_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.ini"
            path.write_text("[bot]\ntoken = token\nchat_id = 1\n", encoding="utf-8")

            cfg = tgbot.load_config(path)

        self.assertEqual(cfg["bot"]["token"], "token")

    def test_load_config_rejects_missing_or_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing.ini"
            with self.assertRaises(SystemExit):
                tgbot.load_config(missing)

            bad = Path(tmpdir) / "bad.ini"
            bad.write_text("[other]\nvalue = 1\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                tgbot.load_config(bad)

            empty_token = Path(tmpdir) / "empty.ini"
            empty_token.write_text("[bot]\nchat_id = 1\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                tgbot.load_config(empty_token)

    def test_api_call_success_and_http_error(self) -> None:
        response = mock.MagicMock()
        response.read.return_value = b'{"ok": true, "result": 1}'
        response.__enter__.return_value = response

        with mock.patch("tgbot.urlopen", return_value=response):
            self.assertEqual(tgbot.api_call("token", "getMe"), {"ok": True, "result": 1})

        http_error = HTTPError(
            url="https://example.com",
            code=500,
            msg="boom",
            hdrs=None,
            fp=io.BytesIO(b'{"ok": false, "description": "bad"}'),
        )
        with mock.patch("tgbot.urlopen", side_effect=http_error):
            self.assertEqual(
                tgbot.api_call("token", "getMe"),
                {"ok": False, "description": "bad"},
            )

    def test_api_call_retries_network_errors(self) -> None:
        response = mock.MagicMock()
        response.read.return_value = b'{"ok": true}'
        response.__enter__.return_value = response

        with (
            mock.patch("tgbot.urlopen", side_effect=[URLError("boom"), response]),
            mock.patch("tgbot.time.sleep") as sleep,
        ):
            result = tgbot.api_call("token", "getMe", retries=1)

        self.assertEqual(result, {"ok": True})
        sleep.assert_called_once()

    def test_api_call_exits_after_final_network_error(self) -> None:
        with mock.patch("tgbot.urlopen", side_effect=URLError("boom")):
            with self.assertRaises(SystemExit):
                tgbot.api_call("token", "getMe", retries=0)


class SessionLogTest(unittest.TestCase):
    """Cover JSONL session logging behavior."""

    def test_session_log_appends_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_log = tgbot.SessionLog(Path(tmpdir), "sess:1")
            session_log.append("incoming_prompt", text="hello")

            lines = session_log.path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["event"], "incoming_prompt")
            self.assertEqual(record["text"], "hello")
            self.assertIn("time", record)


class CronTest(unittest.TestCase):
    """Cover cron parsing and matching."""

    def test_parse_crontab(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "crontab.md"
            path.write_text(
                "## 0 9 * * *\nMorning check\n\n## 30 18 * * 1-5\nEvening wrap\n",
                encoding="utf-8",
            )

            jobs = tgbot.parse_crontab(path)

        self.assertEqual(
            jobs,
            [
                {"expr": "0 9 * * *", "prompt": "Morning check"},
                {"expr": "30 18 * * 1-5", "prompt": "Evening wrap"},
            ],
        )

    def test_cron_matches(self) -> None:
        dt = datetime(2026, 4, 24, 9, 0)
        self.assertTrue(tgbot._cron_matches("0 9 * * 5", dt))
        self.assertFalse(tgbot._cron_matches("1 9 * * 5", dt))
        self.assertFalse(tgbot._cron_matches("* * *", dt))
        self.assertTrue(tgbot._cron_field_matches("*/15", 30, 0, 59))
        self.assertTrue(tgbot._cron_field_matches("10-20", 15, 0, 59))
        self.assertTrue(tgbot._cron_field_matches("7", 7, 0, 59))


class GroupMessageTest(unittest.TestCase):
    """Cover mention handling and prompt extraction."""

    def test_strip_mentions_and_address_detection(self) -> None:
        text = "run @MyBot status"
        entities = [{"type": "mention", "offset": 4, "length": 6}]

        self.assertEqual(
            tgbot._bot_mention_ranges(text, entities, "MyBot"),
            [(8, 20)],
        )
        self.assertEqual(tgbot._strip_bot_mentions(text, entities, "MyBot"), "run status")
        self.assertTrue(
            tgbot._addressed_in_group(
                {"text": text, "entities": entities},
                bot_id=99,
                bot_username="MyBot",
            )
        )

    def test_group_reply_counts_as_addressed(self) -> None:
        msg = {"reply_to_message": {"from": {"id": 42}}, "text": "continue"}
        self.assertTrue(tgbot._addressed_in_group(msg, bot_id=42, bot_username="bot"))

    def test_extract_prompt_filters_allow_users_and_group_addressing(self) -> None:
        update = {
            "message": {
                "message_id": 7,
                "text": "please @MyBot deploy",
                "entities": [{"type": "mention", "offset": 7, "length": 6}],
                "chat": {"id": -100, "type": "group"},
                "from": {"id": 11, "username": "alice"},
            }
        }

        prompt = tgbot._extract_prompt(update, {11}, bot_id=99, bot_username="MyBot")
        denied = tgbot._extract_prompt(update, {12}, bot_id=99, bot_username="MyBot")
        no_address = tgbot._extract_prompt(
            {
                "message": {
                    "text": "plain text",
                    "chat": {"id": -100, "type": "group"},
                    "from": {"id": 11},
                }
            },
            {11},
            bot_id=99,
            bot_username="MyBot",
        )

        self.assertEqual(prompt["text"], "please deploy")
        self.assertEqual(prompt["reply_chat_id"], -100)
        self.assertIsNone(denied)
        self.assertIsNone(no_address)


class ConfigHelpersTest(unittest.TestCase):
    """Cover config-derived helper behavior."""

    def test_load_allow_users(self) -> None:
        cfg = make_config("[bot]\nallow_users = 1, 2,3\n")
        self.assertEqual(tgbot._load_allow_users(cfg, 9), {1, 2, 3})
        cfg = make_config("[bot]\nchat_id = 9\n")
        self.assertEqual(tgbot._load_allow_users(cfg, 9), {9})

    def test_owner_and_command_loaders(self) -> None:
        cfg = make_config("[bot]\nchat_id = 9\n[acp]\ncommand = agent --acp\n")
        args = SimpleNamespace(agent_cmd=None)
        self.assertEqual(tgbot._load_owner_chat_id(cfg), 9)
        self.assertEqual(tgbot._load_acp_command(args, cfg), "agent --acp")

        with self.assertRaises(SystemExit):
            tgbot._load_owner_chat_id(make_config("[bot]\ntoken = token\n"))

        with self.assertRaises(SystemExit):
            tgbot._load_acp_command(SimpleNamespace(agent_cmd=None), make_config("[bot]\nchat_id = 9\n"))

    def test_resolve_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = make_config("[acp]\ncwd = /unused\n")
            args = SimpleNamespace(cwd=tmpdir)
            path, cwd = tgbot._resolve_cwd(args, cfg)
            self.assertEqual(path, Path(tmpdir).resolve())
            self.assertEqual(cwd, str(Path(tmpdir).resolve()))

    def test_resolve_cwd_rejects_missing_directory(self) -> None:
        cfg = make_config("[acp]\ncwd = /unused\n")
        args = SimpleNamespace(cwd="/definitely/missing/path")
        with self.assertRaises(SystemExit):
            tgbot._resolve_cwd(args, cfg)

    def test_load_cron_jobs_returns_empty_for_missing_file(self) -> None:
        cfg = make_config("[cron]\nfile = /definitely/missing.md\n")
        self.assertEqual(tgbot._load_cron_jobs(cfg), [])


class PermissionHandlingTest(unittest.TestCase):
    """Cover ACP permission selection logic."""

    def test_parse_permission_reply(self) -> None:
        options = [
            {"optionId": "allow", "kind": "allow", "name": "Allow once"},
            {"optionId": "deny", "kind": "deny", "name": "Deny"},
        ]

        self.assertEqual(tgbot._parse_permission_reply("y", options), (True, "allow", False))
        self.assertEqual(tgbot._parse_permission_reply("n", options), (True, None, False))
        self.assertEqual(tgbot._parse_permission_reply("2", options), (True, "deny", False))
        self.assertEqual(tgbot._parse_permission_reply("9", options), (False, None, True))
        self.assertEqual(tgbot._parse_permission_reply("later", options), (False, None, False))
        self.assertEqual(
            tgbot._default_permission_option([{"optionId": "deny", "kind": "deny", "name": "Deny"}]),
            "deny",
        )

    def test_permission_request_text_includes_tool_call(self) -> None:
        text = tgbot._permission_request_text(
            {"toolCall": {"toolCallId": "call-1"}},
            [{"optionId": "allow", "kind": "allow", "name": "Allow"}],
        )
        self.assertIn("工具: call-1", text)
        self.assertIn("1) Allow", text)

    def test_handle_permission_yolo_uses_allow_option(self) -> None:
        option_id, offset = tgbot._handle_permission(
            "token",
            1,
            {"options": [{"optionId": "allow", "kind": "allow", "name": "Allow"}]},
            True,
            5,
        )
        self.assertEqual(option_id, "allow")
        self.assertEqual(offset, 5)

    def test_handle_permission_interactive_retries_invalid_number(self) -> None:
        calls: list[tuple[str, dict]] = []

        def fake_api_call(token: str, method: str, params: dict | None = None, retries: int = 0):
            calls.append((method, params or {}))
            if method == "sendMessage":
                return {"ok": True}
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 8,
                        "message": {
                            "chat": {"id": 100},
                            "text": "9",
                        },
                    },
                    {
                        "update_id": 9,
                        "message": {
                            "chat": {"id": 100},
                            "text": "y",
                        },
                    },
                ],
            }

        with mock.patch("tgbot.api_call", side_effect=fake_api_call):
            option_id, offset = tgbot._handle_permission(
                "token",
                100,
                {"options": [{"optionId": "allow", "kind": "allow", "name": "Allow"}]},
                False,
                8,
            )

        self.assertEqual(option_id, "allow")
        self.assertEqual(offset, 10)
        self.assertEqual(calls[0][0], "sendMessage")
        self.assertEqual(calls[2][1]["text"], "⚠️ 请回复 y/n 或选项编号")


class TelegramReplyTest(unittest.TestCase):
    """Cover streamed Telegram reply behavior."""

    def test_reply_updates_and_splits_long_messages(self) -> None:
        calls: list[tuple[str, dict]] = []
        message_ids = iter([10, 11])

        def fake_api_call(token: str, method: str, params: dict | None = None, retries: int = 0):
            calls.append((method, params or {}))
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": next(message_ids)}}
            return {"ok": True, "result": {}}

        with mock.patch("tgbot.api_call", side_effect=fake_api_call):
            reply = tgbot.TelegramReply("token", 3, max_text=10)
            reply.update("123456789012345")
            reply.finalize("123456789012345")

        self.assertEqual(calls[0][0], "sendMessage")
        self.assertEqual(calls[1][0], "editMessageText")
        self.assertEqual(calls[2][0], "sendMessage")
        self.assertEqual(calls[3][1]["text"], "012345")


class CommandSyncTest(unittest.TestCase):
    """Cover Telegram command synchronization and prompt buffering."""

    def test_sync_telegram_commands_registers_and_clears(self) -> None:
        calls: list[str] = []
        session_log = FakeSessionLog()
        commands_state = {"signature": None, "registered": False, "current": []}

        def fake_api_call(token: str, method: str, params: dict | None = None, retries: int = 0):
            calls.append(method)
            return {"ok": True, "result": {}}

        with mock.patch("tgbot.api_call", side_effect=fake_api_call):
            tgbot._sync_telegram_commands(
                "token",
                [{"name": "status", "description": "Show status"}],
                commands_state,
                session_log,
            )
            tgbot._sync_telegram_commands("token", [], commands_state, session_log)

        self.assertEqual(calls, ["setMyCommands", "deleteMyCommands"])
        self.assertEqual(
            [event for event, _fields in session_log.events],
            ["commands_registered", "commands_cleared"],
        )

    def test_enqueue_prompt_buffers_and_drops_when_full(self) -> None:
        pending_prompts = deque(
            [
                {"reply_chat_id": 1, "text": str(index), "source": "telegram"}
                for index in range(tgbot.MAX_PENDING_PROMPTS)
            ]
        )
        session_log = FakeSessionLog()
        prompt = {
            "reply_chat_id": 9,
            "text": "later",
            "source": "telegram",
            "from_id": 2,
            "username": "bob",
        }

        with mock.patch("tgbot.api_call", return_value={"ok": True}) as api_call:
            accepted = tgbot._enqueue_prompt("token", pending_prompts, session_log, prompt)

        self.assertFalse(accepted)
        api_call.assert_called_once()
        self.assertEqual(session_log.events[0][0], "prompt_dropped")

    def test_prompt_session_payload_keeps_extra_fields(self) -> None:
        acp = SimpleNamespace(session_id="sess-1")
        prompt = tgbot._prompt_record(
            text="run",
            reply_chat_id=5,
            source="cron",
            extra={"cron_index": 2},
        )

        payload = tgbot._prompt_session_payload(acp, prompt, 7)

        self.assertEqual(payload["turn_id"], 7)
        self.assertEqual(payload["session_id"], "sess-1")
        self.assertEqual(payload["cron_index"], 2)


class AcpSessionTest(unittest.TestCase):
    """Cover ACP session update helpers."""

    def test_start_new_session(self) -> None:
        fake_proc = SimpleNamespace(
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            kill=mock.Mock(),
        )

        with (
            mock.patch("tgbot.subprocess.Popen", return_value=fake_proc),
            mock.patch.object(
                tgbot.AcpSession,
                "_recv",
                return_value={"id": 0, "result": {"agentInfo": {"name": "agent"}}},
            ),
            mock.patch.object(
                tgbot.AcpSession,
                "_await_response",
                return_value={"id": 1, "result": {"sessionId": "sess-new"}},
            ),
        ):
            session = tgbot.AcpSession.start("agent --acp", "/work")

        self.assertEqual(session.session_id, "sess-new")
        fake_proc.kill.assert_not_called()

    def test_start_loaded_session_rejects_error(self) -> None:
        fake_proc = SimpleNamespace(
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            kill=mock.Mock(),
        )

        with (
            mock.patch("tgbot.subprocess.Popen", return_value=fake_proc),
            mock.patch.object(
                tgbot.AcpSession,
                "_recv",
                return_value={"id": 0, "result": {"agentInfo": {"name": "agent"}}},
            ),
            mock.patch.object(
                tgbot.AcpSession,
                "_await_response",
                return_value={"id": 1, "error": {"message": "bad session"}},
            ),
        ):
            with self.assertRaises(RuntimeError):
                tgbot.AcpSession.start("agent --acp", "/work", session_id="sess-old")

        fake_proc.kill.assert_called_once()

    def test_close_kills_process_after_wait_failure(self) -> None:
        proc = SimpleNamespace(
            stdin=SimpleNamespace(close=mock.Mock()),
            wait=mock.Mock(side_effect=RuntimeError("boom")),
            kill=mock.Mock(),
        )
        session = tgbot.AcpSession()
        session._proc = proc

        session.close()

        proc.kill.assert_called_once()

    def test_prompt_handles_agent_requests_and_notifications(self) -> None:
        session = tgbot.AcpSession()
        session.session_id = "sess-1"
        reply = mock.Mock()
        session._reply = reply
        session._request = mock.Mock(return_value=7)
        msg_q: queue.Queue = queue.Queue()
        for item in [
            {"id": 99, "method": "session/request_permission", "params": {"options": []}},
            {
                "method": "session/update",
                "params": {
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"text": "hello\n"},
                    }
                },
            },
            {
                "method": "session/update",
                "params": {
                    "update": {
                        "sessionUpdate": "tool_call",
                        "title": "search",
                        "kind": "tool",
                        "locations": [{"path": "/tmp/a"}],
                    }
                },
            },
            {"id": 7, "result": {}},
        ]:
            msg_q.put(item)

        chunks: list[str] = []
        with mock.patch.object(session, "_start_prompt_reader", return_value=msg_q):
            result = session.prompt(
                "hello",
                on_chunk=chunks.append,
                on_permission=lambda params: "allow",
            )

        self.assertIn("hello\n", chunks[0])
        self.assertIn("🔧 [tool] search (/tmp/a)", chunks[-1])
        self.assertIn("🔧 [tool] search", result)
        reply.assert_called_once_with(
            99,
            {"outcome": {"outcome": "selected", "optionId": "allow"}},
        )

    def test_start_prompt_reader_forwards_messages(self) -> None:
        session = tgbot.AcpSession()
        session._recv = mock.Mock(side_effect=[{"id": 5, "result": {}}])

        class ImmediateThread:
            def __init__(self, target, daemon):
                self._target = target
                self.daemon = daemon

            def start(self) -> None:
                self._target()

        with mock.patch("tgbot.threading.Thread", ImmediateThread):
            msg_q = session._start_prompt_reader(5)

        self.assertEqual(msg_q.get_nowait(), {"id": 5, "result": {}})

    def test_await_response_skips_session_updates(self) -> None:
        seen: list[list[dict]] = []
        session = tgbot.AcpSession(on_available_commands=seen.append)
        session._recv = mock.Mock(
            side_effect=[
                {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "available_commands_update",
                            "availableCommands": [{"name": "status"}],
                        }
                    },
                },
                {"id": 3, "result": {}},
            ]
        )

        result = session._await_response(3)

        self.assertEqual(result, {"id": 3, "result": {}})
        self.assertEqual(seen, [[{"name": "status"}]])

    def test_handle_agent_request_supports_cancel_and_unsupported(self) -> None:
        session = tgbot.AcpSession()
        session._reply = mock.Mock()

        session._handle_agent_request(
            {"id": 1, "method": "session/request_permission", "params": {}},
            on_permission=lambda params: None,
        )
        session._handle_agent_request(
            {"id": 2, "method": "unknown", "params": {}},
            on_permission=lambda params: None,
        )

        self.assertEqual(
            session._reply.call_args_list[0].args,
            (1, {"outcome": {"outcome": "cancelled"}}),
        )
        self.assertEqual(
            session._reply.call_args_list[1].args,
            (2, {"error": {"code": -32601, "message": "Not supported"}}),
        )

    def test_handle_session_update_tracks_available_commands(self) -> None:
        seen: list[list[dict]] = []
        session = tgbot.AcpSession(on_available_commands=seen.append)

        kind = session._handle_session_update(
            {
                "sessionUpdate": "available_commands_update",
                "availableCommands": [{"name": "status"}],
            }
        )

        self.assertEqual(kind, "available_commands_update")
        self.assertEqual(session.available_commands, [{"name": "status"}])
        self.assertEqual(seen, [[{"name": "status"}]])

    def test_start_logged_acp_session_creates_log(self) -> None:
        fake_acp = SimpleNamespace(session_id="sess-1")
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch("tgbot.AcpSession.start", return_value=fake_acp),
                mock.patch("tgbot._state_dir", return_value=Path(tmpdir)),
            ):
                acp, session_log = tgbot._start_logged_acp_session(
                    "token",
                    "agent --acp",
                    "/work",
                    None,
                    False,
                )

            self.assertIs(acp, fake_acp)
            self.assertIsNotNone(session_log)
            self.assertTrue(session_log.path.exists())


class UpdateProcessingTest(unittest.TestCase):
    """Cover high-level update processing helpers."""

    def test_drain_pending_prompt(self) -> None:
        pending = deque([{"reply_chat_id": 9, "text": "run", "source": "telegram"}])
        with mock.patch("tgbot._handle_prompt", return_value=4) as handle_prompt:
            drained, turn_id = tgbot._drain_pending_prompt(
                "token",
                SimpleNamespace(session_id="s1"),
                None,
                pending,
                4000,
                3,
                mock.Mock(),
            )

        self.assertTrue(drained)
        self.assertEqual(turn_id, 4)
        handle_prompt.assert_called_once()
        self.assertFalse(pending)

    def test_process_telegram_updates(self) -> None:
        update = {
            "update_id": 10,
            "message": {
                "message_id": 1,
                "text": "hello",
                "chat": {"id": 3, "type": "private"},
                "from": {"id": 8, "username": "alice"},
            },
        }

        with (
            mock.patch("tgbot.api_call", return_value={"ok": True, "result": [update]}),
            mock.patch("tgbot._handle_prompt", return_value=1) as handle_prompt,
        ):
            offset, turn_id = tgbot._process_telegram_updates(
                "token",
                {8},
                99,
                "MyBot",
                0,
                SimpleNamespace(session_id="s1"),
                None,
                4000,
                0,
                mock.Mock(),
            )

        self.assertEqual(offset, 11)
        self.assertEqual(turn_id, 1)
        handle_prompt.assert_called_once()

    def test_run_due_cron_jobs(self) -> None:
        fixed_now = datetime(2026, 4, 24, 9, 0)

        class FixedDateTime:
            @staticmethod
            def now() -> datetime:
                return fixed_now

        with (
            mock.patch("tgbot.datetime", FixedDateTime),
            mock.patch("tgbot._handle_prompt", return_value=2) as handle_prompt,
        ):
            turn_id = tgbot._run_due_cron_jobs(
                [{"expr": "0 9 * * 5", "prompt": "check"}],
                {},
                100,
                "token",
                SimpleNamespace(session_id="s1"),
                None,
                4000,
                1,
                mock.Mock(),
            )

        self.assertEqual(turn_id, 2)
        handle_prompt.assert_called_once()

    def test_cmd_acp_initializes_and_closes_session(self) -> None:
        cfg = make_config(
            "[bot]\ntoken = token\nchat_id = 100\nallow_users = 8\n[acp]\ncommand = agent --acp\ncwd = /tmp\n"
        )
        fake_acp = SimpleNamespace(session_id="sess-1", close=mock.Mock())
        args = SimpleNamespace(agent_cmd=None, cwd=None, session_id=None, yolo=False)

        with (
            mock.patch("tgbot.load_config", return_value=cfg),
            mock.patch("tgbot._resolve_cwd", return_value=(Path("/tmp"), "/tmp")),
            mock.patch("tgbot._load_cron_jobs", return_value=[]),
            mock.patch("tgbot._load_bot_identity", return_value=(9, "MyBot")),
            mock.patch("tgbot._start_logged_acp_session", return_value=(fake_acp, None)),
            mock.patch("tgbot._drain_pending_prompt", return_value=(False, 0)),
            mock.patch("tgbot._process_telegram_updates", side_effect=KeyboardInterrupt),
            mock.patch("tgbot._run_due_cron_jobs", return_value=0),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            with self.assertRaises(KeyboardInterrupt):
                tgbot.cmd_acp(args)

        fake_acp.close.assert_called_once()
        self.assertIn("ACP session ready: sess-1", stdout.getvalue())


class CommandFlowTest(unittest.TestCase):
    """Cover command-line subcommands without network access."""

    def test_cmd_send_uses_config_default_chat(self) -> None:
        cfg = make_config("[bot]\ntoken = token\nchat_id = 12\n")
        args = SimpleNamespace(chat_id=None, text="hello")
        stdout = io.StringIO()

        with (
            mock.patch("tgbot.load_config", return_value=cfg),
            mock.patch("tgbot.api_call", return_value={"ok": True}),
            contextlib.redirect_stdout(stdout),
        ):
            tgbot.cmd_send(args)

        self.assertIn("Message sent to 12.", stdout.getvalue())

    def test_cmd_get_json_output(self) -> None:
        cfg = make_config("[bot]\ntoken = token\nchat_id = 12\n")
        args = SimpleNamespace(all=False, json=True)
        stdout = io.StringIO()

        def fake_api_call(token: str, method: str, params: dict | None = None, retries: int = 0):
            if params and params.get("offset") == 101:
                return {"ok": True}
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 100,
                        "message": {
                            "chat": {"id": 12},
                            "from": {"first_name": "Alice"},
                            "text": "hello",
                            "date": 0,
                        },
                    }
                ],
            }

        with (
            mock.patch("tgbot.load_config", return_value=cfg),
            mock.patch("tgbot.api_call", side_effect=fake_api_call),
            contextlib.redirect_stdout(stdout),
        ):
            tgbot.cmd_get(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload[0]["chat_id"], 12)
        self.assertEqual(payload[0]["text"], "hello")

    def test_load_bot_identity(self) -> None:
        with mock.patch(
            "tgbot.api_call",
            return_value={"ok": True, "result": {"id": 9, "username": "MyBot"}},
        ):
            self.assertEqual(tgbot._load_bot_identity("token"), (9, "MyBot"))

    def test_main_dispatches_to_subcommands(self) -> None:
        with (
            mock.patch("sys.argv", ["tgbot.py", "send", "hello"]),
            mock.patch("tgbot.cmd_send") as cmd_send,
        ):
            tgbot.main()
        cmd_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
