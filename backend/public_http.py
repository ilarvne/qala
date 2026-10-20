"""Bounded reads for fixed, public provider URLs; no caller-supplied origins."""
from __future__ import annotations

import asyncio
import httpx

USER_AGENT = "Qala-Astana/1.0 (educational city walking prototype; public metadata)"


async def public_get(url: str, *, params: dict | None = None, max_bytes: int = 2_000_000) -> bytes:
    async def read():
        async with httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2), follow_redirects=False,
                                     headers={"User-Agent": USER_AGENT}) as client:
            async with client.stream("GET", url, params=params) as response:
                response.raise_for_status()
                parts, size = [], 0
                async for part in response.aiter_bytes():
                    size += len(part)
                    if size > max_bytes:
                        raise ValueError("Public provider response exceeded the size limit")
                    parts.append(part)
                return b"".join(parts)
    return await asyncio.wait_for(read(), timeout=5)
