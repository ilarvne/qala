# Russian narration refresh, 20 October 2026

The user supplied replacement ElevenLabs access and rejected the earlier pronunciation and screencast text. The replacement key is stored only in the private 0600 environment file. Account diagnostics are reports, never interface captions.

The refreshed script follows the seven actual recorded workflows, uses ordinary Russian and spoken-out numbers, and avoids library names. It distinguishes6,505 dataset records from6,504 ordinary map points; a separately closed historical museum is retained in exports. It does not imply sixteen completed language conversations.

Official documentation was reviewed through Exa and the primary API pages:

- [Eleven v4](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/eleven-v4): content-creation model, improved cross-language accent handling. Its supported voice settings differ from earlier models; do not pass unsupported speed/style/SSML controls.
- [Pronunciation guidance](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices): voice selection, clear text and pronunciation controls. Unicode stress marks are not a documented pronunciation guarantee.
- [Voice-library API](https://elevenlabs.io/docs/api-reference/voices/voice-library/get-shared): language/voice metadata is discovery evidence, not proof of synthesis entitlement.
- [Speech with timestamps](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps): use actual normalized character alignment for captions and edit timing.
- [Forced alignment](https://elevenlabs.io/docs/api-reference/forced-alignment/create): available when cleaned display text differs from spoken pronunciation substitutions.

Actual new-account GET/models includesEleven v4. The native Russian Nikolay voice could be added, but its bounded synthesis attempt returned HTTP 402; no retry, subscription change or upgrade followed. An accessible Sarah v4 audition succeeded. Its actual AlemPlus transcription matched the tested words, and decode/loudness checks passed. These are technical and word-recognition checks, not native-listener pronunciation certification. The actual MP3 audition was presented in the task for optional user steering before the complete narration.

The media-only generator and its request-hash receipts record the actual selected voice/model, text and timestamp alignment. Final audio/video duration, loudness, captions and source intervals must be read from the final export report. A cancelled previous render is not a verified current video. The current narration is newly synthesized using the replacement account; retained older takes are not the current audio.
