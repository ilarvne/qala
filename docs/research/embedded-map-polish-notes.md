# Embedded MapLibre restoration: verified implementation notes

The latest user instruction restores the original embedded, keyless MapLibre
view. It supersedes the earlier provider-only direction for this iteration.
The result is an OSM building-height visualization, not a photogrammetric city
model. Geometry limitations belong in the map's source/details interaction;
the map should not carry a decorative status caption.

## Verified source and API facts

Checked against the installed MapLibre GL JS 6.15.0 types, its current official
[3D building example](https://maplibre.org/maplibre-gl-js/docs/examples/display-buildings-in-3d/),
[light specification](https://maplibre.org/maplibre-style-spec/light/), and
[sky specification](https://maplibre.org/maplibre-style-spec/sky/). Live source
metadata and central-Astana source features were read in the browser.

- Positron's existing vector source is `openmaptiles`, pointing to
  `https://tiles.openfreemap.org/planet`. Reuse it rather than requesting a
  second identical source.
- Its existing flat building layer is `building`; its vector source layer is
  also `building`. The TileJSON declares `render_height` and
  `render_min_height` as numbers, `hide_3d` as a boolean and `colour` as a
  string. The source's maximum native zoom is 14; higher camera zoom normally
  overscales those tiles.
- Follow the official `hide_3d != true` filter. Fade building heights into view
  over a small zoom interval (the final mobile-tested range is 13.5–14.5) rather than popping full towers
  into a city-wide overview. Use actual supplied heights without arbitrary
  landmark-specific amplification.
- Clamp the base between zero and its height. A loaded central-Astana feature
  actually contained `render_height: 5` and `render_min_height: 18`; blindly
  trusting both violates the style's base ≤ height requirement.
- `setLight` is supported. A restrained starting point is
  `{ anchor: 'viewport', color: '#ffffff', intensity: 0.32,
  position: [1.5, 210, 45] }`. Viewport anchoring maintains legibility during
  rotation. Lighting shades roof and wall faces; the style does not offer
  independent roof and wall colors in a single ordinary extrusion layer.
- Use opacity 1 and `fill-extrusion-vertical-gradient: true`. Translucency can
  expose blended back faces and create visual clutter. It is not a substitute
  for light and carefully chosen color.
- `setSky` exists, but its fog color requires actual terrain. `setFog` is not
  a MapLibre API. Avoid a DEM dependency or fabricated terrain merely to add
  atmosphere to Astana's walking map.

## Restrained cartography and interaction

| Before | After | Why |
| --- | --- | --- |
| External 3D hyperlink | Stateful 2D/3D button on the same canvas | Keeps route, selection, camera and navigation inside the product |
| Extreme pitch and dense gray towers | Pitch around 48°, bounded at 60°, cool neutral buildings around `#d9e2ed` with taller forms around `#cad6e5` | Maintains a useful walking view and separates the cobalt route from the city |
| Buildings above labels | Insert depth below the first text symbol; add route after depth | Street names and route remain legible |
| Double Latin/native street names | One selected-language expression | Reduces clutter without suppressing useful street information |
| Flat camera with depth still present | Hide every depth layer and lock max pitch to 0 in 2D | Makes 2D genuinely flat |
| Long camera flights | Interruptible camera ease around 240 ms; zero movement for keyboard and reduced motion | Preserves continuity without delaying control |

Street feature properties were verified: `name:en`, `name:ru`, `name:kk`,
`name_en`, `name`, `name:latin`, `name:nonlatin`. English can use
`coalesce(name:en, name_en, name)`, Russian `coalesce(name:ru, name)`, and
Kazakh `coalesce(name:kk, name)`. Prefer native `name` over `name:latin` as a
last fallback: one Dostyq street segment's actual `name:latin` was Spanish
`Calle Dostyk`.

Keep the existing city/country-label zoom limit of 13, actual route geometry,
white route casing, selected numbered marker, DOM accessibility labels,
production worker URL, responsive control insets, retry cleanup and source
attribution. A view-mode change must not recreate the WebGL context or refit
the entire itinerary. Preserve selected-place focus through mode switching.

The first desktop/mobile batch exposed three material issues: selected-marker
clearance beside the right controls, attribution overlap, and zero-height
buildings at the fitted mobile zoom (14.71). The final adjustment increases
right padding, anchors attribution above the measured cards on the left and
uses a 13.5–14.5 height fade. Final verification and captures are recorded in
`artifacts/embedded-map-verification.json`. Headless browser observations do
not establish physical-device performance or architectural accuracy.
