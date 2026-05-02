"""Resy availability adapter.

Calls the same /4/find endpoint that resy.com's web app uses. The auth header
contains the public web client API key (visible in any browser dev-tools call
on resy.com), not a personal token.
"""
import logging
import requests
from typing import List

from .base import Adapter, Slot

log = logging.getLogger(__name__)

RESY_API_KEY = "VbpQBw1YSJWtjuaOoGNiUKwRQEYbPbX9"


class ResyAdapter(Adapter):
    name = "resy"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f'ResyAPI api_key="{RESY_API_KEY}"',
            "X-Origin": "https://resy.com",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        })

    def find_slots(self, venue_id, date, party_size, watch) -> List[Slot]:
        url = "https://api.resy.com/4/find"
        params = {
            "lat": 0,
            "long": 0,
            "day": date,
            "party_size": party_size,
            "venue_id": venue_id,
        }
        try:
            r = self.session.get(url, params=params, timeout=15)
        except requests.RequestException as e:
            log.warning("Resy request failed for venue %s: %s", venue_id, e)
            return []
        if r.status_code != 200:
            log.warning("Resy returned %s for venue %s", r.status_code, venue_id)
            return []
        data = r.json()

        slots: List[Slot] = []
        for venue in data.get("results", {}).get("venues", []):
            for slot in venue.get("slots", []):
                start = (slot.get("date") or {}).get("start", "")
                # start: "2026-05-03 18:00:00"
                if " " not in start:
                    continue
                time_str = start.split(" ", 1)[1][:5]
                slots.append(Slot(
                    platform=self.name,
                    venue_id=str(venue_id),
                    date=date,
                    time=time_str,
                    party_size=party_size,
                    booking_url=self._booking_url(watch, time_str),
                    raw=slot,
                ))
        return slots

    def _booking_url(self, watch: dict, time_str: str) -> str:
        if watch.get("booking_url"):
            return self.build_booking_url_from_template(watch, time_str)
        slug = watch.get("venue_slug")
        city = watch.get("city_code", "ny")
        date = watch["date"]
        seats = watch["party_size"]
        if slug:
            return (
                f"https://resy.com/cities/{city}/{slug}"
                f"?date={date}&seats={seats}&time={time_str.replace(':', '')}"
            )
        # Fallback: send to the city search page
        return (
            f"https://resy.com/cities/{city}"
            f"?date={date}&seats={seats}&query={watch.get('name', '')}"
        )
