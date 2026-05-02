"""Entry point — loaded by the GitHub Actions cron.

Each invocation can run multiple polls in a row (LOOP_COUNT, LOOP_INTERVAL_SEC)
so we get tighter polling than GitHub Actions' 5-minute cron minimum allows.
With LOOP_COUNT=3 and LOOP_INTERVAL_SEC=120 inside an every-5-min cron, you
effectively check every ~2 minutes.
"""
import logging
import os
import sys
import time
from datetime import date as _date, timedelta
from typing import List

import yaml

from .adapters import get_adapter
from .notifier import send_sms
from .state import load_state, save_state, already_alerted, mark_alerted

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("monitor")

CONFIG_FILE = os.environ.get("CONFIG_FILE", "restaurants.yaml")
DRY_RUN = os.environ.get("DRY_RUN") == "1"
LOOP_COUNT = max(1, int(os.environ.get("LOOP_COUNT", "1")))
LOOP_INTERVAL_SEC = max(0, int(os.environ.get("LOOP_INTERVAL_SEC", "0")))


def resolve_date(raw):
    """Allow `today`, `tomorrow`, or YYYY-MM-DD strings."""
    if not raw:
        return None
    s = str(raw).strip().lower()
    if s == "today":
        return _date.today().isoformat()
    if s == "tomorrow":
        return (_date.today() + timedelta(days=1)).isoformat()
    return str(raw)


def in_window(time_str: str, window: List[str]) -> bool:
    if not window:
        return True
    if len(window) != 2:
        log.warning("time_window must be [start, end]; got %r", window)
        return True
    return window[0] <= time_str <= window[1]


def run_once(watches: list, state: dict) -> int:
    """One poll across all watches. Returns number of new matches."""
    new_matches = 0
    for watch in watches:
        name = watch.get("name") or "(unnamed)"
        platform = watch.get("platform")
        if not platform:
            log.warning("Skipping %s: no platform", name)
            continue

        watch["date"] = resolve_date(watch.get("date"))
        if not watch["date"]:
            log.warning("Skipping %s: missing date", name)
            continue

        try:
            adapter = get_adapter(platform)
        except Exception as e:
            log.error("Skipping %s: %s", name, e)
            continue

        try:
            slots = adapter.find_slots(
                venue_id=str(watch.get("venue_id", "")),
                date=watch["date"],
                party_size=int(watch.get("party_size", 2)),
                watch=watch,
            )
        except Exception as e:
            log.error("Error checking %s: %s", name, e)
            continue

        log.info(
            "[%s] %s on %s: %d slot(s) returned",
            platform, name, watch["date"], len(slots),
        )

        window = watch.get("time_window", [])
        for slot in slots:
            if not in_window(slot.time, window):
                continue
            if already_alerted(state, slot.key, slot.date):
                continue

            new_matches += 1
            body = (
                f"OPEN: {name} @ {slot.time} on {slot.date} "
                f"(party {slot.party_size}). Book now: {slot.booking_url}"
            )
            log.info("MATCH: %s", body)
            if DRY_RUN:
                log.info("(DRY_RUN=1) skipping SMS")
            else:
                try:
                    send_sms(body)
                except Exception as e:
                    log.error("SMS failed for %s: %s", name, e)
                    continue
            mark_alerted(state, slot.key, slot.date)
    return new_matches


def main() -> int:
    if not os.path.exists(CONFIG_FILE):
        log.error("Config file %s not found", CONFIG_FILE)
        return 1

    with open(CONFIG_FILE) as f:
        cfg = yaml.safe_load(f) or {}
    watches = cfg.get("watches", [])
    if not watches:
        log.warning("No watches configured in %s", CONFIG_FILE)
        return 0

    state = load_state()
    total_matches = 0

    for i in range(LOOP_COUNT):
        if i > 0 and LOOP_INTERVAL_SEC > 0:
            log.info(
                "Sleeping %d sec before poll %d/%d...",
                LOOP_INTERVAL_SEC, i + 1, LOOP_COUNT,
            )
            time.sleep(LOOP_INTERVAL_SEC)
        log.info("--- Poll %d/%d ---", i + 1, LOOP_COUNT)
        try:
            total_matches += run_once(watches, state)
        except Exception as e:
            log.error("Poll iteration %d failed: %s", i + 1, e)
        # Persist state after every iteration so a crash doesn't lose alerts.
        save_state(state)

    log.info(
        "Done. %d total new match(es) across %d poll(s).",
        total_matches, LOOP_COUNT,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
