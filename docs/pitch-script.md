# Qala pitch script

Target duration: 6 minutes 10 seconds, including a 30-second product demonstration. Present at a calm conversational pace. The nine slide titles match the accompanying deck. The demonstration uses a simulated EXPO location and the local grounded mode unless live provider credentials have actually been configured.

## Slide 1: Qala — 0:00–0:25

Imagine arriving in Astana with a little time and no clear plan. Qala helps you choose a useful next hour. Tell it where you are, how much time you have and what matters to you. It returns a few nearby places with a reason, an estimated visit and a concrete thing to do there. The concept serves visitors and people who already live in the city.

## Slide 2: A decision with real constraints — 0:25–1:00

The difficult question is specific: I am near MEGA Silk Way, I have forty-five minutes, and I want a walk. A useful answer must respect location and time. A family needs different suggestions. Someone looking for a socket needs evidence of that socket. A passenger flying soon needs time to get back. The brief asks for recommendations that are relevant, contextual and honest. These constraints shape the product before we generate any prose.

## Slide 3: The working prototype — 1:00–2:10

Here is the prototype. I can choose a simulated landmark, so the demonstration does not ask for anyone's real location. I choose forty-five minutes and request a walk. The map and recommendation list share the same context. Each place has a short explanation, an estimated walk and visit, and an action. I can inspect the source and see what remains uncertain.

[Demonstrate the walk preset, inspect one recommendation, then switch to quiet coffee. Allow thirty seconds.]

The coffee case illustrates a useful limit. The corpus can identify a cafe, but it may have no evidence about sockets. Qala should say that clearly and suggest asking staff. The local planner works without model credentials. Optional provider features have separate setup and status.

## Slide 4: The RAG flow — 2:10–2:55

We collect public POI data through an automated pipeline and keep source identifiers and collection dates. LangGraph coordinates context understanding, hybrid retrieval, budget planning, grounded response and optional preference memory. LangChain provides the document and vector-store interfaces. Retrieval combines BM25, local lexical vectors, interest matching and proximity.

The planner then applies categories, indoor and accessibility constraints, schedule checks, and cumulative walking and visit time. An optional model selects evidence focus and an approved activity through a strict schema. The application renders localized explanations from verified fields and trusted activity templates. Provider-written prose never enters the response. A no-match result is valid when the available evidence cannot support the request.

## Slide 5: Evidence and uncertainty — 2:55–3:40

The National Museum gives a concrete example. Its official website says it closes on Mondays. A museum request on Monday must not produce a confident open-now answer. Regular schedules also do not guarantee tickets or rule out exceptional closures.

Qala separates three things: facts from POI sources, computed estimates such as walking time, and generated ideas such as taking a photograph. Map lines illustrate a sequence. They do not prove a pedestrian path. These distinctions make the answer easier to assess and reduce the chance that fluent language hides missing data.

## Slide 6: Existing products — 3:40–4:15

We researched existing products through Exa and official sources. Google Maps already offers conversational nearby discovery through Ask Maps. Wanderlog combines AI with itineraries and route optimization. Mindtrip markets preference memory. VoiceMap and izi.TRAVEL provide established audio experiences.

Our opportunity is a focused Astana companion with inspectable local evidence and explicit constraints. We should test that proposition with users instead of claiming that conversation or audio alone makes the product unique.

## Slide 7: Privacy and optional voice — 4:15–4:55

The default is a chosen landmark. Browser location follows an explicit action. Precise coordinates stay out of preference storage. Memory starts off and stores only selected preferences and coarse location when the user opts in. The session is pseudonymous, expires after thirty days and supports deletion.

ElevenLabs synthesis and voice sessions, plus an inbound phone integration, can use the same planner. Those live services need keys and provider setup. We distinguish implemented integration code from a call that has actually been tested. This prototype is not an emergency or navigation service.

## Slide 8: Pilot and business model — 4:55–5:40

The proposed first distribution channel is visitor-facing partners: hotels, museums, universities and city information. Visitors use the core experience free. We would test paid tooling that helps partners maintain verified details and publish walking collections.

That is a hypothesis, not revenue. Before setting prices, we need evidence that recommendations lead to usable visits and that partners value keeping their information current. We would measure constraint violations, stale records, useful first choices and provider cost per completed recommendation. Any future commercial referral must be disclosed and must not silently change relevance ranking.

## Slide 9: The next pilot — 5:40–6:10

The deliverable includes the local app, collected data, ingestion scripts, scenario tests, research, privacy notes and this presentation. The five cases in the brief are covered, with additional tests for languages, group context, accessibility, unknown hours and malicious instructions.

The next pilot should add verified local updates and pedestrian routing, then test usefulness with real visitors. Qala's promise is modest and practical: a few suggestions that fit the time you have, with enough evidence to decide whether to go.

## Краткое резюме по-русски

Qala помогает жителям и гостям Астаны выбрать занятие рядом с собой на ближайшие 30–120 минут. Пользователь указывает локацию, доступное время и предпочтения. В ответ получает до трёх конкретных мест с объяснением, примерным временем и действием.

Данные POI собираются автоматически. LangGraph управляет поиском, проверкой ограничений и формированием ответа. Источники, расчётные оценки и сгенерированные идеи обозначаются отдельно. Неизвестные часы работы, розетки и доступность остаются неизвестными. Например, Национальный музей нельзя предлагать как открытый в понедельник.

Основной сценарий работает локально без ключей облачных сервисов. ElevenLabs и телефонный канал требуют настройки провайдеров. Память включается пользователем, хранит предпочтения и приблизительную локацию, действует 30 дней и удаляется по запросу.

Бизнес-гипотеза: бесплатный помощник для посетителей и платные инструменты для партнёров, которые обновляют информацию и создают маршруты. Цены и спрос ещё предстоит проверить. Следующий этап — пилот с местными организациями, проверка данных и полноценная пешеходная маршрутизация.

