"""Tock (exploretock.com) availability adapter."""
import logging
import requests
from typing import List

from .base import Adapter, Slot

log = logging.getLogger(__name__)


class TockAdapter(Adapter):
    name = "tock"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        })

    def find_slots(self, venue_id, date, party_size, watch) -> List[Slot]:
        # Tock's consumer search endpoint, used by their public widget.
        url = (
            f"https://www.exploretock.com/api/consumer/{venue_id}"
            f"/search/v2/timeslots"
        )
        params = {"date": date, "size": party_size}
        try:
            r = self.session.get(url, params=params, timeout=15)
        except requests.RequestException as e:
            log.warning("Tock request failed for %s: %s", venue_id, e)
            return []
        if r.status_code != 200:
            log.warning("Tock returned %s for %s", r.status_code, venue_id)
            return []
        try:
            data = r.json()
        except ValueError:
            log.warning("Tock returned non-JSON for %s", venue_id)
            return []

        slots: List[Slot] = []
        timeslots = (
            data.get("timeslots")
            or data.get("results")
            or data.get("availability")
            or []
        )
        for ts in timeslots:
            t = ts.get("time") or ts.get("startTime") or ts.get("dateTime")
            if not t:
                continue
            time_str = t.split("T", 1)[1][:5] if "T" in t else t[:5]
            slots.append(Slot(
                platform=self.name,
                venue_id=str(venue_id),
                date=date,
                time=time_str,
                party_size=party_size,
                booking_url=self._booking_url(watch, time_str),
                raw=ts,
            ))
        return slots

    def _booking_url(self, watch: dict, time_str: str) -> str:
        if watch.get("booking_url"):
            return self.build_booking_url_from_template(watch, time_str)
        slug = watch["venue_id"]
        date = watch["date"]
        seats = watch["party_size"]
        return (
            f"https://www.exploretock.com/{slug}/search"
            f"?date={date}&size={seats}&time={time_str}"
        )
