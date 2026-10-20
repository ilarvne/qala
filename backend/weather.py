"""Fixed-city, bounded Open-Meteo forecast with single-flight memory caching.

Exact user coordinates, messages and session identifiers never leave the app.
Weather is a soft ranking signal. Explicit filters and source hours remain hard
constraints; a model forecast cannot certify access or a safe walking surface.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import WeatherContext
from .public_http import public_get

CITY = (51.1282, 71.4304)
LOCAL = ZoneInfo("Asia/Almaty")
URL = "https://api.open-meteo.com/v1/forecast"
FIELDS = ("temperature_2m", "apparent_temperature", "wind_speed_10m", "wind_gusts_10m",
          "precipitation", "precipitation_probability", "weather_code", "is_day")
GUIDANCE = {
    "en": {"cold": "The forecast feels like −10 °C or colder; consider shorter outdoor sections and a warm indoor stop.", "heat": "The forecast feels like 32 °C or warmer; consider shade, water and an indoor break.", "wind": "Forecast wind reaches 40 km/h or gusts reach 60 km/h; consider a sheltered alternative.", "precipitation": "Precipitation is forecast during this visit; consider shelter and check conditions before leaving.", "thunderstorm": "A thunderstorm is forecast during this visit; check local alerts and consider postponing outdoor sections."},
    "ru": {"cold": "По прогнозу ощущается −10 °C или холоднее: сократите участки на улице и предусмотрите тёплую остановку.", "heat": "По прогнозу ощущается 32 °C или теплее: предусмотрите тень, воду и перерыв в помещении.", "wind": "По прогнозу ветер от 40 км/ч или порывы от 60 км/ч: рассмотрите защищённый от ветра вариант.", "precipitation": "На время прогулки прогнозируются осадки: предусмотрите укрытие и проверьте условия перед выходом.", "thunderstorm": "На время прогулки прогнозируется гроза: проверьте местные предупреждения и рассмотрите перенос участков на улице."},
    "kk": {"cold": "Болжам бойынша −10 °C немесе одан суық сезіледі: сырттағы бөліктерді қысқартып, жылы жерде аялдаңыз.", "heat": "Болжам бойынша 32 °C немесе одан ыстық сезіледі: көлеңке, су және жабық жерде үзіліс қарастырыңыз.", "wind": "Болжамдағы жел 40 км/сағ немесе екпіні 60 км/сағ-қа жетеді: ықтасын балама қарастырыңыз.", "precipitation": "Серуен кезінде жауын-шашын болжанады: пана қарастырып, шығар алдында жағдайды тексеріңіз.", "thunderstorm": "Серуен кезінде найзағай болжанады: жергілікті ескертулерді тексеріп, сырттағы бөліктерді кейінге қалдыруды қарастырыңыз."},
}


def enabled() -> bool:
    return os.getenv("QALA_WEATHER", "on").casefold() not in {"off", "0", "false", "disabled"}


def _number(value, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("Invalid forecast value")
    return float(value)


def parse_forecast(payload: dict) -> list[dict]:
    hourly = payload.get("hourly", {})
    times = hourly.get("time")
    units = payload.get("hourly_units", {})
    expected = {"temperature_2m": "°C", "apparent_temperature": "°C", "wind_speed_10m": "km/h", "wind_gusts_10m": "km/h", "precipitation": "mm", "precipitation_probability": "%", "weather_code": "wmo code", "is_day": ""}
    if not isinstance(times, list) or not 2 <= len(times) <= 500 or any(units.get(key) != unit for key, unit in expected.items()):
        raise ValueError("Unexpected forecast units or length")
    if any(not isinstance(hourly.get(key), list) or len(hourly[key]) != len(times) for key in FIELDS):
        raise ValueError("Incomplete forecast series")
    rows = []
    for index, stamp in enumerate(times):
        at = datetime.fromtimestamp(_number(stamp, 0, 4_102_444_800), timezone.utc).astimezone(LOCAL)
        if rows and at - rows[-1]["at"] != timedelta(hours=1):
            raise ValueError("Non-contiguous hourly forecast")
        ranges = ((-100, 70), (-120, 90), (0, 500), (0, 600), (0, 500), (0, 100), (0, 99), (0, 1))
        values = [_number(hourly[key][index], *bounds) for key, bounds in zip(FIELDS, ranges)]
        if values[-2] != int(values[-2]) or values[-1] not in {0, 1}:
            raise ValueError("Invalid weather code or daylight value")
        rows.append({"at": at, **dict(zip(FIELDS, values))})
    return rows


class CityWeather:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._rows: list[dict] = []
        self._expires = 0.0
        self._fetched_at: str | None = None
        self._verified = False
        self._checked_at: str | None = None

    def status(self) -> dict:
        return {"enabled": enabled(), "live_verified": self._verified, "checked_at": self._checked_at}

    async def _load(self) -> bool:
        if time.monotonic() < self._expires:
            return True
        async with self._lock:
            if time.monotonic() < self._expires:
                return True
            self._checked_at = datetime.now(timezone.utc).isoformat()
            try:
                raw = await public_get(URL, params={"latitude": CITY[0], "longitude": CITY[1], "hourly": ",".join(FIELDS),
                                                    "timezone": "Asia/Almaty", "timeformat": "unixtime", "wind_speed_unit": "kmh",
                                                    "forecast_days": 16, "past_days": 1})
                rows = parse_forecast(json.loads(raw))
                self._rows, self._fetched_at, self._verified = rows, self._checked_at, True
                self._expires = time.monotonic() + 900
            except Exception:
                self._rows, self._fetched_at, self._verified = [], None, False
                self._expires = time.monotonic() + 120
            return False

    async def forecast(self, at: datetime, minutes: int, *, language: str = "en", in_city: bool = True) -> WeatherContext:
        at = at.replace(tzinfo=LOCAL) if at.tzinfo is None else at.astimezone(LOCAL)
        end = at + timedelta(minutes=max(0, min(480, minutes)))
        base = {"valid_at": at.isoformat(), "window_end": end.isoformat()}
        if not enabled():
            return WeatherContext(status="disabled", **base)
        if not in_city:
            return WeatherContext(status="outside_city", **base)
        now = datetime.now(LOCAL)
        if at < now - timedelta(days=1) or end > now + timedelta(days=15):
            return WeatherContext(status="outside_forecast", **base)
        cached = await self._load()
        base.update(fetched_at=self._fetched_at, cached=cached)
        if not self._rows:
            return WeatherContext(status="unavailable", **base)
        # Instantaneous values use the visit's containing hour. Precipitation
        # is a preceding-hour total, so include the following boundary too.
        begin = at.replace(minute=0, second=0, microsecond=0)
        until = end.replace(minute=0, second=0, microsecond=0) + (timedelta(hours=1) if end.minute or end.second else timedelta())
        rows = [row for row in self._rows if begin <= row["at"] <= until]
        if not rows or rows[0]["at"] != begin or rows[-1]["at"] != until:
            return WeatherContext(status="outside_forecast", **base)
        current = rows[0]
        minimum, maximum = min(row["apparent_temperature"] for row in rows), max(row["apparent_temperature"] for row in rows)
        wind, gust = max(row["wind_speed_10m"] for row in rows), max(row["wind_gusts_10m"] for row in rows)
        precipitation = sum(row["precipitation"] for row in rows[1:] or rows)
        probability = max(row["precipitation_probability"] for row in rows)
        reasons = []
        if minimum <= -10: reasons.append("cold")
        if maximum >= 32: reasons.append("heat")
        if wind >= 40 or gust >= 60: reasons.append("wind")
        if precipitation >= .5 or probability >= 60: reasons.append("precipitation")
        if any(row["weather_code"] in {95, 96, 99} for row in rows): reasons.append("thunderstorm")
        return WeatherContext(status="available", **base, temperature_c=current["temperature_2m"], apparent_temperature_c=current["apparent_temperature"],
                              wind_kmh=round(wind, 1), gust_kmh=round(gust, 1), precipitation_mm=round(precipitation, 2),
                              precipitation_probability=probability, weather_code=int(current["weather_code"]), is_day=bool(current["is_day"]),
                              reason_codes=reasons, guidance=[GUIDANCE.get(language, GUIDANCE["en"])[reason] for reason in reasons])
