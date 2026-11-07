"""Wires configuration, data sources and pollers together."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .announcements import AnnouncementStore
from .config import ConfigStore
from .poller import Poller, SourceDisabled
from .providers import flights as flights_mod
from .providers import news as news_mod
from .providers import timetable as timetable_mod
from .providers import transport as transport_mod
from .providers import weather as weather_mod
from .providers.routes import RouteResolver
from .ticker import AircraftEvents
from .util import make_session

logger = logging.getLogger(__name__)


class Services:
    def __init__(self, config: ConfigStore, routes: RouteResolver, announcements: AnnouncementStore):
        self.config = config
        self.routes = routes
        self.announcements = announcements
        self.aircraft_events = AircraftEvents()
        self.session = make_session()
        self._preview: tuple[str, float] | None = None  # (announcement id, until epoch)
        self._preview_lock = threading.Lock()
        cfg = lambda section, key, default: lambda: config.get()[section].get(key, default)  # noqa: E731
        self.pollers: dict[str, Poller] = {
            "flights": Poller("flights", self._fetch_flights, cfg("flights", "refresh_seconds", 15), max_backoff=120),
            "weather": Poller("weather", self._fetch_weather, cfg("weather", "refresh_seconds", 600)),
            "transport": Poller("transport", self._fetch_transport, cfg("transport", "refresh_seconds", 60)),
            "timetable": Poller("timetable", self._fetch_timetable, cfg("timetable", "refresh_seconds", 300)),
            "news": Poller("news", self._fetch_news, cfg("ticker", "refresh_seconds", 900), max_backoff=3600),
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
        tc = c["ticker"]
        if tc["enabled"]:
            self.aircraft_events.update(flights, tc["emergencies"], tc["notable_aircraft"])
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

    def _fetch_news(self) -> Any:
        tc = self.config.get()["ticker"]
        if not (tc["enabled"] and tc["news_enabled"]):
            raise SourceDisabled()
        return news_mod.fetch_news(self.session, tc)

    # --- ticker & announcements --------------------------------------------------------
    def ticker_items(self) -> list[dict[str, Any]]:
        """Everything the ticker should show right now (empty = hide the ticker)."""
        c = self.config.get()
        tc = c["ticker"]
        if not tc["enabled"]:
            return []
        items: list[dict[str, Any]] = []
        for a in self.announcements.active(datetime.now(self.tz()).date()):
            if a["in_ticker"] and a["title"]:
                text = a["title"] + (f" – {a['text']}" if a["text"] else "")
                items.append({"id": f"a:{a['id']}", "kind": "announcement", "text": text})
        if tc["emergencies"] or tc["notable_aircraft"]:
            items.extend(e for e in self.aircraft_events.items()
                         if (e["kind"] == "emergency" and tc["emergencies"])
                         or (e["kind"] == "aircraft" and tc["notable_aircraft"]))
        news = self.pollers["news"].snapshot
        if tc["news_enabled"] and news.data:
            items.extend({"id": f"n:{n['id']}", "kind": "news", "text": n["title"], "source": n["source"],
                          "published": n["published"]} for n in news.data)
        return items

    def slides(self) -> list[dict[str, Any]]:
        if not self.config.get()["announcements"]["slides_enabled"]:
            return []
        return [_slide(a) for a in self.announcements.active(datetime.now(self.tz()).date()) if a["as_slide"]]

    def preview(self, ann_id: str, seconds: float) -> None:
        with self._preview_lock:
            self._preview = (ann_id, time.time() + seconds)

    def current_preview(self) -> dict[str, Any] | None:
        """An announcement the admin asked to show right now, as a slide."""
        with self._preview_lock:
            if not self._preview or self._preview[1] < time.time():
                self._preview = None
                return None
            ann_id, until = self._preview
        a = self.announcements.get(ann_id)
        return {**_slide(a), "until": until} if a else None


def _slide(a: dict[str, Any]) -> dict[str, Any]:
    return {"id": a["id"], "title": a["title"], "text": a["text"],
            "image": f"/media/{a['image']}" if a["image"] else None,
            "fit": a.get("image_fit", "contain")}
