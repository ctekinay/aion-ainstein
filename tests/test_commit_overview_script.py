"""Tests for scripts/dev/commit_overview.sh."""

import subprocess
import os
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent


class TestCommitOverviewScript:
    """Verify the commit overview script exists, runs, and produces output."""

    SCRIPT_PATH = PROJECT_ROOT / "scripts" / "dev" / "commit_overview.sh"

    def test_script_exists(self):
        """Script file must exist on disk."""
        assert self.SCRIPT_PATH.exists(), f"Script not found: {self.SCRIPT_PATH}"

    def test_script_exits_zero(self):
        """Script must exit with code 0."""
        result = subprocess.run(
            ["bash", str(self.SCRIPT_PATH)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Script exited with {result.returncode}.\n"
            f"stderr: {result.stderr[:500]}"
        )

    def test_script_prints_at_least_one_commit_line(self):
        """Script output must contain at least one git commit hash line."""
        result = subprocess.run(
            ["bash", str(self.SCRIPT_PATH)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = result.stdout.strip().split("\n")
        # A commit line from 'git log --oneline' looks like: "abcdef1 Some message"
        commit_lines = [
            line for line in lines
            if len(line) >= 8 and line[:7].replace(" ", "").isalnum()
            and not line.startswith("---")
            and not line.startswith("===")
            and not line.startswith("Generated")
            and not line.startswith("Branch")
            and not line.startswith("HEAD")
            and not line.startswith("Files")
            and not line.startswith("Done")
            and not line.startswith("AION")
        ]
        assert len(commit_lines) >= 1, (
            f"Expected at least 1 commit line in output, found {len(commit_lines)}.\n"
            f"First 20 lines:\n" + "\n".join(lines[:20])
        )

    def test_rollback_map_exists(self):
        """docs/dev/rollback_map.md must exist."""
        rollback_map = PROJECT_ROOT / "docs" / "dev" / "rollback_map.md"
        assert rollback_map.exists(), f"Rollback map not found: {rollback_map}"
