# User interface preferences

The user explicitly rejected decorative microcopy. Do not add branding taglines,
footer slogans, privacy reassurances, explanatory fine print, or floating status
captions merely to fill space. Keep controls direct. Put necessary factual details
and limitations inside the relevant source, route or settings interaction.

Specifically removed by request: “Astana, at your pace.”, “Source-backed places.
Your preferences, your choice.”, “Your location. Your control.”, the floating
“Today at … · Astana time” caption, and the preference-memory helper paragraphs.
Do not reintroduce these or equivalents.

The user also explicitly rejected proactive API-quota notices in the voice
interface. Do not add remaining-character balances, provider-limit captions,
technical health summaries or reassurance text to voice, map or settings merely
because an API was audited. Keep account diagnostics in submission/research
reports. An actual failed user action may show its concise actionable error.

# Presentation preferences

The user removed the photo/rating count block from the dataset slide, including
“34 фото — 22 места” and “1 оценка — без текста отзыва”. Do not replace it with
another photo count or limitation caption. Keep source-coverage details in the
documentation and source notes.

# Map accuracy

The latest explicit user instruction restores the original embedded 3D view
and asks for polish. Use the keyless MapLibre/OpenFreeMap map with footprint
extrusions as the default 3D view. The 3D control must operate inside the app;
never replace it with an external hyperlink or a provider-key prompt. Keep
routes, selection and GPS in the same map instance when switching modes.

These extrusions are a schematic representation of mapped footprints and
available height data, not verified landmark models or photogrammetry. The
earlier Bayterek and alem.ai cylinder feedback remains an accuracy constraint:
do not claim accurate architectural geometry or invent landmark patches. Put
necessary source limitations in the relevant source or map interaction rather
than adding floating fine print. Flat 2D must hide every depth layer and lock
pitch at zero, not merely lower the camera.

The failed municipal attempt and Yandex evaluation remain research history
in `artifacts/municipal-map-attempt.json` and `docs/research/`. Neither Yandex
nor 2GIS is required or selected by the current build. Do not restore 2GIS as
the application's fallback.
