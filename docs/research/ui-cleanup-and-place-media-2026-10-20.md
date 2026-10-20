# Place discovery cleanup, 20 October 2026

The review targets the existing Qala interface and the current challenge brief. The primary task is to choose a nearby place, understand its fit and start a walk. The retained visual direction is white, slate, cobalt and Geist, with Phosphor icons and the existing Assistant UI/OpenUI runtime.

## Evidence and decisions

Exa discovery and primary-source reading informed the implementation:

- [Nielsen Norman Group: progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/) supports keeping common tasks visible and making secondary detail available on demand. Cards now show the place, an available rating, walking/visit time and a direct map action. Source diagnostics, licensing context, collected descriptions and generated-suggestion provenance live inside the place's Sources disclosure. Required photo credits and provider attribution remain visible.
- [W3C: target size minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) defines a 24 CSS pixel minimum with spacing and other exceptions. Qala's mobile card actions, scenario controls, GPS/filter controls and navigation now use 44 pixel targets. This is a focused improvement, not a claim of full WCAG conformance or a physical-device usability study.
- [WAI-ARIA: modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) informed the existing shadcn dialog's retained focus handling. Opening a place from its title/photo and closing with Escape restores focus to the initiating control. The practical section omits empty fields, while missing hours remain explicit in the relevant place interaction.
- [shadcn Dialog](https://ui.shadcn.com/docs/components/radix/dialog) and [Button](https://ui.shadcn.com/docs/components/radix/button) documentation support reuse of the installed components. Native details/summary handles source disclosures. No second assistant runtime or parallel custom chat implementation was introduced.

The before/after inspection used the actual production UI at 1440×1000 and 390×844. It found redundant category/action lines, small source icons, empty photo boxes and low-value helper paragraphs. These were removed or replaced with direct controls. Desktop/mobile review also covered a real API-backed rating, place details, no horizontal overflow and focus return. The existing map renderer was not redesigned: 3D remains schematic footprint extrusion; 2D hides all depth layers and locks pitch in the same instance.

## Ratings and photographs

The existing owned-key 2GIS source lookup now supplies current displayed cards and Assistant UI/OpenUI responses, including comparisons. It is requested only after an explicit user action, for at most three current places. Same-view consumers reuse in-flight/displayed state. A new plan, language change, cancellation or unmount invalidates the old view. No result is written to browser storage, the POI corpus, a completed-response cache, the RAG index or preference memory. Provider counts remain separate from written review counts. Missing ratings are omitted rather than fabricated.

See [the API capability research](twogis-live-ratings-and-media-2026-10-20.md) for the distinction between rating aggregates, gallery links and actual licensed photo/review content. Official Places access does not provide every photograph or review body. The new open photograph expansion uses independently acquired Commons files, exact source identities, attributed licences, decoding checks and visual review. Preferred cover images improve Bayterek and Mega Silk Way without generating replacement venue photography. Publication evidence and final counts belong to the current dataset manifest and media audit.

The previous Nur Alem museum record remains historical and closed. Alem.ai is a separately sourced exterior landmark. A museum component inside the building has its own schedule; it does not establish whole-building visitor hours or make the former museum current. No old interior photo, review or rating is transferred to a new operator.

## Submission boundary

The edited Russian deck uses actual interface screenshots and current manifest/test-report values. The Remotion refresh uses continuous browser recordings and existing actual ElevenLabs narration. At the read-only account check, 9,888 of 10,000 synthesis characters were used and extension was unavailable; a new full narration cannot be generated from the remaining allowance. Reusing recorded narration does not constitute a new voice or pronunciation verification. Video and screenshot manifests distinguish fresh captures from any retained historical voice evidence.

The local package can be prepared and verified without publishing it. A required accessible YouTube URL, physical microphone/telephone testing and complete citywide photo/review coverage remain separate external requirements. No jury score or “200% complete” claim follows from these changes.
