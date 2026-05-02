"""OpenTable availability adapter.

OpenTable's public availability endpoint is more closed than Resy's, and the
exact shape of the response changes from time to time. This adapter aims at the
GraphQL endpoint used by their booking widget. If it stops returning data for
your target restaurant, open the restaurant page in Chrome, look at the
Network tab when the date/time picker loads, and adjust the request below.
"""
import logging
import requests
from typing import List

from .base import Adapter, Slot

log = logging.getLogger(__name__)


class OpenTableAdapter(Adapter):
    name = "opentable"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "x-csrf-token": "fetch",
        })

    def find_slots(self, venue_id, date, party_size, watch) -> List[Slot]:
        url = "https://www.opentable.com/dapi/fe/gql?optype=query&opname=RestaurantsAvailability"
        # We query a center time and let OpenTable return the full day's slots.
        body = {
            "operationName": "RestaurantsAvailability",
            "variables": {
                "restaurantIds": [int(venue_id)],
                "date": date,
                "partySize": int(party_size),
                "useCache": False,
            },
            "extensions": {},
            "query": (
                "query RestaurantsAvailability($restaurantIds: [Int!]!, "
                "$date: String!, $partySize: Int!, $useCache: Boolean) { "
                "availability(restaurantIds: $restaurantIds, date: $date, "
                "partySize: $partySize, useCache: $useCache) { "
                "__typename ... on Available { restaurantId timeSlots { "
                "dateTime time isAvailable } } } }"
            ),
        }
        try:
            r = self.session.post(url, json=body, timeout=15)
        except requests.RequestException as e:
            log.warning("OpenTable request failed for rid %s: %s", venue_id, e)
            return []
        if r.status_code != 200:
            log.warning(
                "OpenTable returned %s for rid %s", r.status_code, venue_id
            )
            return []
        try:
            data = r.json()
        except ValueError:
            log.warning("OpenTable returned non-JSON for rid %s", venue_id)
            return []

        slots: List[Slot] = []
        availability = (
            data.get("data", {}).get("availability", []) or []
        )
        for entry in availability:
            for ts in entry.get("timeSlots", []) or []:
                if not ts.get("isAvailable"):
                    continue
                dt = ts.get("dateTime") or ts.get("time")
                if not dt:
                    continue
                if "T" in dt:
                    d_part, t_part = dt.split("T", 1)
                else:
                    d_part, t_part = date, dt
                if d_part != date:
                    continue
                time_str = t_part[:5]
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
        rid = watch["venue_id"]
        date = watch["date"]
        seats = watch["party_size"]
        return (
            f"https://www.opentable.com/booking/restref/availability"
            f"?rid={rid}&restRef={rid}"
            f"&datetime={date}T{time_str}&covers={seats}"
        )
