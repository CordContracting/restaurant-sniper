"""Wisely / Olo Engage availability adapter.

Wisely (now part of Olo) doesn't run a single central availability API the way
Resy or OpenTable do — each restaurant embeds the Wisely widget on its own
website, hitting a Wisely-hosted endpoint that varies per host. So this
adapter is configured per-restaurant via two YAML keys:

  availability_url:   Full URL (including query params with placeholders) that
                      returns JSON availability when GET'd.
                      Available placeholders: {date} {party_size} {venue_id}
  availability_method: "GET" or "POST" (default GET)
  availability_body:   Optional JSON body for POST requests, with the same
                       placeholders. Pass as a dict in YAML.

How to find your restaurant's URL:
  1. Open the restaurant's reservation page (where you'd normally book).
  2. Open Chrome DevTools → Network tab → filter "XHR" or "Fetch".
  3. Pick a date and party size; watch which request returns time slots.
  4. Right-click that request → Copy → Copy as cURL. The URL it hits is what
     you put in `availability_url` (replace the date / size / id parts with
     {date}, {party_size}, {venue_id} placeholders so different days work).
"""
import json
import logging
from typing import List

import requests

from .base import Adapter, Slot

log = logging.getLogger(__name__)


class WiselyAdapter(Adapter):
    name = "wisely"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        })

    def find_slots(self, venue_id, date, party_size, watch) -> List[Slot]:
        template = watch.get("availability_url")
        if not template:
            log.error(
                "Wisely watch %r is missing `availability_url` in config. "
                "See README → Wisely setup.",
                watch.get("name"),
            )
            return []

        url = template.format(
            venue_id=venue_id, date=date, party_size=party_size
        )
        method = (watch.get("availability_method") or "GET").upper()
        body_template = watch.get("availability_body")

        try:
            if method == "POST":
                body = self._fill_template(body_template, venue_id, date, party_size)
                r = self.session.post(url, json=body, timeout=15)
            else:
                r = self.session.get(url, timeout=15)
        except requests.RequestException as e:
            log.warning("Wisely request failed for %s: %s", venue_id, e)
            return []

        if r.status_code != 200:
            log.warning(
                "Wisely returned %s for %s — check your availability_url",
                r.status_code, venue_id,
            )
            return []

        try:
            data = r.json()
        except ValueError:
            log.warning("Wisely returned non-JSON for %s", venue_id)
            return []

        return self._parse_times(data, venue_id, date, party_size, watch)

    def _fill_template(self, body_template, venue_id, date, party_size):
        if not body_template:
            return {}
        # Walk the dict and replace placeholders inside strings.
        def fill(v):
            if isinstance(v, str):
                return v.format(
                    venue_id=venue_id, date=date, party_size=party_size
                )
            if isinstance(v, dict):
                return {k: fill(val) for k, val in v.items()}
            if isinstance(v, list):
                return [fill(x) for x in v]
            return v
        return fill(body_template)

    def _parse_times(
        self, data: dict, venue_id, date, party_size, watch
    ) -> List[Slot]:
        # Wisely / Olo response shapes vary; try the common keys.
        candidates = (
            data.get("availability")
            or data.get("times")
            or data.get("results")
            or data.get("slots")
            or data.get("timeSlots")
            or data.get("openings")
            or []
        )
        # Some endpoints wrap in {"data": {"availability": [...]}}
        if not candidates and isinstance(data.get("data"), dict):
            inner = data["data"]
            candidates = (
                inner.get("availability")
                or inner.get("times")
                or inner.get("slots")
                or []
            )

        slots: List[Slot] = []
        for entry in candidates:
            if isinstance(entry, str):
                t = entry
                raw = {"time": entry}
            elif isinstance(entry, dict):
                t = (
                    entry.get("time")
                    or entry.get("startTime")
                    or entry.get("dateTime")
                    or entry.get("start_time")
                )
                raw = entry
            else:
                continue
            if not t:
                continue
            time_str = (
                t.split("T", 1)[1][:5] if "T" in t else t[:5]
            )
            if len(time_str) == 4:
                time_str = "0" + time_str
            slots.append(Slot(
                platform=self.name,
                venue_id=str(venue_id),
                date=date,
                time=time_str,
                party_size=party_size,
                booking_url=self._booking_url(watch, time_str),
                raw=raw,
            ))
        return slots

    def _booking_url(self, watch: dict, time_str: str) -> str:
        if watch.get("booking_url"):
            return self.build_booking_url_from_template(watch, time_str)
        # If the user gave us a reservation page URL, use that.
        return watch.get("reservation_page_url", "")
