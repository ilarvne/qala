---
name: Qala
description: A precision architectural city atlas for an Astana walking companion.
colors:
  primary: "#3666f6"
  primary-hover: "#2857e8"
  accent-surface: "#edf2ff"
  active-surface: "#eef3ff"
  canvas: "#f6f7f9"
  surface: "#fff"
  ink: "#20232b"
  slate: "#666e7c"
  muted-surface: "#f3f4f7"
  border: "#e5e7ec"
  route-charcoal: "#242833"
  card-detail: "#59667b"
typography:
  display:
    fontFamily: '"Geist Variable", sans-serif'
    fontSize: "30px"
    fontWeight: 550
    lineHeight: 1.21
    letterSpacing: "-0.035em"
  title:
    fontFamily: '"Geist Variable", sans-serif'
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.02em"
  body:
    fontFamily: '"Geist Variable", sans-serif'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.7
  card-body:
    fontFamily: '"Geist Variable", sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  card-metadata:
    fontFamily: '"Geist Variable", sans-serif'
    fontSize: "12px"
    fontWeight: 400
  label:
    fontFamily: '"Geist Variable", sans-serif'
    fontSize: "12px"
    fontWeight: 550
rounded:
  small: "5px"
  chip: "7px"
  control: "8px"
  search: "10px"
  overlay: "12px"
  card: "13px"
  dialog: "14px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  pane: "22px"
  section: "24px"
  sheet: "28px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "0 18px"
    height: "43px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.slate}"
    rounded: "{rounded.search}"
  input-search:
    backgroundColor: "#fcfcfd"
    textColor: "{colors.ink}"
    rounded: "{rounded.search}"
    padding: "0 14px"
    height: "40px"
  nav-active:
    backgroundColor: "{colors.active-surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.search}"
    height: "43px"
    width: "42px"
  chip-scenario:
    backgroundColor: "{colors.surface}"
    textColor: "#566273"
    rounded: "{rounded.chip}"
    padding: "9px 11px"
  card-place:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "8px"
    height: "166px"
  composer:
    backgroundColor: "{colors.surface}"
    textColor: "#454e5f"
    rounded: "{rounded.card}"
  itinerary:
    backgroundColor: "{colors.route-charcoal}"
    textColor: "{colors.surface}"
    rounded: "{rounded.overlay}"
    padding: "12px 14px"
---

# Design System: Qala

## Overview

**Creative North Star: "The Precision City Atlas"**

Qala treats Astana as a grounded architectural city model. White instrument surfaces, charcoal text, cool slate map detail and a concentrated cobalt accent make the next useful action easy to find. Geist and Phosphor icons give the interface a clear, compact, contemporary character. This is the user's approved replacement of the earlier green and cream identity, using the grounded architectural city model / precision atlas direction (new-work seed index 5).

The map uses OpenFreeMap/OpenStreetMap geographic data in one embedded MapLibre renderer. The user's latest instruction restores the original keyless 3D approach, with clearer cartography and polished interaction. Building extrusions describe footprints and available source heights; they are not verified landmark models or photogrammetry. The 2D/3D button changes this map in place and never opens an external provider. Representative artwork remains illustrative, never geographic evidence.

**Key Characteristics:**

- White and cool neutral surfaces with a single cobalt action color.
- Embedded footprint 3D and genuinely flat 2D, with source limits kept honest.
- Compact Geist typography, precise spacing and Phosphor icon controls.
- A focused assistant paired with persistent route and place context.
- Brief, interruptible motion with immediate keyboard and reduced-motion states.

## Colors

The palette is cool, architectural and predominantly neutral; the frontmatter records the implemented values.

### Primary

- **Atlas Cobalt** (`primary`): primary actions, route geometry, numbered stops, selection, focus and the Qala compass.
- **Pressed Cobalt** (`primary-hover`): hover treatment for the main walking action.
- **Cobalt Wash** (`accent-surface` and `active-surface`): selected map controls, assistant identity and active navigation.

### Neutral

- **Studio White** (`surface`): assistant, header, navigation and map overlays.
- **Cool Canvas** (`canvas`): the application backing surface.
- **Charcoal Ink** (`ink`): main interface text.
- **Slate Text** (`slate`): secondary interface information.
- **Mist Surface** (`muted-surface`): quiet backgrounds and secondary controls.
- **Fine Divider** (`border`): separation without heavy framing.
- **Route Charcoal** (`route-charcoal`): the bottom itinerary surface.
- **Card Slate** (`card-detail`): practical place actions and walking/visit metadata, with stronger contrast against white cards.

**The Cobalt Signal Rule.** Use cobalt for action, selection and geographic meaning; keep large interface surfaces neutral.

Provider cartography and landmark materials retain their geographic appearance; they do not introduce additional interface action colors.

## Typography

**Display and body font:** self-hosted Geist Variable, with a sans-serif fallback. The interface uses one family for a consistent instrument-like rhythm. Large welcome copy has tight tracking; compact body copy uses generous leading. There is no decorative display face or separate mono identity.

### Hierarchy

- **Display:** the assistant welcome heading uses the frontmatter display role. It becomes slightly smaller in narrower desktop and short-height layouts.
- **Title:** desktop and mobile place-card names use the 16px title role. Assistant stop names use the same readable size.
- **Body:** explanatory assistant text uses the body role, with slightly more leading in message and stop descriptions.
- **Card body and metadata:** walking/visit metadata uses 12px text and ratings use 13px. Direct actions remain readable on mobile with 44px touch targets. Category boilerplate and duplicate action descriptions do not belong in compact cards.
- **Label:** panel headings and plan labels use the label role. Secondary route metadata, sources and map labels step down to compact sizes according to their component.
- **Wordmark:** a tightly tracked lowercase Qala wordmark, with stronger weight than the welcome heading.

**The Direct Copy Rule.** Keep controls direct. Do not fill space with taglines, slogan footers, privacy reassurances, explanatory fine print or floating decorative captions. Put necessary factual details and limitations inside the relevant source, route or settings interaction. This is an explicit user preference recorded in `AGENTS.md`.

## Layout

The desktop workspace fills the viewport below a slim header (68px). A narrow navigation rail (64px), assistant pane (358px) and flexible map divide the width. The map occupies the remaining canvas; place cards and the charcoal itinerary float at its lower edge. Context and scenario controls sit above the geographic content. The assistant scrolls independently and pins its composer near the bottom.

Spacing uses small increments for controls and larger, consistent pane insets. The assistant has 22px content insets; sheets use 28px desktop padding. Avoid converting the spatial workspace into a marketing page or a metric dashboard.

At widths up to 1270px, the assistant narrows to 330px. Between 761px and 1000px it narrows to 300px and the rail to 52px. At widths of at least 1600px, the pane expands to 390px. At 760px and below, a 60px header and 63px bottom navigation replace the desktop framing. Map and assistant become alternate views; the cards remain horizontally scrollable over the map. Detail sheets occupy the full mobile width. Map attribution stays visible above the lower overlays.

The current Explore composition is recorded in `.impeccable/surfaces/explore.md`; it is a surface expression of this world, not a requirement that every future screen use the same composition.

## Elevation & Depth

Default 3D obtains depth from mapped building footprints and available source heights. It is a schematic geographic view, with no claim of detailed landmark accuracy. Flat mode hides every extrusion, sets pitch to zero and locks pitch gestures; lowering the camera alone is insufficient. Returning to 3D restores depth within the same renderer. White overlays remain legible; assistant and shell stay restrained.

### Shadow Vocabulary

- **Context overlay:** `0 4px 18px #1c294617`, used below the map context bar.
- **Place card:** `0 5px 18px #24304a17`, separating the white card from cartography.
- **Itinerary:** `0 8px 20px #1d263521`, supporting the dark route action surface.
- **Map controls:** `0 3px 16px rgb(25 43 75 / 8%), 0 1px 2px rgb(25 43 75 / 3%)`, used for the stacked geographic controls.

**The Geographic Depth Rule.** Keep the user's restored 3D view embedded and keyless. Never present footprint extrusions or hand-made landmark patches as an accurate architectural city model, and hide every depth layer in flat 2D.

Camera changes are interruptible: cancel or retarget the previous movement before a new one. Pointer camera changes take 240ms; reduced-motion and keyboard camera actions are immediate. Switching to 2D hides depth and locks pitch immediately so interrupted transitions cannot leave 3D geometry visible. MapLibre uses absolute route-fit padding to prevent accumulated insets. Insets reserve the card area so controls and attribution remain visible. Interface feedback stays within 120–180ms; avoid text reveals and long flights.

## Shapes

Controls have compact, gently rounded corners. Search and navigation use the search radius; place cards and the composer use the card radius; context and route surfaces use the overlay radius. The radius vocabulary in the frontmatter is normative. Circular shapes are reserved for stop numbers, origin/GPS markers and small icon controls. Fine one-pixel borders distinguish adjacent white surfaces. Place imagery is clipped inside a smaller inset corner.

## Components

### Buttons

The main walking action is a compact cobalt rectangle with white text, a clear hover color and a visible focus outline. Secondary actions use neutral or transparent surfaces. Icon controls have accessible names. Press feedback scales briefly; hover emphasis is scoped to fine-pointer devices where authored. Disabled controls retain readable state rather than implying availability.

### Inputs / Fields

The top search is a lightly bordered field with a search icon and a compact keyboard shortcut hint. Focus changes the border and restores a white surface. Search results use a white, shadowed list with explicit hover and keyboard selection states. The assistant composer is a bordered white container with a soft cobalt focus treatment, a multiline field and a separate send/cancel control.

### Navigation

The desktop rail uses Phosphor icons, cobalt on a pale blue surface for the active destination, and slate for inactive controls. The mobile bottom navigation adds visible short labels and preserves map/assistant switching. Settings, saved places and itinerary open focused side sheets.

### Chips

Scenario chips are small white rounded rectangles with quiet labels and icons. They form a horizontally scrollable row over the map. Hover adds a pale cobalt treatment; the chips trigger concrete planning scenarios rather than act as decorative categories.

### Cards / Containers

Place cards show a real available image, a numbered stop, legible title, save control, sourced rating when available, walking/visit times and a direct map action. Cards are 166px tall on desktop and 174px on mobile. Omit the photo region when no real photo exists. The title or photo opens practical place details; Sources holds secondary provenance and uncertainty. The selected card receives a cobalt outline. Generated imagery is illustrative and must not replace venue photography.

### Assistant

Assistant UI owns the conversational thread, composer, send/cancel, errors, retry and jump-to-latest behavior. Recommendations use a compact numbered stop list with linked sources and a collapsible evidence area. Selecting a stop connects the conversation to the matching map marker and card. Returned street-route totals and per-leg walking times update the matching current recommendation, including its walking-time explanation; earlier or different conversation results keep their original data. The assistant pane has no decorative header, slogan footer or privacy strip. Show real planning status and provider failures without adding reassurance or filler captions.

### Map and Itinerary

CityMap lazily loads one MapLibre/OpenFreeMap renderer with 3D as the initial mode. No map API key is needed. The mode button updates the embedded scene and keeps the same canvas, exact pedestrian geometry, numbered stops, selection and opt-in GPS. In 2D every extrusion is hidden and pitch is locked at zero; returning to 3D restores building depth. Explicit mode state is independent of a user manually pitching the 3D camera toward zero. Cleanup releases maps/listeners; route and recommendation state remain in their shared application owner. A tile failure exposes recovery without silently changing the user's plan.

Dashed estimated stop links become a solid street route only when pedestrian routing returns geometry. The bottom charcoal itinerary exposes stop count, time, distance and the walking action. Its walking total sums the rounded-up route legs, then adds visits and a five-minute buffer, matching the current assistant result and place-card timings. Directions, GPX export, opt-in GPS and route caveats remain practical and clearly distinct from the concept artwork. The current map decision and verification scope are in `docs/research/embedded-map-restoration.md`; earlier provider qualification is retained as research history.

## Do's and Don'ts

### Do:

- **Do** keep white, charcoal and cool slate dominant, with cobalt signaling action and selection.
- **Do** use Geist and Phosphor consistently with compact, legible component hierarchy.
- **Do** preserve geographic attribution, route quality labels and explicit uncertainty.
- **Do** use interruptible camera motion and immediate keyboard and reduced-motion states.
- **Do** label generated artwork and use real geographic data for the map.
- **Do** request location and microphone access only after the user's explicit action.
- **Do** keep controls direct and place necessary factual details inside the relevant source, route or settings interaction.
- **Do** keep the 3D view embedded, preserve the map instance when toggling and keep every depth layer hidden in flat 2D.

### Don't:

- **Don't** restore the rejected green, cream and chartreuse identity.
- **Don't** present the conceptual photographic map as the implemented map or claim photogrammetry.
- **Don't** make estimated links look like verified pedestrian paths.
- **Don't** claim generated venue artwork or unverified hours as evidence.
- **Don't** claim live voice availability without configured and verified providers.
- **Don't** add long camera flights, text reveal animations or decorative dashboard metrics.
- **Don't** add decorative taglines, slogan footers, privacy reassurances, explanatory fine print or floating decorative captions.
- **Don't** present generic footprint extrusions or hand-made landmark patches as an accurate 3D city model.
- **Don't** turn the main 3D button into a provider hyperlink, require a browser map key or restore 2GIS as the fallback.

## Assistant upgrade surfaces

Preserve the precision-atlas world. The assistant starts with direct task controls, without a slogan or decorative city artwork. Native Assistant UI owns editing, branching, cancellation and scrolling. OpenUI renders only the registered trusted city vocabulary: itinerary, comparison, constraints, clarification and follow-ups. One surface owns follow-ups; do not duplicate them below tool output. Real licensed venue photos replace generated venue imagery, with credits/gallery controls in source inspection. A missing photo produces a compact text itinerary entry rather than a large empty image panel. Conversation entry uses brief opacity/translate motion; keyboard and reduced-motion paths are immediate. Mobile composer input is16px and controls44px. Keep the embedded map and geographic constraints unchanged.
