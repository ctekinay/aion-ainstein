"""Pixel Agents integration — manifest-based discovery for the forked VSCode extension.

Writes an ainstein-manifest.json and per-agent JSONL files into the extension's
project directory so that the Pixel Agents extension can discover and visualize
AInstein's Pydantic AI agents.

JSONL records use the extension's transcript format so the existing
transcriptParser.ts can drive character animations without modification.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Import canonical agent labels — single source of truth
from aion.agents import AGENT_LABELS

# Pixel agents use a subset (exclude "synthesis" — not a real agent)
AGENTS: dict[str, str] = {
    k: v for k, v in AGENT_LABELS.items() if k != "synthesis"
}


def _get_project_dir(ext_root: str | None) -> Path | None:
    """Derive the Pixel Agents project directory from the current working directory.

    Mirrors the path logic in pixel-agents/src/agentManager.ts:getProjectDirPath().
    """
    if not ext_root:
        return None  # Pixel Agents disabled — set PIXEL_AGENTS_DIR to enable
    workspace = os.getcwd()
    dir_name = re.sub(r"[^a-zA-Z0-9-]", "-", workspace)
    project_dir = Path(ext_root) / "projects" / dir_name
    if not project_dir.exists():
        try:
            project_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
    return project_dir


class PixelAgentRegistry:
    """Manages per-agent JSONL files and the shared manifest."""

    def __init__(self) -> None:
        self._project_dir: Path | None = None
        self._agents: dict[str, dict[str, Any]] = {}  # key → {file, path, tool_counter}
        self._initialized = False

    def init(self, pixel_agents_dir: str | None = None) -> None:
        """Create JSONL files and write the manifest.

        Args:
            pixel_agents_dir: Root directory for Pixel Agents data.
                              Pass settings.pixel_agents_dir from the caller.
        """
        self._project_dir = _get_project_dir(pixel_agents_dir)
        if not self._project_dir:
            logger.warning("pixel_agents.init: could not determine project dir")
            return

        # Clean up stale files from previous runs (e.g. crashed server)
        for old_file in self._project_dir.glob("ainstein-*.jsonl"):
            old_file.unlink(missing_ok=True)
        old_manifest = self._project_dir / "ainstein-manifest.json"
        if old_manifest.exists():
            old_manifest.unlink(missing_ok=True)

        # Create per-agent JSONL files
        for key, name in AGENTS.items():
            session_id = uuid.uuid4().hex[:12]
            filename = f"ainstein-{session_id}.jsonl"
            filepath = self._project_dir / filename
            filepath.touch()
            self._agents[key] = {
                "name": name,
                "filename": filename,
                "path": filepath,
                "tool_counter": 0,
                "active_tool_id": None,
            }

        # Write manifest AFTER all JSONL files exist
        manifest = {
            "type": "ainstein",
            "agents": [
                {"key": key, "name": info["name"], "jsonlFile": info["filename"]}
                for key, info in self._agents.items()
            ],
        }
        manifest_path = self._project_dir / "ainstein-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        self._initialized = True
        logger.info(
            "pixel_agents.init",
            project_dir=str(self._project_dir),
            agents=list(self._agents.keys()),
        )

    def shutdown(self) -> None:
        """Remove manifest and JSONL files."""
        if not self._initialized or not self._project_dir:
            return
        manifest_path = self._project_dir / "ainstein-manifest.json"
        try:
            manifest_path.unlink(missing_ok=True)
        except OSError:
            pass
        for info in self._agents.values():
            try:
                info["path"].unlink(missing_ok=True)
            except OSError:
                pass
        self._agents.clear()
        self._initialized = False
        logger.info("pixel_agents.shutdown")

    # ── Activity events ──────────────────────────────────────────────

    def speech(self, agent_key: str, text: str, duration: float = 3.0) -> None:
        """Show a speech bubble with text above the agent character.

        Emits a 'speech' record that the extension's transcriptParser
        forwards as an agentSpeech message to the webview.
        """
        info = self._agents.get(agent_key)
        if not info:
            return
        info["was_active"] = True
        self._write(info, {
            "type": "speech",
            "text": text,
            "duration": duration,
        })

    def thinking(self, agent_key: str, description: str = "") -> None:
        """Mark agent as active (text output / thinking)."""
        info = self._agents.get(agent_key)
        if not info:
            return
        info["was_active"] = True
        # Emit an assistant text block — the parser treats text-only turns
        # as activity (resets idle timers)
        self._write(info, {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": description or "Thinking..."}]
            },
        })

    def tool_call(self, agent_key: str, tool_name: str, description: str = "") -> None:
        """Emit a tool_use event — triggers 'active' animation with tool status."""
        info = self._agents.get(agent_key)
        if not info:
            return
        # Complete any active tool first — prevents the permission timer from
        # firing when tool_use records pile up without matching tool_results.
        if info.get("active_tool_id"):
            self.tool_result(agent_key, "Done")
        info["was_active"] = True
        info["tool_counter"] += 1
        tool_id = f"ainstein_{agent_key}_{info['tool_counter']}"
        info["active_tool_id"] = tool_id
        self._write(info, {
            "type": "assistant",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": {"description": description} if description else {},
                }]
            },
        })

    def tool_result(self, agent_key: str, result: str = "") -> None:
        """Emit a tool_result event — completes the active tool."""
        info = self._agents.get(agent_key)
        if not info:
            return
        tool_id = info.get("active_tool_id")
        if not tool_id:
            return
        info["active_tool_id"] = None
        self._write(info, {
            "type": "user",
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result or "Done",
                }]
            },
        })

    def idle(self, agent_key: str, delay: float = 1.5) -> None:
        """Mark agent as idle (waiting for input) — emits turn_duration.

        Only emits if the agent was actually active (had thinking or tool_call
        events). Agents that never participated stay silent — no checkmarks.

        Uses a delay (default 1.5s) so the file watcher has time to read and
        render the active state before turn_duration clears it. Without the
        delay, all events land in one poll cycle and isActive flips to false
        before the webview ever renders the active state.
        """
        info = self._agents.get(agent_key)
        if not info:
            return
        # Skip if agent was never active this turn
        if not info.get("was_active"):
            return
        # Complete any active tool first
        if info.get("active_tool_id"):
            self.tool_result(agent_key, "Complete")

        def _write_idle():
            self._write(info, {
                "type": "system",
                "subtype": "turn_duration",
            })

        info["was_active"] = False
        if delay > 0:
            threading.Timer(delay, _write_idle).start()
        else:
            _write_idle()

    def idle_all(self) -> None:
        """Mark all active agents as idle. Agents that never participated are skipped."""
        for key in self._agents:
            self.idle(key)

    # ── Internal ─────────────────────────────────────────────────────

    def _write(self, info: dict[str, Any], record: dict[str, Any]) -> None:
        """Append a JSON record to the agent's JSONL file."""
        try:
            with open(info["path"], "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            logger.warning("pixel_agents.write_error", error=str(e))


# Module-level singleton
pixel_registry = PixelAgentRegistry()
