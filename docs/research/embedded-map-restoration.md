# Embedded map restoration

The latest user instruction is to restore the first embedded 3D approach and
polish it. This supersedes the earlier selection of a keyed Yandex renderer.
The main 3D control must operate in the application, without opening another
site or requiring a provider key.

## Current architecture

CityMap lazily loads one MapLibre renderer using the OpenFreeMap Positron
cartographic style and OpenStreetMap-derived vector data. MapLibre's worker is
bundled with the application for production decoding. The map starts in 3D;
an explicit button switches between 3D and flat 2D. No browser map API key is
required in the environment, Docker build or Compose configuration. Network
access is still necessary for vector tiles and pedestrian routing.

Mode changes update the same map instance rather than remounting the renderer.
Route geometry, place selection, origin, GPS marker and the current geographic
context remain attached. The explicit mode is independent of camera pitch:
a user can manually look straight down while remaining in 3D mode.

Flat 2D hides all building extrusions and locks the allowed pitch at zero.
Returning to 3D restores depth inside the same canvas. Changing pitch alone
does not qualify as flat 2D. Camera actions cancel or retarget the preceding
movement. Keyboard actions and reduced-motion preferences require immediate
camera changes; pointer movements are brief. Route fitting uses absolute
padding to prevent insets from accumulating after place selection.

The shared application still owns recommendations, the selected place, the
current street route and optional GPS updates. Valhalla supplies pedestrian
geometry and instructions. Dashed estimated links remain distinct from a
confirmed street route. The map does not replace the planner's evidence or
alter the current itinerary when the display mode changes.

## Geographic limits

This is a schematic 3D map of mapped building footprints and available source
heights. It is not a photogrammetric municipal mesh, a detailed architectural
model or a proof of accurate landmark shape. In particular, a footprint
extrusion cannot reconstruct Bayterek's lattice or the alem.ai sphere. Do not
claim that restoring this renderer solves those geometry limitations or add
invented landmark patches to imply city-wide accuracy.

Keep attribution visible. Put necessary data qualifications inside a relevant
map or source interaction. The user explicitly rejected decorative floating
captions and explanatory fine print added to fill space.

## Verification scope

`scripts/verify_embedded_map.py` is the focused production-browser check. Its
output is `artifacts/embedded-map-verification.json`; only the observations in
a completed report count as verification. It checks real API responses,
OpenFreeMap tiles and Valhalla street geometry rather than mocked map or
recommendation responses. The checks include embedded 3D/2D pointer controls,
one-canvas continuity, exact route preservation, interrupted mode toggles,
keyboard marker selection, mobile controls and assistant switching.

GPS callbacks are synthetic and injected only after the explicit live-location
action. Programmatic rapid toggles exercise interruption handling separately
from actual pointer checks. Headless browser rendering does not establish
physical-device frame rates, architectural accuracy, source completeness or
a completed outdoor walk. Older keyed-provider checks do not validate this
restoration.

## Retained history and outstanding work

The actual municipal attempt remains in
`artifacts/municipal-map-attempt.json`. The central mesh failed; the sparse
northern local research control was not suitable for this app. The previous
Yandex implementation and provider coverage studies remain historical research
in `docs/research/`. Neither Yandex nor 2GIS is selected by the current build.
No borrowed provider key or unqualified municipal asset is needed for the
restored map.

The full original hackathon objective remains incomplete. Live ElevenLabs
narration/conversation, telephone verification, public deployment, a refreshed
demo and the required YouTube publication have separate outstanding access or
delivery requirements. Restoring the embedded map does not mark those items
complete.
