from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str = Field(default="Astana", max_length=150)


class ConversationContext(BaseModel):
    """Client-held planning state, never a source of POI facts or durable chat."""
    model_config = ConfigDict(extra="forbid")
    interests: list[str] = Field(default_factory=list, max_length=20)
    excluded_ids: list[str] = Field(default_factory=list, max_length=100)
    last_recommendation_ids: list[str] = Field(default_factory=list, max_length=3)
    excluded_categories: list[str] = Field(default_factory=list, max_length=20)
    duration_minutes: int | None = Field(default=None, ge=10, le=480)
    accessible: bool | None = None
    indoor: bool | None = None
    group_size: int | None = Field(default=None, ge=1, le=20)
    airport: bool = False
    airport_transfer_minutes: int | None = Field(default=None, ge=0, le=240)
    max_walk_minutes: int | None = Field(default=None, ge=1, le=120)
    event_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    outdoor_preference: bool = False

    @field_validator("event_date")
    @classmethod
    def valid_event_date(cls, value):
        return date.fromisoformat(value).isoformat() if value is not None else None

    @field_validator("interests", "excluded_ids", "last_recommendation_ids", "excluded_categories")
    @classmethod
    def bounded_tokens(cls, value):
        return list(dict.fromkeys(str(x).strip()[:100] for x in value if str(x).strip()))


class RecommendRequest(BaseModel):
    message: str = Field(default="A walk nearby", max_length=3000)
    location: Location = Field(default_factory=lambda: Location(lat=51.0897, lon=71.4073, label="Mega Silk Way · simulated location"))
    duration_minutes: int = Field(default=60, ge=10, le=480)
    interests: list[str] = Field(default_factory=list, max_length=20)
    language: Literal["en", "ru", "kk"] = "en"
    accessible: bool = False
    indoor: bool = False
    group_size: int = Field(default=1, ge=1, le=20)
    session_id: str | None = Field(default=None, min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    remember: bool = False
    memory_generation: int | None = Field(default=None, ge=0)
    use_saved_preferences: bool = True
    starts_at: datetime | None = None
    airport_transfer_minutes: int | None = Field(default=None, ge=0, le=240)
    conversation: ConversationContext | None = None
    excluded_ids: list[str] = Field(default_factory=list, max_length=100)
    excluded_categories: list[str] = Field(default_factory=list, max_length=20)
    max_walk_minutes: int | None = Field(default=None, ge=1, le=120)
    regenerate: bool = False

    @field_validator("interests")
    @classmethod
    def short_interests(cls, value):
        return [str(x).strip()[:80] for x in value if str(x).strip()]


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2500)
    language: Literal["en", "ru", "kk"] = "en"


class VoiceSessionRequest(BaseModel):
    # Spoken conversation locale is independent from the three planner/UI locales.
    language: Literal["en", "ru", "kk", "de", "fr", "es", "zh", "ar", "tr", "hi", "ja", "ko", "uk", "it", "ky", "az"] = "en"


class MemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent: Literal[True]
    memory_generation: int | None = Field(default=None, ge=0)
    interests: list[str] = Field(default_factory=list, max_length=20)
    language: Literal["en", "ru", "kk"] | None = None
    duration_minutes: int | None = Field(default=None, ge=10, le=480)
    accessible: bool | None = None
    indoor: bool | None = None
    excluded_categories: list[str] | None = Field(default=None, max_length=20)
    max_walk_minutes: int | None = Field(default=None, ge=1, le=120)


class Explanation(BaseModel):
    """An LLM may choose trusted presentation options, never response prose."""
    model_config = ConfigDict(extra="forbid")
    poi_id: str = Field(min_length=1, max_length=100)
    source_url: str = Field(min_length=1, max_length=500)
    evidence_focus: Literal["category", "time", "category_and_time"]
    action_kind: Literal["coffee_pause", "public_walk", "family_play", "ask_museum", "indoor_break", "public_view", "viewpoint_pause", "confirm_access"]


class Narrative(BaseModel):
    """Bounded model selection. No arbitrary model text enters the response."""
    model_config = ConfigDict(extra="forbid")
    intro_style: Literal["warm", "concise"]
    explanations: list[Explanation] = Field(min_length=1, max_length=3)


class WeatherContext(BaseModel):
    """Public city forecast; never a claim about a particular path's safety."""
    status: Literal["available", "unavailable", "disabled", "outside_forecast", "outside_city"]
    provider: Literal["Open-Meteo"] = "Open-Meteo"
    city: Literal["Astana"] = "Astana"
    source_url: str = "https://open-meteo.com/en/docs"
    attribution: str = "Weather data by Open-Meteo (CC BY 4.0)"
    fetched_at: str | None = None
    cached: bool = False
    valid_at: str
    window_end: str
    temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    wind_kmh: float | None = None
    gust_kmh: float | None = None
    precipitation_mm: float | None = None
    precipitation_probability: float | None = None
    weather_code: int | None = None
    is_day: bool | None = None
    reason_codes: list[Literal["cold", "heat", "wind", "precipitation", "thunderstorm"]] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)
    scope: str = "City forecast, not conditions at a particular street"


class CalendarEvent(BaseModel):
    id: str
    title: str
    url: str
    date: str
    start_time: None = None
    date_precision: Literal["day"] = "day"
    venue: None = None
    poi_id: None = None
    availability: Literal["unverified"] = "unverified"


class EventsContext(BaseModel):
    status: Literal["available", "unavailable", "disabled"]
    provider: Literal["Astana Venue Management"] = "Astana Venue Management"
    source_url: str = "https://a-vm.kz/events/"
    fetched_at: str | None = None
    cached: bool = False
    requested_date: str
    items: list[CalendarEvent] = Field(default_factory=list)
    matching_date_count: int = 0
    scope: str = "Official calendar metadata; confirm time, venue and tickets at source"


class IntegrationCapability(BaseModel):
    id: str
    name: str
    status: Literal["active", "configured", "available", "key_required", "restricted", "unavailable", "disabled", "not_integrated"]
    configured: bool
    live_verified: bool = False
    last_checked_at: str | None = None
    source_url: str
    detail: str
    capabilities: list[str] = Field(default_factory=list)


class IntegrationsResponse(BaseModel):
    checked_at: str
    integrations: list[IntegrationCapability]
