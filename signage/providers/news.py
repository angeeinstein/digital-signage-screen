"""Aviation news headlines from RSS/Atom feeds, for the ticker.

Only headlines are shown, with the feed's name, so the ticker credits its
source. Feeds that were checked (2026-11):

* Austrian Wings and FlightGlobal publish RSS and answer automated clients.
* The Aviation Herald has no public feed, and Aviation Safety Network
  answers 403 to non-browser clients, so neither can be used.
* Google News search feeds work, but return many follow-up and local stories.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from ..util import DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)

MAX_FEED_BYTES = 3 * 1024 * 1024
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"
RSS1 = "{http://purl.org/rss/1.0/}"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(text: str | None) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    return _WS_RE.sub(" ", text).strip()


def _parse_date(text: str | None) -> datetime | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)  # RSS: RFC 822
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))  # Atom / Dublin Core: ISO 8601
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _source_name(title: str, url: str) -> str:
    """Short feed name: "Austrian Wings - Österreichs Luftfahrtmagazin" -> "Austrian Wings"."""
    name = re.split(r"\s+[-|–:]\s+", _clean(title), maxsplit=1)[0]
    if not name:
        name = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return name[:40]


def parse_feed(content: bytes, url: str) -> list[dict[str, Any]]:
    """Parse RSS 2.0, RSS 1.0 (RDF) or Atom into headline dicts."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise ValueError(f"not a valid feed ({e})") from None

    if root.tag == f"{ATOM}feed":
        source = _source_name(root.findtext(f"{ATOM}title") or "", url)
        entries = []
        for e in root.findall(f"{ATOM}entry"):
            link_el = e.find(f"{ATOM}link[@rel='alternate']")
            if link_el is None:
                link_el = e.find(f"{ATOM}link")
            entries.append((
                e.findtext(f"{ATOM}title"),
                link_el.get("href") if link_el is not None else "",
                e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated"),
                e.findtext(f"{ATOM}id"),
            ))
    else:
        channel = root.find("channel")
        if channel is None:
            channel = root.find(f"{RSS1}channel")
        if channel is None:
            raise ValueError("not an RSS or Atom feed")
        source = _source_name(channel.findtext("title") or channel.findtext(f"{RSS1}title") or "", url)
        items = channel.findall("item") or root.findall(f"{RSS1}item")
        entries = [
            (
                i.findtext("title") or i.findtext(f"{RSS1}title"),
                i.findtext("link") or i.findtext(f"{RSS1}link"),
                i.findtext("pubDate") or i.findtext(f"{DC}date"),
                i.findtext("guid"),
            )
            for i in items
        ]

    out = []
    for title, link, date, guid in entries:
        title = _clean(title)
        if not title:
            continue
        link = (link or "").strip()
        published = _parse_date(date)
        key = (guid or link or title).strip()
        out.append({
            "id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:12],
            "title": title[:300],
            "link": link,
            "source": source,
            "published": published.isoformat() if published else None,
        })
    return out


def keyword_list(keywords: str) -> list[str]:
    return [k.strip().casefold() for k in re.split(r"[,\n]", keywords or "") if k.strip()]


def select_headlines(items: list[dict[str, Any]], keywords: str, max_age_hours: int, limit: int,
                     now: datetime | None = None) -> list[dict[str, Any]]:
    """Recent headlines matching a keyword, newest first, without duplicates."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)
    words = keyword_list(keywords)
    seen: set[str] = set()
    picked = []
    for item in items:
        published = _parse_date(item.get("published"))
        if published is None or published < cutoff or published > now + timedelta(hours=1):
            continue  # undated items can't be checked for age, so skip them
        title_key = re.sub(r"\W+", "", item["title"].casefold())
        if title_key in seen:
            continue
        if words and not any(w in item["title"].casefold() for w in words):
            continue
        seen.add(title_key)
        picked.append(item)
    picked.sort(key=lambda i: i["published"], reverse=True)
    return picked[:limit]


def fetch_feed(session: requests.Session, url: str) -> list[dict[str, Any]]:
    resp = session.get(url, timeout=DEFAULT_TIMEOUT, stream=True)
    try:
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        chunks, size = [], 0
        for chunk in resp.iter_content(64 * 1024):
            size += len(chunk)
            if size > MAX_FEED_BYTES:
                raise ValueError("feed is too large")
            chunks.append(chunk)
        content = b"".join(chunks)
    finally:
        resp.close()
    return parse_feed(content, url)


def fetch_news(session: requests.Session, cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch all configured feeds. Fails only if every feed fails."""
    urls = [u.strip() for u in (cfg.get("news_feeds") or "").splitlines() if u.strip()]
    if not urls:
        return [], {"feeds": 0}
    items: list[dict[str, Any]] = []
    errors = []
    for url in urls:
        try:
            items.extend(fetch_feed(session, url))
        except (requests.RequestException, ValueError) as e:
            logger.info("News feed %s failed: %s", url, e)
            errors.append(f"{url}: {e}")
    if errors and len(errors) == len(urls):
        raise RuntimeError("; ".join(errors))
    headlines = select_headlines(items, cfg.get("news_keywords", ""), cfg["news_max_age_hours"],
                                 cfg["news_max_items"])
    return headlines, {"feeds": len(urls), "failed": errors, "checked": len(items)}
