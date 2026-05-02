"""Tiny state file used to dedupe alerts across runs."""
import json
import os
from datetime import date as _date, timedelta

STATE_FILE = os.environ.get("STATE_FILE", "state.json")


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"alerted": {}}
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"alerted": {}}
    if "alerted" not in data:
        data["alerted"] = {}
    return data


def save_state(state: dict) -> None:
    # Prune entries older than 7 days so the file stays small.
    cutoff = (_date.today() - timedelta(days=7)).isoformat()
    state["alerted"] = {
        d: keys for d, keys in state.get("alerted", {}).items() if d >= cutoff
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def already_alerted(state: dict, slot_key: str, watch_date: str) -> bool:
    return slot_key in state.get("alerted", {}).get(watch_date, {})


def mark_alerted(state: dict, slot_key: str, watch_date: str) -> None:
    state.setdefault("alerted", {}).setdefault(watch_date, {})[slot_key] = True
