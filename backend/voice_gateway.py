"""Restricted local bridge for the provider's authenticated planner webhook.

Expose this listener through a tunnel instead of exposing the entire application.
Authentication remains at the main backend; no key is stored by this bridge.
"""
from __future__ import annotations

import json
import httpx
from fastapi import FastAPI, HTTPException, Request, Response

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MAX_BODY = 32_768


@app.post("/api/voice/tools/recommend")
async def planner_webhook(request: Request):
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(415, "JSON required")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise HTTPException(413, "Request too large")
    try:
        async with httpx.AsyncClient(timeout=65, follow_redirects=False) as client:
            upstream = await client.post(
                "http://127.0.0.1:8000/api/voice/tools/recommend", content=bytes(body),
                headers={"Content-Type": "application/json", "X-Qala-Tool-Secret": request.headers.get("x-qala-tool-secret", "")},
            )
    except httpx.HTTPError:
        raise HTTPException(502, "Planner temporarily unavailable") from None
    # Operational receipt only: no headers, location, text, capability or IP.
    print(json.dumps({"voice_webhook_status": upstream.status_code}), flush=True)
    return Response(upstream.content, status_code=upstream.status_code,
                    media_type="application/json", headers={"Cache-Control": "no-store"})
