# Qala product concept

Qala helps residents and visitors decide what to do nearby in Astana, using their available time and stated needs. A request produces one to three specific places, a short reason for each, an estimated walk and visit duration, and a concrete activity. A timed mini-route connects suitable stops.

## People and jobs

| Person | Immediate job | Useful outcome |
|---|---|---|
| Resident near MEGA Silk Way | Fill 30–60 minutes with a walk | A feasible nearby stop or short route |
| Person working remotely | Find quiet coffee and a socket | A cafe candidate with socket evidence or an explicit verification request |
| Family | Find a suitable nearby activity | Family tags, realistic visit time and no invented facilities |
| Visitor with a flight soon | Use spare time without missing the flight | A conservative local option or advice to stay near the airport |
| Evening explorer | Find a worthwhile activity late | Suitable public places and clear opening-hours uncertainty |

## Interaction

Choose a landmark or explicitly share location. Set time, interests, language and relevant constraints. Ask naturally or choose one of the five scenario presets. Inspect recommendations and the route on the map, read the evidence, and adjust the request. Save places locally if useful. Enable preference memory only deliberately. Speech and phone use the same planner when their providers are configured.

The interface shows the location and filters used. It explains uncertainty beside the relevant place. It does not imply that a generated illustration is a real map or that a line between points proves a walkable route.

## Product rules

1. Every suggested place must come from the collected POI dataset.
2. Hard constraints take priority over fluent output. No feasible option is an acceptable result.
3. The response separates source facts, estimates and generated activity ideas.
4. A missing socket, wheelchair, schedule or event field must not become a positive claim.
5. The planner accounts for estimated walking and visit time. Pre-flight requests require an explicit airport-transfer estimate. The planner asks for it when missing, then deducts that estimate and a 90-minute airport-formalities reserve.
6. Preference memory is optional and deletable. Precise location must not persist in preference storage.
7. The local recommendation flow works without cloud credentials. Live AI narration, ElevenLabs and telephony require configured providers.

## Business hypothesis

Begin with a free visitor experience distributed through hotels, museums, universities and city visitor information. Test a partner dashboard subscription for maintaining verified venue details and distributing branded walking collections. The paying customer would receive editorial tooling and data-quality reporting, while ranking continues to follow user constraints.

Potential revenue streams are partner subscriptions and clearly disclosed booking referrals after trust has been established. Prices, conversion rates and willingness to pay are unvalidated. No partner contracts, bookings or recurring revenue are claimed. Paid placement must never silently override relevance or safety.

A first pilot should test whether people choose a recommendation, whether the suggested stop was usable, and how often evidence was missing or outdated. Track cost per successful recommendation when optional providers are enabled. Keep analytics aggregated and exclude precise locations.

## Release scope

The hackathon deliverable is a reproducible local prototype, collected POI corpus, automated ingestion, documented graph, tests, presentation and recorded demo. It is not a production navigation service, a live availability guarantee, an emergency service or a booking agent. Production expansion needs authenticated partner editing, data refresh monitoring, a pedestrian routing provider, provider privacy review and real accessibility verification.

See `research/product-research.md`, `privacy-and-safety.md`, `test-scenarios.md` and `criteria-matrix.md` for evidence and acceptance conditions.

