# Frontend acceptance notes

- React + TypeScript + Vite. `npm run build` and `npm run typecheck` pass.
- Actual shadcn CLI registry sources installed: button, badge, dialog, sheet, select, switch, toggle-group, field, input-group, alert, skeleton, separator, empty, and their dependencies. Source uses local class merge utility and current Radix primitives.
- Main explorer uses a real backend recommendation request. No mock successful recommendation, map route or provider response.
- Initial viewport explicitly identifies its simulated EXPO starting point and planned visit time in Astana timezone. Changing time recomputes server-side hours checks. Night preset changes planned time to20:00.
- Five presets are available with stable demo testids. The airport scenario asks the user for a transfer estimate and sends that estimate to the backend; no guaranteed airport travel time is invented.
- Unknown opening times are labeled. Evidence separates POI facts from generated suggestions, displays collected date and trace, and includes the separate opening-hours source when provided.
- Map uses actual OpenStreetMap tiles with attribution and shows connection lines as estimated. Tile failure does not block recommendations. Google Maps navigation is an external, explicit action.
- Geolocation is requested only by clicking the location action. Exact location lives in React state, never localStorage.
- Bookmarks are stored in localStorage. Session memory is off by default. Opt-in preferences go through the backend, and the user can delete them.
- ElevenLabs voice dynamically loads the current React SDK with its required provider. Private signed session URLs remain server-side until needed. Microphone is requested only after the voice start action; missing credentials produce a specific unavailable response. Speech playback uses the ElevenLabs backend endpoint and never falls back silently to another voice.
- Self-hosted Manrope and DM Sans provide the visual typography. Generated artwork is identified as an illustration. Actual Commons photographs retain source and license credits.
- Reduced motion disables authored transitions; dialogs and sheets have accessible titles, keyboard behavior and focus handling.
- Impeccable mechanical detector ran once against the completed frontend and returned[]; parent owns one desktop/mobile screenshot pass and one confirmation pass.

## Known practical limits

External map tiles need network access. POI coverage is limited to the collected dataset. Routing connections are estimates unless the backend reports walking-network mode. Listed hours are source evidence, never live verification. Provider voice needs server credentials. Multi-language interface is implemented; dynamic place names preserve source spelling.

## Review fixes

Deliberate null airport-transfer estimates now reach the API. Empty responses display the backend clarification; all material missing-data notes are visible above the composer. Memory success is announced only after a confirmed server write, and memory deletion requires an OK response. Voice connection startup is guarded against close/unmount during signing or microphone permission, and all EN/RU/KK notices disclose audio, selected starting coordinates and current filters being sent to ElevenLabs.

Reload hydration reads the server memory record before the initial recommendation and restores the consent switch. The initial request uses remember:false so it does not create or renew preferences merely by loading the page. Failed hydration shows a recovery message and Retry repeats hydration. EN/RU/KK location and memory help now disclose the coarse area and30-day retention. Shared response parsing replaces empty/non-JSON gateway parser errors with a recovery message and preserves real server503 details. Focused Node regression proof passed for empty502, HTML502, preserved503detail and successfulJSON.
