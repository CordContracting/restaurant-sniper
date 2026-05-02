"""Yelp Reservations availability adapter.

Yelp doesn't publicly document a reservation availability API, so this adapter
is best-effort. Strategy:
  1. Try the JSON endpoint that powers the booking widget.
  2. Fall back to scraping embedded JSON from the reservations HTML page.

If neither yields slots when you can clearly see availability in a browser,
open Chrome DevTools on the Yelp reservation page, watch the Network tab as
you change date/party-size, and update the URL/payload in `find_slots`.

The `venue_id` for Yelp is the slug used in the reservation URL — for a page
at https://www.yelp.com/reservations/din-tai-fung-glendale-2 the slug is
`din-tai-fung-glendale-2`.
"""
import json
import logging
import re
from typing import List

import requests

from .base import Adapter, Slot

log = logging.getLogger(__name__)


class YelpAdapter(Adapter):
    name = "yelp"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        })

    def find_slots(self, venue_id, date, party_size, watch) -> List[Slot]:
        slots = self._try_json_endpoint(venue_id, date, party_size, watch)
        if not slots:
            slots = self._scrape_html(venue_id, date, party_size, watch)
        return slots

    def _try_json_endpoint(self, venue_id, date, party_size, watch) -> List[Slot]:
        # Yelp's reservation widget historically calls this endpoint shape.
        url = f"https://www.yelp.com/reservations/{venue_id}/availability"
        params = {"covers": party_size, "date": date}
        try:
            r = self.session.get(url, params=params, timeout=15)
        except requests.RequestException as e:
            log.warning("Yelp JSON request failed for %s: %s", venue_id, e)
            return []
        if r.status_code != 200:
            log.info(
                "Yelp JSON endpoint returned %s for %s (will try HTML fallback)",
                r.status_code, venue_id,
            )
            return []
        try:
            data = r.json()
        except ValueError:
            log.info("Yelp JSON endpoint returned non-JSON for %s", venue_id)
            return []

        return self._parse_times(data, venue_id, date, party_size, watch)

    def _scrape_html(self, venue_id, date, party_size, watch) -> List[Slot]:
        url = f"https://www.yelp.com/reservations/{venue_id}"
        params = {"covers": party_size, "date": date}
        try:
            r = self.session.get(url, params=params, timeout=15)
        except requests.RequestException as e:
            log.warning("Yelp HTML request failed for %s: %s", venue_id, e)
            return []
        if r.status_code != 200:
            log.warning(
                "Yelp HTML page returned %s for %s", r.status_code, venue_id
            )
            return []
        html = r.text

        # Yelp embeds availability in a JSON blob inside the page. We look for
        # arrays of times keyed under "available" / "openings" / "times".
        slots: List[Slot] = []
        for pattern in (
            r'"availableTimes"\s*:\s*(\[[^\]]+\])',
            r'"openings"\s*:\s*(\[[^\]]+\])',
            r'"times"\s*:\s*(\[[^\]]+\])',
        ):
            for match in re.finditer(pattern, html):
                try:
                    arr = json.loads(match.group(1))
                except (ValueError, json.JSONDecodeError):
                    continue
                slots.extend(
                    self._parse_times(
                        {"times": arr}, venue_id, date, party_size, watch
                    )
                )
            if slots:
                break

        # Last resort — pull bare HH:MM strings from any "time": "..." pairs.
        if not slots:
            for m in re.finditer(r'"time"\s*:\s*"(\d{1,2}:\d{2})"', html):
                time_str = m.group(1)
                if len(time_str) == 4:
                    time_str = "0" + time_str
                slots.append(Slot(
                    platform=self.name,
                    venue_id=str(venue_id),
                    date=date,
                    time=time_str,
                    party_size=party_size,
                    booking_url=self._booking_url(watch, time_str),
                    raw={"source": "regex", "time": time_str},
                ))

        # De-dupe by time
        seen = set()
        uniq = []
        for s in slots:
            if s.time not in seen:
                seen.add(s.time)
                uniq.append(s)
        return uniq

    def _parse_times(
        self, data: dict, venue_id, date, party_size, watch
    ) -> List[Slot]:
        candidates = (
            data.get("availability_times")
            or data.get("availableTimes")
            or data.get("times")
            or data.get("openings")
            or data.get("availability")
            or []
        )
        slots: List[Slot] = []
        for entry in candidates:
            if isinstance(entry, str):
                t = entry
            elif isinstance(entry, dict):
                t = (
                    entry.get("time")
                    or entry.get("startTime")
                    or entry.get("starts_at")
                    or entry.get("dateTime")
                )
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
                raw=entry if isinstance(entry, dict) else {"time": t},
            ))
        return slots

    def _booking_url(self, watch: dict, time_str: str) -> str:
        if watch.get("booking_url"):
            return self.build_booking_url_from_template(watch, time_str)
        slug = watch["venue_id"]
        date = watch["date"]
        seats = watch["party_size"]
        return (
            f"https://www.yelp.com/reservations/{slug}"
            f"?covers={seats}&date={date}&time={time_str}"
        )
