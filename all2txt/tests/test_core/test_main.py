"""Tests for the CLI entry point (__main__.py)."""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _run_main(argv: list[str], mock_detect: bool = True) -> int:
    """Run main() with given argv, return SystemExit code."""
    detect_patch = patch(
        "all2txt.core.registry.subprocess.check_output",
        return_value="text/plain",
    )
    with patch.object(sys, "argv", ["all2txt"] + argv):
        from all2txt.__main__ import main

        try:
            if mock_detect:
                with detect_patch:
                    main()
            else:
                main()
            return 0
        except SystemExit as exc:
            return int(exc.code) if exc.code is not None else 0


def test_main_single_file_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "hello.txt"
    f.write_text("hello world")
    exit_code = _run_main([str(f)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "hello world" in captured.out


def test_main_adds_newline_if_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "no_newline.txt"
    f.write_text("no newline at end")
    _run_main([str(f)])
    captured = capsys.readouterr()
    assert captured.out.endswith("\n")


def test_main_multiple_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("alpha")
    b.write_text("beta")
    exit_code = _run_main([str(a), str(b)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "alpha" in captured.out
    assert "beta" in captured.out


def test_main_failed_file_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "unknown.xyz"
    f.write_bytes(b"\x00\x01\x02")
    with patch("all2txt.core.registry.registry.extract", side_effect=RuntimeError("no backend")):
        exit_code = _run_main([str(f)], mock_detect=False)
    assert exit_code == 1
    assert "error" in capsys.readouterr().err


def test_main_detect_error_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.txt"
    f.write_text("x")
    from subprocess import CalledProcessError

    with patch(
        "all2txt.core.registry.subprocess.check_output",
        side_effect=CalledProcessError(1, "file"),
    ):
        exit_code = _run_main([str(f)], mock_detect=False)
    assert exit_code == 1
    assert "error" in capsys.readouterr().err


def test_main_file_command_missing_falls_back_to_mimetypes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When file(1) is missing, mimetypes fallback is used and extraction still succeeds."""
    import logging

    f = tmp_path / "x.txt"
    f.write_text("x")
    with patch(
        "all2txt.core.registry.subprocess.check_output",
        side_effect=FileNotFoundError("file not found"),
    ):
        with caplog.at_level(logging.WARNING, logger="all2txt.core.registry"):
            exit_code = _run_main([str(f)], mock_detect=False)
    assert exit_code == 0
    assert any("mimetypes" in r.message for r in caplog.records)


def test_main_mime_override(tmp_path: Path) -> None:
    f = tmp_path / "data.txt"
    f.write_text("some text")
    mock_extract = MagicMock(return_value="extracted")
    with patch("all2txt.core.registry.registry.extract", mock_extract):
        _run_main(["--mime", "text/plain", str(f)], mock_detect=False)
    mock_extract.assert_called_once_with(f, mime="text/plain")


def test_main_debug_sets_log_level(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("x")
    with patch("logging.basicConfig") as mock_log:
        _run_main(["--debug", str(f)])
    call_kwargs = mock_log.call_args[1]
    assert call_kwargs["level"] == logging.DEBUG


def test_main_config_path_passed_to_load(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("x")
    cfg = tmp_path / "my.yaml"
    cfg.write_text("{}")
    with patch("all2txt.__main__.load_config") as mock_cfg:
        from all2txt.core.config import Config

        mock_cfg.return_value = Config()
        _run_main(["--config", str(cfg), str(f)])
    mock_cfg.assert_called_once_with(cfg)


def test_backends_init_tolerates_import_error() -> None:
    import importlib

    import all2txt.backends as backends_pkg

    with patch.dict(sys.modules, {"all2txt.backends.plaintext": None}):
        # ImportError is silently swallowed (optional dependency absent)
        importlib.reload(backends_pkg)


def test_backends_init_reraises_non_import_error() -> None:
    import importlib

    import all2txt.backends as backends_pkg

    with patch("builtins.__import__", side_effect=SyntaxError("bad syntax")):
        with pytest.raises(SyntaxError):
            importlib.reload(backends_pkg)
