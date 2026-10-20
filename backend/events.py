"""Official event calendar metadata, with robots checks and no article copying.

The operator's date-only calendar cannot certify show times, venue location,
tickets or a duration. Such records are discovery results, never invented stops
in a timed walking route. RSS publication dates are not event dates.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import os
import time
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

from .models import CalendarEvent, EventsContext
from .public_http import USER_AGENT, public_get

URL = "https://a-vm.kz/events/"
ROBOTS_URL = "https://a-vm.kz/robots.txt"
LOCAL = ZoneInfo("Asia/Almaty")
MONTHS = {name: index for index, names in enumerate([
    ("january", "января"), ("february", "февраля"), ("march", "марта"), ("april", "апреля"),
    ("may", "мая"), ("june", "июня"), ("july", "июля"), ("august", "августа"),
    ("september", "сентября"), ("october", "октября"), ("november", "ноября"), ("december", "декабря")], 1) for name in names}


def enabled():
    return os.getenv("QALA_EVENTS", "on").casefold() not in {"off", "0", "false", "disabled"}


def _date(text: str) -> str | None:
    match = re.fullmatch(r"\s*(\d{1,2})\s+([^\W\d_]+)\s+(\d{4})\s*", text.casefold())
    if not match or match[2] not in MONTHS:
        return None
    try:
        return date(int(match[3]), MONTHS[match[2]], int(match[1])).isoformat()
    except ValueError:
        return None


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.records: list[CalendarEvent] = []
        self._kind = None
        self._tag = None
        self._parts: list[str] = []
        self._pending = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "a" and "news-card__link" in classes:
            self._kind, self._tag, self._parts = "title", tag, []
            self._pending = {"url": attrs.get("href", "")}
        elif "news-card__date" in classes and self._pending:
            self._kind, self._tag, self._parts = "date", tag, []

    def handle_data(self, data):
        if self._kind and sum(map(len, self._parts)) < 1000:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag != self._tag or not self._pending:
            return
        text = re.sub(r"\s+", " ", " ".join(self._parts)).strip()
        if self._kind == "title":
            self._pending["title"] = text[:240]
        elif self._kind == "date":
            stamp, url = _date(text), self._pending["url"]
            parsed = urlsplit(url)
            if stamp and self._pending.get("title") and parsed.scheme == "https" and parsed.netloc == "a-vm.kz" and parsed.path.startswith("/events/") and not parsed.query and not parsed.fragment:
                self.records.append(CalendarEvent(id="avm-" + hashlib.sha256(url.encode()).hexdigest()[:16],
                                                  title=self._pending["title"], url=url, date=stamp))
            self._pending = None
        self._kind, self._tag, self._parts = None, None, []


def parse_calendar(html: str) -> list[CalendarEvent]:
    parser = CalendarParser()
    parser.feed(html)
    return list({record.url: record for record in parser.records}.values())[:100]


class OfficialEvents:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._expires = 0.0
        self._fetched_at: str | None = None
        self._checked_at: str | None = None
        self._verified = False
        self._records: list[CalendarEvent] = []

    def status(self):
        return {"enabled": enabled(), "live_verified": self._verified, "checked_at": self._checked_at}

    async def _load(self) -> bool:
        if time.monotonic() < self._expires:
            return True
        async with self._lock:
            if time.monotonic() < self._expires:
                return True
            self._checked_at = datetime.now(timezone.utc).isoformat()
            try:
                robots = (await public_get(ROBOTS_URL, max_bytes=100_000)).decode("utf-8")
                policy = RobotFileParser(ROBOTS_URL)
                policy.parse(robots.splitlines())
                if not policy.can_fetch(USER_AGENT, URL):
                    raise ValueError("Operator disallows calendar collection")
                raw = await public_get(URL, max_bytes=1_000_000)
                records = parse_calendar(raw.decode("utf-8"))
                # The public page is not an API contract: markup changes must
                # fail visibly rather than imply there are no events in town.
                if not records:
                    raise ValueError("No parseable dated calendar entries")
                self._records, self._fetched_at, self._verified = records, self._checked_at, True
                self._expires = time.monotonic() + 3600
            except Exception:
                self._records, self._fetched_at, self._verified = [], None, False
                self._expires = time.monotonic() + 300
            return False

    async def upcoming(self, at: datetime, *, days: int = 14) -> EventsContext:
        at = at.replace(tzinfo=LOCAL) if at.tzinfo is None else at.astimezone(LOCAL)
        stamp = at.date()
        if not enabled():
            return EventsContext(status="disabled", requested_date=stamp.isoformat())
        cached = await self._load()
        common = {"requested_date": stamp.isoformat(), "cached": cached, "fetched_at": self._fetched_at}
        if not self._verified:
            return EventsContext(status="unavailable", **common)
        end = stamp + timedelta(days=max(1, min(30, days)))
        records = sorted((record for record in self._records if stamp <= date.fromisoformat(record.date) < end), key=lambda record: (record.date, record.title))
        return EventsContext(status="available", **common, items=records[:12], matching_date_count=sum(record.date == stamp.isoformat() for record in records))
