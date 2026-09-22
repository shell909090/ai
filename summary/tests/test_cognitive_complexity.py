"""Regression tests for the cognitive complexity gate."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_cognitive_complexity import check_project, function_scores


class CognitiveComplexityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_source(self, name: str, source: str) -> Path:
        """Create a Python fixture under the temporary project root."""
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def test_accepts_fifteen_and_rejects_sixteen(self) -> None:
        source = "def example(value):\n"
        source += "".join("    " * depth + "if value:\n" for depth in range(1, 6))
        source += "    " * 6 + "pass\n"
        path = self.write_source("example.py", source)
        self.assertEqual(function_scores(path), [(1, "example", 15)])
        with self.assertLogs(level="INFO"):
            self.assertEqual(check_project(self.root), 0)

        self.write_source("example.py", source + "    if value:\n        pass\n")
        self.assertEqual(function_scores(path), [(1, "example", 16)])
        with self.assertLogs(level="ERROR") as logs:
            self.assertEqual(check_project(self.root), 1)
        self.assertIn("example cognitive complexity 16 > 15", logs.output[0])

    def test_finds_methods_nested_and_async_functions(self) -> None:
        path = self.write_source("example.py", (
            "class Example:\n"
            "    def outer(self):\n"
            "        def inner():\n"
            "            pass\n"
            "        return inner\n"
            "    async def run(self):\n"
            "        pass\n"
        ))
        self.assertEqual({name for _, name, _ in function_scores(path)}, {"outer", "inner", "run"})

    def test_excludes_environment_but_includes_tests(self) -> None:
        self.write_source(".venv/invalid.py", "invalid python syntax")
        self.write_source(".cache/invalid.py", "invalid python syntax")
        self.write_source("tests/example.py", "def test_example():\n    pass\n")
        with self.assertLogs(level="INFO") as logs:
            self.assertEqual(check_project(self.root), 0)
        self.assertIn("1 files, 1 functions", logs.output[-1])

    def test_invalid_python_fails_scan(self) -> None:
        self.write_source("invalid.py", "def invalid(:")
        with self.assertLogs(level="ERROR"):
            self.assertEqual(check_project(self.root), 1)

    def test_empty_directory_fails_scan(self) -> None:
        with self.assertLogs(level="ERROR"):
            self.assertEqual(check_project(self.root), 1)


if __name__ == "__main__":
    unittest.main()
