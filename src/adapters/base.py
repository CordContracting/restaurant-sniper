"""Adapter base class + Slot dataclass shared by every platform implementation."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Slot:
    platform: str
    venue_id: str
    date: str          # YYYY-MM-DD
    time: str          # HH:MM (24h)
    party_size: int
    booking_url: str
    raw: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Stable key used for dedupe across runs."""
        return f"{self.platform}:{self.venue_id}:{self.date}:{self.time}:{self.party_size}"


class Adapter:
    """Subclass per reservation platform."""

    name: str = ""

    def find_slots(
        self, venue_id: str, date: str, party_size: int, watch: dict
    ) -> List[Slot]:
        raise NotImplementedError

    def build_booking_url_from_template(self, watch: dict, time: str) -> str:
        """Use the user-supplied `booking_url` template if present.

        Available placeholders: {date} {party_size} {time} {time_compact}
        """
        template = watch.get("booking_url")
        if not template:
            raise ValueError(
                f"No booking_url template for {watch.get('name')!r}"
            )
        return template.format(
            date=watch["date"],
            party_size=watch["party_size"],
            time=time,
            time_compact=time.replace(":", ""),
        )
