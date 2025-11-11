from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_STATE_FILE = Path.home() / ".cache" / "langchain-deps-agent" / "blueprints.json"


@dataclass
class BlueprintRecord:
    name: str
    blueprint_id: str
    saved_at: str
    agent_path: Optional[str] = None


class BlueprintMemory:
    """Small helper to persist blueprint IDs between CLI invocations."""

    def __init__(self, state_file: Path | None = None) -> None:
        self.state_file = state_file or DEFAULT_STATE_FILE

    # Internal helpers -------------------------------------------------
    def _load(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {"blueprints": {}, "last_used_name": None}
        try:
            data = json.loads(self.state_file.read_text())
        except json.JSONDecodeError:
            return {"blueprints": {}, "last_used_name": None}
        data.setdefault("blueprints", {})
        data.setdefault("last_used_name", None)
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(data, indent=2))

    # Public API -------------------------------------------------------
    def remember(self, name: str, blueprint_id: str, agent_path: str | None = None) -> BlueprintRecord:
        data = self._load()
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        data["blueprints"][name] = {
            "blueprint_id": blueprint_id,
            "saved_at": timestamp,
            "agent_path": agent_path,
        }
        data["last_used_name"] = name
        self._save(data)
        return BlueprintRecord(name=name, blueprint_id=blueprint_id, saved_at=timestamp, agent_path=agent_path)

    def recall(self, name: str | None = None) -> Optional[BlueprintRecord]:
        data = self._load()
        lookup_name = name or data.get("last_used_name")
        if not lookup_name:
            return None
        entry = data["blueprints"].get(lookup_name)
        if not entry:
            return None
        return BlueprintRecord(
            name=lookup_name,
            blueprint_id=entry["blueprint_id"],
            saved_at=entry["saved_at"],
            agent_path=entry.get("agent_path"),
        )

    def forget(self, name: str) -> None:
        data = self._load()
        if name in data["blueprints"]:
            data["blueprints"].pop(name)
        if data.get("last_used_name") == name:
            data["last_used_name"] = None
        self._save(data)


__all__ = ["BlueprintMemory", "BlueprintRecord", "DEFAULT_STATE_FILE"]
