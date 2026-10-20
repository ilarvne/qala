#!/usr/bin/env python3
"""Exercise the configured private ElevenLabs socket using a synthetic text turn.

Receives actual generated audio; does not claim microphone or telephone testing.
Secrets and signed URLs are never printed or persisted.
"""
from __future__ import annotations

import asyncio
import base64
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]


async def main():
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "method": "Real private ElevenLabs WebSocket, synthetic typed user turn, actual streamed audio and restricted authenticated planner webhook", "microphone_verified": False, "telephone_verified": False}
    counts = Counter()
    responses, audio = [], bytearray()
    receipt_log = Path('/tmp/qala-voice-gateway.log')
    before = receipt_log.read_text().count('"voice_webhook_status": 200') if receipt_log.exists() else 0
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post('http://127.0.0.1:8000/api/voice/session', json={"language": "en"})
            report['session_status'] = response.status_code
            response.raise_for_status()
            signed = response.json()['signed_url']
        async with websockets.connect(signed, open_timeout=20, max_size=8_000_000) as socket:
            await socket.send(json.dumps({"type": "conversation_initiation_client_data", "dynamic_variables": {"language": "en", "context": "Synthetic integration test. No personal information."}, "conversation_config_override": {"agent": {"language": "en"}}}))
            sent = False
            started = time.monotonic()
            last_audio = started
            async with asyncio.timeout(80):
                while True:
                    try:
                        data = json.loads(await asyncio.wait_for(socket.recv(), timeout=2))
                    except TimeoutError:
                        if len(responses) >= 2 and time.monotonic() - last_audio > 1.5:
                            break
                        continue
                    kind = data.get('type', 'unknown')
                    counts[kind] += 1
                    if kind == 'ping':
                        await socket.send(json.dumps({"type": "pong", "event_id": data['ping_event']['event_id']}))
                    elif kind == 'conversation_initiation_metadata':
                        metadata = data['conversation_initiation_metadata_event']
                        report['audio_format'] = metadata.get('agent_output_audio_format')
                    elif kind == 'audio':
                        audio.extend(base64.b64decode(data['audio_event']['audio_base_64']))
                        last_audio = time.monotonic()
                    elif kind == 'agent_response':
                        responses.append(data['agent_response_event']['agent_response'])
                        if not sent:
                            await socket.send(json.dumps({"type": "user_message", "text": "I am starting at Bayterek, Astana. I have 60 minutes, alone, group size one. I want architecture and coffee, with no indoor requirement and no wheelchair access requirement. Start on 2026-10-20 at 14:00 with UTC offset plus05:00. Please use the city walking planner now and give its sourced recommendations."}))
                            sent = True
                    if kind == 'error':
                        report['provider_error_received'] = True
                        break
                    if kind == 'agent_response_complete' and len(responses) >= 2 and len(audio) > 1000:
                        break
                    if len(responses) >= 2 and time.monotonic() - last_audio > 2:
                        break
            report['elapsed_seconds'] = round(time.monotonic() - started, 2)
    except Exception as error:
        if isinstance(error, TimeoutError) and len(responses) >= 2 and len(audio) > 1000 and counts['agent_tool_response']:
            report['bounded_receive_deadline_reached'] = True
        else:
            report['error_type'] = type(error).__name__
    after = receipt_log.read_text().count('"voice_webhook_status": 200') if receipt_log.exists() else before
    report.update({"events": dict(counts), "response_count": len(responses), "responses": responses, "streamed_audio_bytes": len(audio), "authenticated_webhook_receipts_during_session": max(0, after - before)})
    report['private_conversation_verified'] = counts['conversation_initiation_metadata'] > 0 and len(responses) >= 2 and len(audio) > 1000
    report['provider_webhook_execution_verified'] = counts['agent_tool_response'] > 0 and after > before
    if audio and report.get('audio_format') in {'ulaw_8000', 'pcm_16000', 'pcm_24000'}:
        directory = ROOT / 'artifacts/audio'; directory.mkdir(exist_ok=True)
        name = 'qala-live-agent.' + ('ulaw' if report['audio_format'] == 'ulaw_8000' else 'pcm')
        (directory / name).write_bytes(audio)
        report['captured_audio'] = str((directory / name).relative_to(ROOT))
    path = ROOT / 'artifacts/live-voice-verification.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'responses'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
