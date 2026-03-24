"""JSON file persistence for HandoffInstance state.

The state file path defaults to ``agency_state.json`` in the current working
directory but can be overridden by setting the ``AGENCY_STATE_FILE`` environment
variable before the module is imported.

All writes are atomic (temp-file + os.replace) so a crash mid-write never
leaves a half-written or empty state file.
"""
from __future__ import annotations

import json
import os
import tempfile
import warnings
from datetime import datetime
from pathlib import Path

from models import HandoffInstance, HandoffPolicy, HandoffState

STATE_FILE = Path(os.environ.get("AGENCY_STATE_FILE", "agency_state.json"))


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def load() -> dict[str, HandoffInstance]:
    """Load persisted handoffs from disk.

    Returns an empty dict if the state file does not yet exist.
    Raises ``RuntimeError`` if the file is present but unreadable / corrupt.
    Individual malformed entries are skipped with a warning rather than
    crashing the whole load.
    """
    if not STATE_FILE.exists():
        return {}

    try:
        raw: dict = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"Failed to load state from '{STATE_FILE}': {exc}"
        ) from exc

    result: dict[str, HandoffInstance] = {}
    for id_, data in raw.items():
        try:
            result[id_] = _deserialize(data)
        except (KeyError, ValueError, TypeError) as exc:
            warnings.warn(
                f"Skipping corrupted handoff '{id_}': {exc}",
                stacklevel=2,
            )
    return result


def save(handoffs: dict[str, HandoffInstance]) -> None:
    """Atomically persist handoffs to disk.

    Uses a temporary file in the same directory followed by ``os.replace``
    so the write is atomic on POSIX systems — a crash mid-write cannot
    produce a partially-written state file.
    """
    payload = {id_: _serialize(h) for id_, h in handoffs.items()}
    content = json.dumps(payload, indent=2)

    dir_ = STATE_FILE.parent
    dir_.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=dir_, suffix=".tmp", prefix=".agency_state_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, STATE_FILE)
    except Exception:
        # Clean up the temp file if anything went wrong
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------ #
# Serialization helpers                                                #
# ------------------------------------------------------------------ #

def _serialize(h: HandoffInstance) -> dict:
    return {
        "id": h.id,
        "state": h.state.value,
        "created_at": h.created_at.isoformat(),
        "updated_at": h.updated_at.isoformat(),
        "notes": h.notes,
        "provided_inputs": list(h.provided_inputs),
        "policy": {
            "from_department": h.policy.from_department,
            "to_department": h.policy.to_department,
            "required_inputs": list(h.policy.required_inputs),
            "expected_outputs": list(h.policy.expected_outputs),
            "sla_hours": h.policy.sla_hours,
            "approver_role": h.policy.approver_role,
        },
    }


def _deserialize(d: dict) -> HandoffInstance:
    _require_keys(d, {"id", "state", "created_at", "updated_at", "notes",
                      "provided_inputs", "policy"})
    p = d["policy"]
    _require_keys(p, {"from_department", "to_department", "required_inputs",
                      "expected_outputs", "sla_hours", "approver_role"})

    policy = HandoffPolicy(
        from_department=p["from_department"],
        to_department=p["to_department"],
        required_inputs=tuple(p["required_inputs"]),
        expected_outputs=tuple(p["expected_outputs"]),
        sla_hours=int(p["sla_hours"]),
        approver_role=p["approver_role"],
    )
    return HandoffInstance(
        policy=policy,
        provided_inputs=tuple(d["provided_inputs"]),
        state=HandoffState(d["state"]),
        id=d["id"],
        created_at=datetime.fromisoformat(d["created_at"]),
        updated_at=datetime.fromisoformat(d["updated_at"]),
        notes=d["notes"],
    )


def _require_keys(d: dict, keys: set[str]) -> None:
    missing = keys - d.keys()
    if missing:
        raise KeyError(f"Missing required keys: {sorted(missing)}")


def handoff_to_dict(h: HandoffInstance) -> dict:
    """Public helper used by CLI and API to render a handoff as a plain dict."""
    return _serialize(h)
