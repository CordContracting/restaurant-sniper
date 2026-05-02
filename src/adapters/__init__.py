from .resy import ResyAdapter
from .opentable import OpenTableAdapter
from .tock import TockAdapter
from .yelp import YelpAdapter
from .wisely import WiselyAdapter

ADAPTERS = {
    "resy": ResyAdapter,
    "opentable": OpenTableAdapter,
    "tock": TockAdapter,
    "yelp": YelpAdapter,
    "wisely": WiselyAdapter,
}


def get_adapter(name: str):
    if name not in ADAPTERS:
        raise ValueError(
            f"Unknown platform: {name!r}. Supported: {sorted(ADAPTERS.keys())}"
        )
    return ADAPTERS[name]()
