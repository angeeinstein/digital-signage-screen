"""Wires configuration, data sources and pollers together."""

from __future__ import annotations

import logging
from typing import Any
from zoneinfo import ZoneInfo

from .config import ConfigStore
from .poller import Poller, SourceDisabled
from .providers import flights as flights_mod
from .providers import timetable as timetable_mod
from .providers import transport as transport_mod
from .providers import weather as weather_mod
from .providers.routes import RouteResolver
from .util import make_session

logger = logging.getLogger(__name__)


class Services:
    def __init__(self, config: ConfigStore, routes: RouteResolver):
        self.config = config
        self.routes = routes
        self.session = make_session()
        cfg = lambda section, key, default: lambda: config.get()[section].get(key, default)  # noqa: E731
        self.pollers: dict[str, Poller] = {
            "flights": Poller("flights", self._fetch_flights, cfg("flights", "refresh_seconds", 15), max_backoff=120),
            "weather": Poller("weather", self._fetch_weather, cfg("weather", "refresh_seconds", 600)),
            "transport": Poller("transport", self._fetch_transport, cfg("transport", "refresh_seconds", 60)),
            "timetable": Poller("timetable", self._fetch_timetable, cfg("timetable", "refresh_seconds", 300)),
        }
        config.on_change(lambda _new: self.refresh_all())

    def start(self) -> None:
        for p in self.pollers.values():
            p.start()
        logger.info("Started %d data pollers", len(self.pollers))

    def stop(self) -> None:
        for p in self.pollers.values():
            p.stop()
        self.routes.flush()

    def refresh_all(self) -> None:
        for p in self.pollers.values():
            p.refresh_now()

    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.config.get()["location"]["timezone"])

    def snapshot(self) -> dict[str, Any]:
        return {name: p.to_dict() for name, p in self.pollers.items()}

    # --- fetchers ------------------------------------------------------------------
    def _fetch_flights(self) -> Any:
        c = self.config.get()
        fc = c["flights"]
        if not fc["enabled"]:
            raise SourceDisabled()
        lat, lon = c["location"]["lat"], c["location"]["lon"]
        raw, provider = flights_mod.fetch_aircraft(self.session, fc["providers"], lat, lon, fc["radius_km"])
        flights = flights_mod.normalize(raw, lat, lon, fc["radius_km"], fc["include_ground"])
        shown = flights[: fc["max_items"]]
        self.routes.annotate(shown, c["routes"])
        return shown, {"provider": provider, "total_in_range": len(flights)}

    def _fetch_weather(self) -> Any:
        c = self.config.get()
        if not c["weather"]["enabled"]:
            raise SourceDisabled()
        return weather_mod.fetch_weather(self.session, c["weather"], c["location"]["lat"], c["location"]["lon"])

    def _fetch_transport(self) -> Any:
        c = self.config.get()
        tc = c["transport"]
        if not tc["enabled"]:
            raise SourceDisabled()
        if not tc["stop_id"]:
            raise SourceDisabled("No stop selected")
        deps = transport_mod.fetch_departures(self.session, tc["stop_id"], self.tz(), tc["max_items"])
        return deps, {"stop_name": tc["stop_name"]}

    def _fetch_timetable(self) -> Any:
        c = self.config.get()
        if not c["timetable"]["enabled"]:
            raise SourceDisabled()
        return timetable_mod.fetch_lectures(self.session, c["timetable"], self.tz())
