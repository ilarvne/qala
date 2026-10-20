"""Bounded, local intent resolution for privacy-preserving conversational RAG.

Only allowlisted constraints cross turns. A client cannot supply remembered POI
facts, schedules, ratings or model instructions through this contract.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .models import RecommendRequest
from .retrieval import ALIASES, FINE_TYPES, INTEREST_CATEGORIES, infer_interests, interest_mentions

RESET = re.compile(r"\b(?:start over|new plan|reset|forget this plan)\b|начн[её]м заново|новый маршрут|жаңа жоспар", re.I)
ALTERNATIVE = re.compile(r"\b(?:alternatives?|something else|different places?|other options?|regenerate)\b|другие места|другой вариант|альтернатив|басқа орын|басқа нұсқа", re.I)
ADDITIVE = re.compile(r"\b(?:also|add|include|with kids|with children)\b|добав|ещ[её]|с реб[её]нком|баламен", re.I)
AIRPORT = re.compile(r"airport|flight|вылет|аэропорт|рейс|ұшақ|әуежай|ұшу", re.I)
# Bounded natural phrasing shared by total-budget exclusion and transfer
# extraction: e.g. "дорогу до аэропорта нужно 45 минут". Digits cannot be
# swallowed as connecting words, so a later flight deadline stays distinct.
TRANSFER_PREFIX = r"(?<!\w)(?:transfer|drive|taxi|дорог\w*|такси|трансфер)(?:\s+[^\W\d_][\w-]*){0,7}\s*(?:[—:]\s*)?"
ENVIRONMENT = re.compile(
    r"(?P<indoor>(?<!\w)(?:indoors?|inside)(?!\w)|внутри(?!\w)|(?:в|внутри)\s+(?:помещен\w*|здани\w*)|жабық(?:\s+(?:жер\w*|орын\w*))?|(?:ғимарат(?:тың)?\s+)?ішінде)"
    r"|(?P<outdoor>(?<!\w)(?:outdoors?|outside)(?!\w)|(?<!\w)open\s+air(?!\w)|на\s+(?:улице|свежем\s+воздухе)|ашық\s+ауада)", re.I)
PLACE_REQUEST = re.compile(
    r"\b(?:recommend|suggest|find|show)\b.{0,80}\b(?:nearby\s+places|places\s+(?:nearby|near\s+me|around\s+me))\b"
    r"|\b(?:recommend|suggest|find|show)\b.{0,50}\b(?:something|anything|a\s+place)\b.{0,30}\b(?:nearby|near\s+me)\b"
    r"|(?:подбери|подобрать|посоветуй|предложи|найди|покажи).{0,70}(?:(?:мест\w*|что-нибудь|что-то).{0,30}(?:рядом|поблизости)|(?:рядом|поблизости).{0,30}мест\w*)"
    r"|жақын\s+(?:жерлерді|орындарды)\s+(?:ұсын|тап|көрсет)"
    r"|жақын\s+жерде\s+не\s+істеуге", re.I)


def resolve_environment(message: str) -> dict:
    """One bounded negation-aware interpretation for filters and weather.

    Prefix negation covers English/Russian and suffix negation covers Kazakh.
    The last explicit environment clause wins. Merely allowing more than one
    environment ("not only indoors") clears the filter without preferring one.
    """
    indoor, outdoor = None, False
    text = message.casefold()
    for match in ENVIRONMENT.finditer(text):
        prefix = re.split(r"[,;.!?]|\b(?:but|instead|но|а)\b", text[max(0, match.start() - 70):match.start()])[-1]
        suffix = re.split(r"[,;.!?]|\b(?:but|instead|но|а)\b", text[match.end():match.end() + 45])[0]
        relaxed = bool(re.search(r"(?:not\s+(?:only|just)|не\s+только)\s*$", prefix))
        negative = bool(re.search(r"(?:\b(?:not|no|without|avoid|never|don['’]t)|\b(?:не|без|кроме|никаких))(?:\s+[\w-]+){0,3}\s*$", prefix)
                        or re.match(r"\s*(?:емес|жоқ)(?!\w)", suffix))
        if relaxed:
            indoor, outdoor = False, False
        else:
            indoor = (match.lastgroup == "indoor") != negative
            outdoor = not indoor
    return {"indoor": indoor, "explicit_outdoor": outdoor}


def minutes_in_message(message: str) -> int | None:
    """Understand explicit budgets, excluding walking/transfer sub-budgets."""
    value = message.casefold()
    if re.search(r"\bhalf an? hour\b|полчаса|жарты сағат", value):
        return 30
    if re.search(r"\b(?:an?|one) hour\b|бір сағат", value):
        return 60
    matches = re.finditer(r"(?<![\d:])(?P<first>\d+(?:[.,]\d+)?)\s*(?:[–—-]\s*(?P<last>\d+(?:[.,]\d+)?)\s*)?(?:[-–]\s*)?(?P<unit>minutes?|mins?|минут\w*|мин\.?|hours?|hrs?|час\w*|ч\.?|сағат)(?!\w)", value)
    for match in matches:
        prefix, suffix = re.split(r"[.!?;]", value[max(0, match.start() - 80):match.start()])[-1], re.split(r"[,;.!?]", value[match.end():match.end() + 35])[0]
        if re.search(r"(?:within|at most|max(?:imum)?|under|не более|до)\s*$", prefix) and re.search(r"walk|walking|пешком|жаяу", prefix + suffix):
            continue
        if re.search(r"минуттан?", match.group("unit")) and re.search(r"аспайтын\s+жаяу", suffix):
            continue
        if re.search(TRANSFER_PREFIX + r"$", prefix):
            continue
        if re.search(r"(?:to the airport|до аэропорта|әуежайға)", suffix):
            continue
        number = float((match.group("last") or match.group("first")).replace(",", "."))
        minutes = round(number * (60 if re.match(r"hour|hr|час|ч|сағат", match.group("unit")) else 1))
        return max(10, min(480, minutes))
    return None


def resolve_constraints(req: RecommendRequest, saved: dict | None, valid_ids: set[str]) -> dict:
    message = req.message
    reset = bool(RESET.search(message))
    prior = req.conversation.model_dump(exclude_none=True) if req.conversation and not reset else {}
    saved = saved or {}
    current, denied = interest_mentions(message)
    explicit = list(dict.fromkeys([x for x in req.interests if x in ALIASES] + infer_interests(" ".join(req.interests)) + current))
    category_intents = set(INTEREST_CATEGORIES) | {"events"}
    mentioned_categories = set(current) & category_intents
    inherited = prior.get("interests", saved.get("interests", []) if not reset else [])
    # A direct request for ordinary nearby places exits an event-only branch;
    # short date replies and refinements to the calendar retain its context.
    if "events" not in current and PLACE_REQUEST.search(message):
        inherited = [key for key in inherited if key != "events"]
        explicit = [key for key in explicit if key != "events"]
    if mentioned_categories and not ADDITIVE.search(message):
        inherited = [x for x in inherited if x not in category_intents or x == "family"]
        explicit = [x for x in explicit if x not in category_intents or x == "family" or x in mentioned_categories]
    interests = [x for x in dict.fromkeys([*inherited, *explicit]) if x in ALIASES and x not in denied]
    excluded_categories = set(req.excluded_categories) | set(prior.get("excluded_categories", saved.get("excluded_categories", []) if not reset else []))
    # An explicit new positive request can re-enable a previously excluded kind.
    for key in mentioned_categories - set(denied):
        excluded_categories.difference_update(INTEREST_CATEGORIES.get(key, set()))
    for key in denied:
        if key == "family":
            # "Without kids" clears a group constraint; museums and parks are
            # still valid for adults. A named playground exclusion is narrower.
            if re.search(r"playgrounds?|площадк|ойын алаң", message, re.I):
                excluded_categories.add("playground")
        elif key in FINE_TYPES:
            excluded_categories.add(key)
        else:
            excluded_categories.update(INTEREST_CATEGORIES.get(key, set()))
    explicit_budget = minutes_in_message(message)
    budget = explicit_budget or prior.get("duration_minutes") or (req.duration_minutes if "duration_minutes" in req.model_fields_set else saved.get("duration_minutes") or req.duration_minutes)
    accessible = req.accessible if "accessible" in req.model_fields_set else prior.get("accessible", saved.get("accessible", req.accessible))
    indoor = req.indoor if "indoor" in req.model_fields_set else prior.get("indoor", saved.get("indoor", req.indoor))
    if "accessible" in current:
        accessible = True
    if "accessible" in denied or re.search(r"remove (?:the )?accessibility filter|убрать фильтр доступности", message, re.I):
        accessible = False
        interests = [x for x in interests if x != "accessible"]
    environment = resolve_environment(message)
    outdoor_preference = bool(prior.get("outdoor_preference", False))
    if environment["indoor"] is not None:
        indoor = environment["indoor"]
        outdoor_preference = environment["explicit_outdoor"]
        if indoor:
            interests = list(dict.fromkeys([*interests, "indoor"]))
        else:
            interests = [x for x in interests if x != "indoor"]
    elif indoor:
        outdoor_preference = False
    group = prior.get("group_size", req.group_size)
    group_match = re.search(r"(?:group of|нас|топта)\s+(\d{1,2})\b|\bfor\s+(\d{1,2})\s+(?:people|persons?|adults?)\b", message, re.I)
    if group_match:
        number = int(next(value for value in group_match.groups() if value))
        if 1 <= number <= 20:
            group = number
    airport = bool(AIRPORT.search(message)) or bool(prior.get("airport"))
    if re.search(r"no (?:more )?flight|not flying|рейс отмен[её]н|без перел[её]та", message, re.I):
        airport = False
    transfer = req.airport_transfer_minutes if req.airport_transfer_minutes is not None else prior.get("airport_transfer_minutes")
    if airport:
        transfer_match = re.search(TRANSFER_PREFIX + r"(\d{1,3})\s*(?:minutes?|mins?|минут\w*|мин\.?)", message, re.I) or re.search(r"(?<!\d)(\d{1,3})\s*(?:minutes?|минут\w*|мин)\s*(?:to the airport|до аэропорта|әуежайға)", message, re.I)
        short_answer = re.fullmatch(r"\s*(\d{1,3})\s*(?:minutes?|mins?|минут\w*|мин|мин\.)?\s*[.!]?\s*", message, re.I)
        if transfer_match:
            transfer = min(240, int(next(group for group in transfer_match.groups() if group)))
        elif transfer is None and short_answer:
            transfer = min(240, int(short_answer[1]))
            budget = prior.get("duration_minutes", req.duration_minutes)
    max_walk = req.max_walk_minutes if req.max_walk_minutes is not None else prior.get("max_walk_minutes", saved.get("max_walk_minutes") if not reset else None)
    walk_match = re.search(r"(?:within|at most|max(?:imum)?|under|не более|до)\s*(\d{1,3})\s*(?:minutes?|mins?|минут\w*|мин)\s*(?:walk|walking|on foot|пешком|жаяу)", message, re.I)
    if walk_match:
        max_walk = max(1, min(120, int(walk_match[1])))
    reverse_walk = re.search(r"(?:walking|walk|on foot)\s*(?:time\s*)?(?:under|within|at most|maximum|max)\s*(\d{1,3})\s*(?:minutes?|mins?)|(\d{1,3})\s*минуттан?\s*аспайтын\s*жаяу", message, re.I)
    if reverse_walk:
        max_walk = max(1, min(120, int(next(value for value in reverse_walk.groups() if value))))
    if re.search(r"\bcloser\b|ближе|жақынырақ", message, re.I) and max_walk is None:
        max_walk = 10
    excluded = set(req.excluded_ids) | set(prior.get("excluded_ids", []))
    if req.regenerate or ALTERNATIVE.search(message):
        excluded.update(prior.get("last_recommendation_ids", []))
    ordinal = re.search(r"(?:skip|remove|without|убери|без)\s*(?:the\s*)?(first|second|third|1|2|3|перв\w*|втор\w*|трет\w*)", message, re.I)
    if ordinal:
        token = ordinal[1].casefold()
        index = 0 if token in {"first", "1"} or token.startswith("перв") else 1 if token in {"second", "2"} or token.startswith("втор") else 2
        previous_ids = prior.get("last_recommendation_ids", [])
        if index < len(previous_ids):
            excluded.add(previous_ids[index])
    event_date = prior.get("event_date")
    if "events" in interests:
        base = (req.starts_at or datetime.now()).date()
        explicit_date = re.search(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)", message)
        if explicit_date:
            try:
                event_date = date.fromisoformat(explicit_date[1]).isoformat()
            except ValueError:
                event_date = None
        elif re.search(r"\btomorrow\b|завтра|ертең", message, re.I):
            event_date = (base + timedelta(days=1)).isoformat()
        elif re.search(r"\btoday\b|\btonight\b|сегодня|бүгін", message, re.I):
            event_date = base.isoformat()
    else:
        event_date = None
    return {"interests": interests, "duration_minutes": budget, "accessible": bool(accessible), "indoor": bool(indoor),
            "group_size": group, "airport": airport, "airport_transfer_minutes": transfer if airport else None,
            "max_walk_minutes": max_walk, "excluded_ids": sorted(excluded & valid_ids)[:100],
            "excluded_categories": sorted(excluded_categories), "followup": bool(prior), "reset": reset,
            "last_recommendation_ids": [], "event_date": event_date, "outdoor_preference": outdoor_preference}
