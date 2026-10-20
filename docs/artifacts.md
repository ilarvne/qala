# Submission artifacts

The current application runs at [localhost:8000](http://localhost:8000/). The published corpus contains 6,505 records. The embedded map exposes all 6,504 ordinary places, with the closed historical record retained separately. Current counts and hashes come from the [dataset manifest](../data/dataset-manifest.json), [media inventory](../artifacts/media-inventory-final.json) and [production map checks](../artifacts/map-catalog-verification.json).

| Artifact | Purpose and evidence |
|---|---|
| [Russian presentation](../artifacts/presentation-ru.pptx) and [PDF](../artifacts/presentation-ru.pdf) | Twelve editable slides, real interface screenshots, generated cover and Phosphor icons. [Verification](../artifacts/presentation-ru-verification.json) records output hashes, all-slide review and source boundaries. |
| [Russian pitch script](pitch-script-ru.md) | Approximately six minutes, with sources and the seven judging criteria mapped to slides. |
| [Scenarios and limits PDF](../artifacts/scenarios-and-limits-ru.pdf) | Five brief scenarios, expected responses and operational boundaries. [Verification](../artifacts/scenarios-and-limits-ru-verification.json) records the four-page review. |
| [Russian scenario document](test-scenarios-ru.md) and [machine-readable results](../artifacts/brief-scenarios-ru.json) | The current five-case evaluation and its 35 constraint checks. |
| [Russian demo MP4](../artifacts/video/ru/qala-demo-ru.mp4) and [SRT](../artifacts/video/ru/qala-demo-ru.srt) | Real browser footage edited in Remotion. The [export report](../artifacts/video/ru/final-export-verification.json) is authoritative for the current render status and exact output hash. |
| [Narration generation receipt](../artifacts/video/ru/narration-generation-v4.json) | Seven Russian ElevenLabs v4 chapter takes. [Transcription checks](../artifacts/video/ru/narration-v4-transcription-verification.json) test intelligibility, not native-speaker pronunciation quality. |
| [Source and RAG documentation](research/conversational-rag-upgrade.md) | Retrieval, context, schema validation and provider boundaries. The [criteria matrix](criteria-matrix.md) links the brief to evidence. |
| [Privacy notes](privacy-and-safety.md) | Consent, editable preferences, rounded stored coordinates, expiry, deletion and external services. |
| [API audit](../artifacts/api-readiness-2026-10-20.json) | Actual service checks and their dates. [Current voice account receipt](../artifacts/voice-new-account-verification.json) confirms the private agent and 16 conversation presets separately. |
| [Submission archive](../artifacts/qala-submission.zip) and [verification](../artifacts/submission-archive-verification.json) | Code, data, documentation and deliverables. The archive report is generated after final packaging and records CRC, hashes, secret exclusion and offline replay. |

YouTube publication still requires a real uploaded URL. The [connection check](../artifacts/youtube-connection-check.json) records a browser bootstrap failure before account selection. A local MP4 or a GitHub repository does not replace that URL.

## Rebuild the Russian presentation

The generator uses the bundled Codex `@oai/artifact-tool` runtime and LibreOffice. It requires the current dataset, successful frozen-source server/scenario reports, verified voice configuration and the six real screenshots in [the screenshot manifest](../artifacts/presentation-assets/ru-screenshots.json).

```bash
node scripts/build_presentation_ru.mjs --check-inputs
node scripts/build_presentation_ru.mjs
```

Set `QALA_RUNTIME_DIR` if the bundled runtime is not at `~/.cache/codex-runtimes/codex-primary-runtime`. Each run retains a private `.presentation-build/` directory with source exports, slide previews and validation. Inspect all twelve rendered slides and all twelve PDF pages before setting visual review complete. A successful package check alone is insufficient.

The deck uses Inter. Text, the high-level RAG diagram and speaker notes remain editable. Interface evidence and venue photographs remain original raster images, with any crops recorded. The generated cover is a conceptual paper atlas, not a photograph or an accurate map.

## Rebuild the scenario document

```bash
.venv/bin/python scripts/verify_brief_scenarios_ru.py
~/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/build_scenarios_pdf_ru.py
```

The first command refreshes the five scenario outputs and Markdown. The second creates the four-page Russian PDF. Render and inspect every changed page.

## Evidence history

The earlier OSM-only 6,222-record build, the subsequent 6,502-record expansion and previous English/Russian presentation and video editions are historical. Dated research and retained reports in `artifacts/history/` preserve their scope. Their test counts, footage and provider checks do not become current evidence merely because a later document links to them. The current [submission checklist](submission-checklist-ru.md) distinguishes the final deliverables, provider configuration, synthetic microphone tests and the remaining YouTube step.
