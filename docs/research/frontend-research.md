# Frontend implementation research

Research date: 19 October 2026. Exa search and page retrieval were used alongside installed package inspection and shadcn CLI documentation.

## Voice architecture

The [official ElevenLabs React SDK documentation](https://elevenlabs.io/docs/eleven-agents/libraries/react) specifies `useConversation`, `startSession`, message/status callbacks, and private credentials acquired server-side. Private agents accept a signed URL for WebSocket; WebRTC uses a conversation token. A `ConversationProvider` is required by current SDK architecture. Microphone access is requested on the user's voice action; keys never enter the frontend bundle. Text input remains available when voice credentials are missing. Do not represent browser speech synthesis as ElevenLabs.

## Maps

The [Leaflet official quick start](https://leafletjs.com/examples/quick-start/) provides markers, polylines, popups and explicit map sizing. Place coordinates and route geometry come from the backend. Leaflet can show the same route regardless of map provider. A connection line does not claim safe street routing.

The [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/) requires visible attribution and the HTTPS tile endpoint. It disallows bulk tile downloads and prefetch. Qala uses normal browser caching, no offline tile scraper, and a clearly recoverable map unavailable state.

## UI primitives and privacy

[shadcn UI](https://ui.shadcn.com/docs) source components installed through the actual CLI provide accessible Radix dialogs, sheets, selects, toggles and switches. Their keyboard behavior and focus handling are retained. Exact geolocation is kept in current React state; only explicitly saved places and opt-in preference state enter local storage. Consent to location is independent from memory consent.

## Image provenance

Generated city art is explicitly illustrative. Actual landmark photos, when used, are kept with original Wikimedia file links and license metadata in the source details. No stock photo is presented as a verified photograph of a cafe or indoor facility.
