"""No-hardware checks for VS Code clickable links and clean text log output."""
from __future__ import annotations
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from utils.terminal_links import emit_path_link, emit_run_file_links


class FakeInteractiveTerminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class TerminalOutputLinksTest(unittest.TestCase):
    def test_interactive_osc8_link_matches_real_absolute_uri(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "相噪 数据 01.png"
            p.write_bytes(b"fake")
            terminal = FakeInteractiveTerminal()
            plain_log = io.StringIO()
            emit_path_link("Screenshot", p, log_handle=plain_log, stream=terminal)
            self.assertIn(f"\x1b]8;;{p.resolve().as_uri()}\x1b\\", terminal.getvalue())
            self.assertIn(p.name, terminal.getvalue())
            self.assertIn(str(p.resolve()), plain_log.getvalue())
            self.assertNotIn("\x1b", plain_log.getvalue())

    def test_fallback_prints_absolute_path_without_controls(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "report.xlsx"
            output = io.StringIO()
            emit_path_link("Summary Excel", p, stream=output)
            self.assertIn(str(p.resolve()), output.getvalue())
            self.assertNotIn("\x1b", output.getvalue())

    def test_run_links_only_list_existing_files_and_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            (run / "run_log.txt").write_text("log", encoding="utf-8")
            (run / "screenshots").mkdir()
            output = io.StringIO()
            with mock.patch("sys.stdout", output):
                emit_run_file_links(run)
            self.assertIn("Output Folder", output.getvalue())
            self.assertIn("Run Log", output.getvalue())
            self.assertIn("Screenshots", output.getvalue())
            self.assertNotIn("Summary Excel", output.getvalue())

    def test_three_case_scripts_integrate_shared_helper(self):
        for dim in (1, 2, 3):
            with self.subTest(dim=dim):
                import importlib
                script = importlib.import_module(f"scripts.fullflow.case_saw_pn_sweep_{dim}param")
                self.assertIs(script.emit_path_link, emit_path_link)
                self.assertIs(script.emit_run_file_links, emit_run_file_links)


if __name__ == "__main__":
    unittest.main()
