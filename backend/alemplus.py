"""Documented AlemPlus adapters with bounded requests and sanitized status.

No credentials, transcripts, raw provider errors or user locations enter logs.
The runtime keeps the existing local document vectors; reranking sees public POI
text and canonical interests only. Cloud embedding is explicitly probed, not
silently used to build another city-wide index.
"""
from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import io
import math
import os
import time
from typing import Any
import wave

import httpx

BASE_URL = "https://llm.alem.ai/v1"
_status: dict[str, dict] = {}
_BROWSER_AUDIO_FORMATS = {"audio/webm": "matroska", "audio/ogg": "ogg", "audio/mp4": "mov"}
_MAX_PCM_BYTES = 61 * 16000 * 2


class ProviderUnavailable(RuntimeError):
    pass


def record_status(service: str, verified: bool, *, status: int | None = None, model: str | None = None):
    _status[service] = {"live_verified": verified, "last_status": status, "model": model,
                        "checked_at": datetime.now(timezone.utc).isoformat()}


def provider_observation(service: str) -> dict:
    """A copy of this process's observations, never provider credentials."""
    return dict(_status.get(service, {"live_verified": False}))


def chat_configuration() -> dict[str, Any] | None:
    selected = os.getenv("QALA_LLM_PROVIDER", "alemplus" if os.getenv("ALEMPLUS_API_KEY") else "openai").casefold()
    if selected in {"alem", "alemplus"} and os.getenv("ALEMPLUS_API_KEY"):
        return {"provider": "AlemPlus", "model": os.getenv("ALEMPLUS_MODEL", "alemllm"),
                "api_key": os.environ["ALEMPLUS_API_KEY"], "base_url": BASE_URL}
    if selected == "openai" and os.getenv("OPENAI_API_KEY"):
        return {"provider": "OpenAI", "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), "api_key": os.environ["OPENAI_API_KEY"]}
    return None


def integration_status() -> dict:
    chat = chat_configuration()
    return {"llm": {"configured": bool(chat), "provider": chat["provider"] if chat else None, "model": chat["model"] if chat else None,
                    **_status.get("llm", {"live_verified": False})},
            "alemplus_rerank": {"configured": bool(os.getenv("ALEMPLUS_RERANK_KEY")) and os.getenv("QALA_RERANK_PROVIDER", "alemplus").casefold() in {"alem", "alemplus"}, "provider": "AlemPlus", "model": "reranker", **_status.get("rerank", {"live_verified": False})},
            "alemplus_embeddings": {"configured": bool(os.getenv("ALEMPLUS_EMBED_KEY")), "provider": "AlemPlus", "model": "text-1024", "active_index": False,
                                     **_status.get("embeddings", {"live_verified": False})},
            "alemplus_stt": {"configured": bool(os.getenv("ALEMPLUS_STT_KEY")), "provider": "AlemPlus", "model": "speech-to-text", **_status.get("stt", {"live_verified": False})},
            "alemplus_stt_kk": {"configured": bool(os.getenv("ALEMPLUS_STT_KK_KEY")), "provider": "AlemPlus", "model": "speech-to-text-kk", **_status.get("stt_kk", {"live_verified": False})}}


async def rerank_candidates(candidates: list[dict], interests: list[str]) -> tuple[list[dict], dict]:
    key = os.getenv("ALEMPLUS_RERANK_KEY")
    if os.getenv("QALA_RERANK_PROVIDER", "alemplus").casefold() not in {"alem", "alemplus"} or not key or not candidates or not interests:
        return candidates, {"provider": "local", "applied": False}
    subset = candidates[:16]
    # Neither raw request text, exact user coordinates nor session capabilities
    # are disclosed to this provider.
    query = "Astana places matching these interests: " + ", ".join(interests[:15])
    documents = [" ".join([poi["name"], poi["category"], poi.get("poi_type", ""), poi["description"], " ".join(poi.get("tags", []))])[:900] for poi in subset]
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=4), follow_redirects=False) as client:
            response = await client.post(BASE_URL + "/rerank", headers={"Authorization": "Bearer " + key},
                                         json={"model": "reranker", "query": query, "documents": documents, "top_n": len(documents)})
        if response.status_code != 200:
            record_status("rerank", False, status=response.status_code, model="reranker")
            raise ProviderUnavailable("Reranking provider unavailable")
        results = response.json().get("results")
        if not isinstance(results, list) or len(results) != len(subset):
            raise ValueError("Incomplete rerank response")
        seen, ranked = set(), []
        for rank, result in enumerate(results, 1):
            index, score = result.get("index"), result.get("relevance_score")
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(subset) or index in seen or not isinstance(score, (int, float)) or not math.isfinite(score):
                raise ValueError("Invalid rerank identity or score")
            seen.add(index)
            poi = subset[index]
            ranked.append({**poi, "retrieval_score": round(.65 * poi["retrieval_score"] + .35 * 61 / (60 + rank), 4),
                           "retrieval_evidence": {**poi.get("retrieval_evidence", {}), "reranker": "AlemPlus/reranker", "rerank_score": round(float(score), 5), "rerank_position": rank}})
        record_status("rerank", True, status=200, model="reranker")
        return sorted(ranked + candidates[len(subset):], key=lambda poi: (-poi["retrieval_score"], poi["distance_m"], poi["id"])), {
            "provider": "AlemPlus", "model": "reranker", "applied": True, "documents": len(subset), "elapsed_ms": round((time.perf_counter() - start) * 1000),
            "disclosed": "canonical interests and public POI text only"}
    except Exception:
        if _status.get("rerank", {}).get("live_verified") is not False:
            record_status("rerank", False, model="reranker")
        return candidates, {"provider": "AlemPlus", "applied": False, "fallback": "local ranking retained"}


async def normalize_browser_audio(audio: bytes, content_type: str) -> bytes:
    """Decode supported browser containers into bounded mono WAV, in memory.

    Pipe-only protocols and a fixed demuxer prevent uploaded container metadata
    from opening external files or URLs. The process is always reaped, including
    request cancellation. No filenames, stderr or source audio are logged.
    """
    process = None
    try:
        demuxer = _BROWSER_AUDIO_FORMATS[content_type]
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-protocol_whitelist", "pipe", "-threads", "1", "-f", demuxer,
            "-i", "pipe:0", "-map", "0:a:0", "-vn", "-t", "61",
            "-map_metadata", "-1", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", "-threads", "1", "-f", "s16le", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        pcm, _ = await asyncio.wait_for(process.communicate(audio), timeout=10)
        if process.returncode or not pcm or len(pcm) > _MAX_PCM_BYTES or len(pcm) % 2:
            raise ValueError("Invalid decoded audio")
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm)
        return output.getvalue()
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ProviderUnavailable("Audio could not be processed. Please use text.") from None
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()


async def transcribe_audio(audio: bytes, filename: str, content_type: str, language: str) -> dict:
    service = "stt_kk" if language == "kk" else "stt"
    model = "speech-to-text-kk" if language == "kk" else "speech-to-text"
    key = os.getenv("ALEMPLUS_STT_KK_KEY" if language == "kk" else "ALEMPLUS_STT_KEY")
    if not key:
        raise ProviderUnavailable("Speech recognition is not configured")
    content_type = content_type.split(";", 1)[0].strip().casefold()
    if content_type in _BROWSER_AUDIO_FORMATS:
        try:
            audio = await normalize_browser_audio(audio, content_type)
            filename, content_type = "dictation.wav", "audio/wav"
        except ProviderUnavailable:
            record_status(service, False, model=model)
            raise
    data = {"model": model}
    if language != "kk":
        data["language"] = language
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=5), follow_redirects=False) as client:
            response = await client.post(BASE_URL + "/audio/transcriptions", headers={"Authorization": "Bearer " + key},
                                         data=data, files={"file": (filename, audio, content_type)})
        if response.status_code != 200:
            record_status(service, False, status=response.status_code, model=model)
            raise ProviderUnavailable("Speech recognition is unavailable. Please use text.")
        text = response.json().get("text")
        if not isinstance(text, str) or len(text) > 6000:
            raise ValueError("Invalid transcription response")
        record_status(service, True, status=200, model=model)
        return {"text": text.strip()[:3000], "language": language, "provider": "AlemPlus", "model": model}
    except ProviderUnavailable:
        raise
    except Exception:
        record_status(service, False, model=model)
        raise ProviderUnavailable("Speech recognition is unavailable. Please use text.") from None
