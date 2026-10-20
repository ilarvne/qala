#!/usr/bin/env python3
"""Reproduce six Russian brief inputs against the current local FastAPI corpus.

Uses the real LangGraph. Every provider is disabled after main has loaded .env;
the memory database is temporary. The 35 checks are constraint/provenance
invariants, not a venue-opening test or an independent relevance score.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.main import app
from backend.agent import listed_visit_status

OUTPUT = ROOT / "artifacts/brief-scenarios-ru.json"
AT = "2026-10-20T14:00:00+05:00"
MEGA = {"lat": 51.0897, "lon": 71.4073, "label": "MEGA / EXPO — тестовая точка"}
CENTRE = {"lat": 51.1283, "lon": 71.4305, "label": "Байтерек — тестовая точка"}
COMMON = {"language": "ru", "starts_at": AT, "remember": False, "use_saved_preferences": False}
CASES = [
    ("C1-mega-walk", {"message": "Я возле Mega Silk Way. Хочу прогулку на 45 минут.", "duration_minutes": 45, "location": MEGA}),
    ("C2-quiet-coffee", {"message": "Хочу тихое место с кофе и розеткой недалеко от меня.", "duration_minutes": 60, "location": MEGA}),
    ("C3-family", {"message": "Еду с ребёнком. Где рядом детская площадка или музей с интерактивами?", "duration_minutes": 90, "group_size": 3, "location": CENTRE}),
    ("C4-airport-unknown", {"message": "Я турист, у меня 2 часа перед вылетом. Что можно посмотреть поблизости?", "duration_minutes": 120,
                          "location": {"lat": 51.0222, "lon": 71.4669, "label": "Аэропорт — тестовая точка"}}),
    ("C4-airport-40min", {"message": "Я турист, у меня 2 часа перед вылетом. На дорогу до аэропорта нужно 40 минут.", "duration_minutes": 120,
                        "airport_transfer_minutes": 40, "location": MEGA}),
    ("C5-late-night", {"message": "Ищу необычную ночную активность на ближайшие 2 часа.", "duration_minutes": 120,
                     "starts_at": "2026-10-20T23:00:00+05:00", "location": CENTRE}),
]
KEYS = ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "TWILIO_AUTH_TOKEN", "VOICE_TOOL_SECRET",
        "ALEMPLUS_API_KEY", "ALEMPLUS_EMBED_KEY", "ALEMPLUS_RERANK_KEY", "ALEMPLUS_STT_KEY", "ALEMPLUS_STT_KK_KEY")


def check_result(case_id, payload, result, by_id):
    places, route, context = result["recommendations"], result["route"], result["context"]
    airport = case_id.startswith("C4-")
    def source_matches(place):
        original = by_id.get(place.get("id"))
        if not original:
            return False
        return (place["source"] == original["source"] and place["lat"] == original["lat"]
                and place["lon"] == original["lon"] and place["category"] == original["category"])
    def hours_fit(place):
        independently_checked = listed_visit_status(place.get("hours"), datetime.fromisoformat(place["arrival_time"]), place["visit_minutes"])
        return independently_checked != "listed_closed" and place["hours_status"] == independently_checked and (
            case_id != "C5-late-night" or independently_checked == "listed_open")
    calculated = sum(place["walk_minutes"] + place["visit_minutes"] for place in places) + route.get("buffer_minutes", 0)
    checks = {
        "at_most_three": 0 <= len(places) <= 3 if airport else 1 <= len(places) <= 3,
        "source_ids_only": all(source_matches(place) for place in places),
        "within_budget": 0 <= route["total_minutes"] == calculated <= context["available_minutes"] <= payload["duration_minutes"],
        "why_action_visit_present": all(isinstance(place.get("why"), str) and bool(place["why"].strip())
                                       and isinstance(place.get("action"), str) and bool(place["action"].strip())
                                       and place["visit_minutes"] > 0 and place["action_origin"] == "generated visit suggestion; not a verified event" for place in places),
        "no_known_closed_places": all(hours_fit(place) for place in places),
    }
    if case_id == "C2-quiet-coffee":
        checks["cafe_only"] = bool(places) and all(place["category"] == "cafe" for place in places)
        checks["socket_uncertainty"] = (any("розет" in warning.casefold() and "не подтвержден" in warning.casefold()
                                           for warning in context.get("missing_data", []))
                                        and all(not by_id[place["id"]].get("amenities", {}).get("power_supply") for place in places))
    if airport:
        stated_transfer = payload.get("airport_transfer_minutes")
        expected_available = max(0, payload["duration_minutes"] - 90 - stated_transfer) if stated_transfer is not None else 0
        checks["honest_no_excursion"] = (not places and not route["coordinates"] and route["total_minutes"] == 0
                                         and context["available_minutes"] == expected_available == 0
                                         and context["airport_reserve_minutes"] == 90 and context["airport_transfer_minutes"] == stated_transfer)
    if case_id == "C4-airport-unknown":
        checks["transfer_clarification"] = (context["airport_transfer_required"] is True
                                            and any(item["field"] == "airport_transfer_minutes" for item in result["clarifications"]))
    return {key: bool(value) for key, value in checks.items()}



def write_document(report):
    cases = {case["id"]: case for case in report["scenarios"]}
    def stops(case_id):
        places = cases[case_id]["result"]["recommendations"]
        return "; ".join(f"«{place['name']}» ({place['category']}, {place['id']}; часы: {place.get('hours') or 'не указаны'})" for place in places) or "остановок нет"
    def sources(case_id):
        return ", ".join(f"[{place['name']}]({place['source']['url']})" for place in cases[case_id]["result"]["recommendations"])
    def timing(case_id):
        route = cases[case_id]["result"]["route"]
        return f"{route['total_minutes']} минут: {route['walk_minutes']} пешком + {route.get('visit_minutes', 0)} на месте + {route.get('buffer_minutes', 0)} запаса"
    c1, c2, c3, c4, c4b, c5 = (cases[key] for key, _ in CASES)
    text = f"""# Проверка пяти сценариев задания Build with AI

Это воспроизводимые проверки ограничений и происхождения данных, а не оценка жюри или обещание доступности заведений. Реальный FastAPI/LangGraph обработал шесть фиксированных русских входов по текущему каталогу из {report['dataset_count']:,} POI, собранному из OpenStreetMap, Overture Maps и Wikidata. Облачные ключи были пустыми; погода, события и облачные модели отключены после загрузки dotenv. Память использовала временную базу. Координаты и время заданы для теста, а не являются историей перемещений человека.

Полные входы, ответы и **{report['passed']} выполненных проверок из {report['total']}** сохранены в [brief-scenarios-ru.json](../artifacts/brief-scenarios-ru.json). Эти инварианты не измеряют субъективную полезность или полноту всех мест города. Локальный feature-hash индекс выбран для воспроизводимости; рабочий локальный нейронный индекс и облачное ранжирование могут изменить порядок.

Во всех случаях: русский язык, память и применение сохранённых предпочтений выключены. Дневное тестовое время - 2026-10-20T14:00:00+05:00, ночное - 23:00; часовой пояс Asia/Almaty. Итоговые минуты ниже - оценка планировщика до проверки пешеходного пути. В приложении Valhalla уточняет маршрут; превышение бюджета блокирует запуск навигации.

## C1. Прогулка у MEGA Silk Way на 30-60 минут

**Ввод:** «{c1['input']['message']}» Координаты 51.0897, 71.4073; бюджет 45 минут.

**Ожидание:** одно-три собранных места поблизости, короткое «почему», конкретное занятие, время на дорогу и посещение. План укладывается в 45 минут; лишняя остановка не добавляется ради количества.

**Получено:** {stops(c1['id'])}. Оценка {timing(c1['id'])}. Действие из ответа: «{c1['result']['recommendations'][0]['action']}». {sources(c1['id'])}.

**Ограничения:** название и категория скопированы из источника. Если расписания нет, ответ не подтверждает открытый вход или работу оборудования. Погода и состояние дорожек в этом автономном прогоне не проверялись.

**Проверки:** одна-три точки, исходные POI ID/координаты/категория/источник, сумма времени в пределах бюджета, объяснение и действие, отсутствие известного закрытого места.

## C2. Тихое кафе с кофе и розеткой

**Ввод:** «{c2['input']['message']}» Координаты 51.0897, 71.4073; бюджет 60 минут.

**Ожидание:** только кафе; тишина и удобства подтверждаются источником либо остаются неизвестными.

**Получено:** {stops(c2['id'])}. Оценка {timing(c2['id'])}. Ответ прямо указывает, что розетки и тихие места не подтверждены; удобства предлагается уточнить при входе. {sources(c2['id'])}.

**Ограничения:** у выбранного места нет явного power_supply. Опубликованные часы не доказывают открытый вход сейчас. Отсутствие отзывов не используется как подтверждение тишины.

**Проверки:** общие инварианты, только cafe и явное предупреждение о неподтверждённых розетках.

## C3. Прогулка с ребёнком: площадка или музей

**Ввод:** «{c3['input']['message']}» Координаты 51.1283, 71.4305; бюджет 90 минут; группа из трёх человек.

**Ожидание:** семейно релевантная категория, реалистичные переходы и посещение. Нельзя обещать интерактивные экспонаты, детскую программу и оборудование без сведений.

**Получено:** {stops(c3['id'])}. Оценка {timing(c3['id'])}. Контекст содержит группу из {c3['result']['context']['group_size']} человек. Действие: «{c3['result']['recommendations'][0]['action']}». {sources(c3['id'])}.

**Ограничения:** музейная категория не доказывает интерактивы или детскую программу. Часы и вместимость требуют проверки по источнику. {c3['result']['route']['walk_minutes']} минут пешком могут быть неудобны с маленьким ребёнком: нужно уточнить предел ходьбы или сменить старт. Ответ не объявляется идеальным семейным маршрутом.

**Проверки:** общие инварианты. Категория, группа и отсутствие обещания интерактивов дополнительно видны в полном ответе; они не объявляются отдельными автоматическими проверками внутри числа 35.

## C4. Турист: два часа до вылета

**Первый ввод:** «{c4['input']['message']}» Точка у аэропорта 51.0222, 71.4669; бюджет 120 минут; трансфер неизвестен.

**Ожидание:** сначала запросить актуальную оценку дороги до аэропорта, затем учесть формальности. Не скрывать возвращение и регистрацию внутри обещания экскурсии.

**Получено:** прогулка не построена; есть уточнение airport_transfer_minutes. Резерв на аэропорт и регистрацию - {c4['result']['context']['airport_reserve_minutes']} минут.

**Второй ввод:** «{c4b['input']['message']}» Старт у MEGA/EXPO, бюджет 120 минут, явно заданный трансфер {c4b['input']['airport_transfer_minutes']} минут.

**Получено:** доступный бюджет max(0, 120 - {c4b['result']['context']['airport_reserve_minutes']} - {c4b['result']['context']['airport_transfer_minutes']}) = {c4b['result']['context']['available_minutes']}; остановок нет.

**Ограничения:** 90 минут - консервативное правило прототипа, а не инструкция авиакомпании. Трансфер задан пользователем, это не прогноз пробок. Требования рейса и контроль безопасности нужно уточнить отдельно.

**Проверки:** общие инварианты, отсутствие экскурсии в обоих случаях; при неизвестном трансфере - запрос недостающего значения.

## C5. Необычная ночная активность

**Ввод:** «{c5['input']['message']}» Координаты 51.1283, 71.4305; бюджет 120 минут; время 2026-10-20T23:00:00+05:00.

**Ожидание:** подходящее опубликованное расписание на весь визит; никаких выдуманных сегодняшних вечеринок, крыш, разрешений доступа или гарантий безопасности.

**Получено:** {stops(c5['id'])}. Оценка {timing(c5['id'])}. Действия предлагают уточнить возрастные ограничения, правила входа и обратную дорогу. {sources(c5['id'])}.

**Ограничения:** это подбор заведений, а не афиша. Отдельная новая интеграция официального календаря проверена в [agent-context-live-verification.json](../artifacts/agent-context-live-verification.json); в этих шести входах она отключена. Текущий вход, освещение, транспорт и безопасность пути не проверены. Возраст и правила входа нужно уточнить.

**Проверки:** общие инварианты; ночное расписание независимо проверяется для прибытия и полной длительности посещения.

## Дополнительные условия приёмки и отдельные доказательства

| Проверка | Условие | Доказательство и область |
| --- | --- | --- |
| Геолокация отклонена | Можно выбрать точку без повторного запроса разрешения | Браузерные проверки интерфейса на прежнем каталоге из 6 222 POI |
| Понедельник в музее | Не обещать вход при закрытом расписании | Backend-тесты расписаний и атрибутированные операторские фрагменты |
| Коляска | Только явный wheelchair=yes; доступность улиц не гарантируется | Backend-тесты фильтра |
| Явные настройки после диалога | Старый текст не отменяет новый выбор | [Проверки React-хука](../artifacts/planner-hook-race-verification.json) |
| Удаление памяти | Поздний ответ не восстанавливает удалённый профиль | Тесты поколений согласия и React-хука |
| Помещение и улица | EN/RU/KK отрицание одинаково учитывается фильтром и погодой | [89 focused tests](../artifacts/agent-context-focused-verification.json) |
| Календарь | Дата и ссылка не превращаются в выдуманный timed POI | [Живая проверка контекста](../artifacts/agent-context-live-verification.json) |
| Публикация данных | При ошибке сохраняются JSON/CSV/GeoJSON и атрибуции | [Проверки публикации](../artifacts/dataset-publication-verification.json) |
| Голос | Синтез, STT, WebSocket, человеческий микрофон и телефон - разные доказательства | Отдельные отчёты AlemPlus/ElevenLabs, без заявления о состоявшемся SIP/Twilio звонке |

## Отдельные браузерные и голосовые проверки

Этот документ воспроизводит пять сценариев задания и 35 проверок их ограничений. Записи интерфейса, голосовые сессии и окончательный MP4 имеют собственные даты, исходники и отчёты в [чеклисте сдачи](submission-checklist-ru.md). Число проверок записи не подставляется из прежней версии ролика. Синтетический вход микрофона не подтверждает испытание физического микрофона человека или телефонный звонок.

## Как повторить

Из корня проекта: .venv/bin/python scripts/verify_brief_scenarios_ru.py. Скрипт заново создаёт JSON и этот документ из реальных результатов текущего каталога; имена и минуты не зашиты в ожидаемые ответы. Для PDF: bundled Python scripts/build_scenarios_pdf_ru.py. Проверять условия, а не буквальное совпадение фраз; не называть 35/35 процентом точности.

Дата формирования: {report['generated_at']}. SHA-256 каталога: {report['dataset_sha256']}. Это срез открытых источников, а не полный реестр физических мест Астаны.
"""
    (ROOT / "docs/test-scenarios-ru.md").write_text(text.replace(f"{report['dataset_count']:,}", f"{report['dataset_count']:,}".replace(",", " ")))


def main():
    # main has already loaded dotenv. Explicitly blank all credentials/selectors
    # now, before creating the application lifespan or any retriever/provider.
    for key in KEYS:
        os.environ[key] = ""
    os.environ.update(QALA_LLM_PROVIDER="local", QALA_RERANK_PROVIDER="none",
                      QALA_EMBEDDINGS="hash", QALA_WEATHER="off", QALA_EVENTS="off")
    dataset_path = ROOT / "data/pois.json"
    raw = dataset_path.read_bytes()
    dataset = json.loads(raw)
    by_id = {place["id"]: place for place in dataset["pois"]}
    records = []
    with tempfile.TemporaryDirectory(prefix="qala-brief-scenarios-") as temp:
        os.environ["QALA_MEMORY_PATH"] = str(Path(temp) / "preferences.sqlite3")
        with TestClient(app) as client:
            for case_id, values in CASES:
                payload = {**COMMON, **values}
                started = time.perf_counter()
                response = client.post("/api/chat", json=payload)
                if response.status_code != 200:
                    raise RuntimeError(f"{case_id}: expected HTTP 200, got {response.status_code}")
                result = response.json()
                if result["mode"] != "grounded-demo" or result["context"]["weather"]["status"] != "disabled" or result["context"]["events"]["status"] != "disabled":
                    raise RuntimeError("Offline provider isolation was not preserved")
                records.append({"id": case_id, "input": payload, "http_status": response.status_code,
                                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                                "result": result, "checks": check_result(case_id, payload, result, by_id)})
    checks = [passed for item in records for passed in item["checks"].values()]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "Real FastAPI/LangGraph, current frozen multi-source POI corpus, fixed simulated Russian inputs, all cloud credentials empty, weather/events disabled, local feature-hash retrieval and temporary memory; not a live venue-opening or human relevance study",
        "dataset_sha256": hashlib.sha256(raw).hexdigest(), "dataset_count": len(dataset["pois"]),
        "providers": {"paid_calls_allowed": False, "weather": "disabled", "events": "disabled", "embeddings": "local-feature-hash"},
        "passed": sum(checks), "total": len(checks), "scenarios": records,
    }
    assert report["total"] == 35, report["total"]
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_document(report)
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "dataset_count": report["dataset_count"], "passed": report["passed"], "total": report["total"],
                      "results": [{"id": item["id"], "places": [place["name"] for place in item["result"]["recommendations"]],
                                   "minutes": item["result"]["route"]["total_minutes"]} for item in records]}, ensure_ascii=False))
    if not all(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

