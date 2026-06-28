"""Unit tests for kanbanctl.py — argument parsing and error handling."""
import json
import os
import sys
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

# Ensure scripts/ is importable as a module.
sys.path.insert(0, os.path.dirname(__file__))
import kanbanctl


def _set_env(monkeypatch=None):
    """Patch env vars required by kanbanctl."""
    os.environ.setdefault("KANBAN_CONTROL_URL", "http://127.0.0.1:9999")
    os.environ.setdefault("KANBAN_CONTROL_TOKEN", "test-token")


class FakeResponse:
    """Minimal urllib response stand-in."""

    def __init__(self, data: dict, status: int = 200):
        self._data = data
        self.status = status

    def read(self):
        return json.dumps(self._data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def _mock_request(data: dict):
    """Return a patcher that makes kanbanctl.request() return data."""
    return patch("kanbanctl.request", return_value=data)


class TestListCards(unittest.TestCase):
    def setUp(self):
        _set_env()

    def test_default_list_is_todo(self):
        args = kanbanctl._parse(["list-cards"])
        self.assertEqual(args.list, "todo")

    def test_explicit_list(self):
        args = kanbanctl._parse(["list-cards", "--list", "doing"])
        self.assertEqual(args.list, "doing")

    def test_calls_correct_path(self):
        with _mock_request([]) as mock_req, patch("builtins.print"):
            kanbanctl._parse(["list-cards", "--list", "done"]).func(
                kanbanctl._parse(["list-cards", "--list", "done"])
            )
            mock_req.assert_called_once_with("GET", "/control/v1/cards?list=done")


class TestShowCard(unittest.TestCase):
    def setUp(self):
        _set_env()

    def test_requires_card_id(self):
        with self.assertRaises(SystemExit):
            kanbanctl._parse(["show-card"])

    def test_calls_correct_path(self):
        with _mock_request({"id": "abc"}) as mock_req, patch("builtins.print"):
            kanbanctl._parse(["show-card", "abc"]).func(
                kanbanctl._parse(["show-card", "abc"])
            )
            mock_req.assert_called_once_with("GET", "/control/v1/cards/abc")


class TestAddTodo(unittest.TestCase):
    def setUp(self):
        _set_env()

    def test_requires_title(self):
        with self.assertRaises(SystemExit):
            kanbanctl._parse(["add-todo"])

    def test_default_cwd_is_getcwd(self):
        """add-todo without --project sends os.getcwd() as cwd."""
        called_body = {}

        def fake_request(method, path, body=None):
            called_body.update(body or {})
            return {"id": "new"}

        with patch("kanbanctl.request", side_effect=fake_request), patch("builtins.print"):
            args = kanbanctl._parse(["add-todo", "--title", "T"])
            args.func(args)

        self.assertEqual(called_body.get("cwd"), os.getcwd())
        self.assertNotIn("project", called_body)

    def test_explicit_project_omits_cwd(self):
        called_body = {}

        def fake_request(method, path, body=None):
            called_body.update(body or {})
            return {"id": "new"}

        with patch("kanbanctl.request", side_effect=fake_request), patch("builtins.print"):
            args = kanbanctl._parse(["add-todo", "--title", "T", "--project", "myproj"])
            args.func(args)

        self.assertEqual(called_body.get("project"), "myproj")
        self.assertNotIn("cwd", called_body)

    def test_model_flag(self):
        called_body = {}

        def fake_request(method, path, body=None):
            called_body.update(body or {})
            return {"id": "new"}

        with patch("kanbanctl.request", side_effect=fake_request), patch("builtins.print"):
            args = kanbanctl._parse(["add-todo", "--title", "T", "--project", "p", "--model", "sonnet"])
            args.func(args)

        self.assertEqual(called_body.get("model"), "sonnet")

    def test_extra_labels(self):
        called_body = {}

        def fake_request(method, path, body=None):
            called_body.update(body or {})
            return {"id": "new"}

        with patch("kanbanctl.request", side_effect=fake_request), patch("builtins.print"):
            args = kanbanctl._parse(
                ["add-todo", "--title", "T", "--project", "p", "--label", "attention"]
            )
            args.func(args)

        self.assertIn("attention", called_body.get("labels", []))


class TestMove(unittest.TestCase):
    def setUp(self):
        _set_env()

    def test_requires_card_and_list(self):
        with self.assertRaises(SystemExit):
            kanbanctl._parse(["move", "card1"])  # missing --list

    def test_calls_correct_path(self):
        with _mock_request({"status": "ok"}) as mock_req, patch("builtins.print"):
            args = kanbanctl._parse(["move", "card1", "--list", "done"])
            args.func(args)
            mock_req.assert_called_once_with(
                "POST", "/control/v1/cards/card1/move", {"list": "done"}
            )


class TestComment(unittest.TestCase):
    def setUp(self):
        _set_env()

    def test_requires_card_and_text(self):
        with self.assertRaises(SystemExit):
            kanbanctl._parse(["comment", "card1"])  # missing --text

    def test_calls_correct_path(self):
        with _mock_request({"status": "ok"}) as mock_req, patch("builtins.print"):
            args = kanbanctl._parse(["comment", "card1", "--text", "hello"])
            args.func(args)
            mock_req.assert_called_once_with(
                "POST", "/control/v1/cards/card1/comments", {"text": "hello"}
            )


class TestLabel(unittest.TestCase):
    def setUp(self):
        _set_env()

    def test_label_add(self):
        with _mock_request({"status": "ok"}) as mock_req, patch("builtins.print"):
            args = kanbanctl._parse(["label", "add", "card1", "attention"])
            args.func(args)
            mock_req.assert_called_once_with(
                "POST", "/control/v1/cards/card1/labels", {"label": "attention"}
            )

    def test_label_remove(self):
        with _mock_request({"status": "ok"}) as mock_req, patch("builtins.print"):
            args = kanbanctl._parse(["label", "remove", "card1", "attention"])
            args.func(args)
            mock_req.assert_called_once_with(
                "DELETE", "/control/v1/cards/card1/labels/attention"
            )


class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        _set_env()

    def test_nonzero_exit_on_api_error(self):
        import urllib.error

        err = urllib.error.HTTPError(
            url="http://x", code=400, msg="bad", hdrs=None, fp=None  # type: ignore[arg-type]
        )
        err.read = lambda: b'{"error":"unknown list: xyz"}'
        with patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(SystemExit) as cm:
                with patch("sys.stderr", new_callable=StringIO):
                    kanbanctl.request("GET", "/control/v1/cards?list=xyz")
            self.assertNotEqual(cm.exception.code, 0)

    def test_error_output_is_json(self):
        import urllib.error

        err = urllib.error.HTTPError(
            url="http://x", code=400, msg="bad", hdrs=None, fp=None  # type: ignore[arg-type]
        )
        err.read = lambda: b'{"error":"title is required"}'
        stderr = StringIO()
        with patch("urllib.request.urlopen", side_effect=err):
            with patch("sys.stderr", stderr):
                with self.assertRaises(SystemExit):
                    kanbanctl.request("POST", "/control/v1/cards", {})

        output = stderr.getvalue().strip()
        self.assertTrue(output.startswith("{"), f"stderr should be JSON, got: {output!r}")
        parsed = json.loads(output)
        self.assertIn("error", parsed)

    def test_missing_url_env(self):
        old = os.environ.pop("KANBAN_CONTROL_URL", None)
        try:
            stderr = StringIO()
            with patch("sys.stderr", stderr):
                with self.assertRaises(SystemExit) as cm:
                    kanbanctl.get_config()
            self.assertNotEqual(cm.exception.code, 0)
        finally:
            if old is not None:
                os.environ["KANBAN_CONTROL_URL"] = old

    def test_missing_token_env(self):
        old = os.environ.pop("KANBAN_CONTROL_TOKEN", None)
        try:
            stderr = StringIO()
            with patch("sys.stderr", stderr):
                with self.assertRaises(SystemExit) as cm:
                    kanbanctl.get_config()
            self.assertNotEqual(cm.exception.code, 0)
        finally:
            if old is not None:
                os.environ["KANBAN_CONTROL_TOKEN"] = old


if __name__ == "__main__":
    unittest.main()
