# Draft request for an Astana 3D evaluation dataset

Prepared for review; not sent to any organisation.

We are evaluating a detailed interactive 3D walking map of Astana. The municipal Geographic Information Center's public scene references photorealistic I3S meshes, including groups labelled 2020–2024. Its public scene service currently returns a backend error. We would like to establish an authorised, supported way to evaluate and, if appropriate, embed the data.

Please provide an evaluation sector covering both **Bayterek, 71.4304546° E / 51.1282882° N**, and **alem.ai / Nur Alem, approximately 71.41607° E / 51.08921° N**, including surrounding streets. A route corridor connecting the sites is sufficient for initial evaluation. For each supplied sector, please include:

- Actual capture and processing dates, coverage polygon and tile/sector index.
- Horizontal and vertical coordinate reference systems, height/geoid model and transformation information.
- Geometry format/version, texture formats and resolution, lower levels of detail, approximate delivery size and known holes or artefacts.
- Measured checkpoint accuracy and its method, separately from nominal image resolution.
- Whether a semantic building/entrance layer is available alongside the continuous mesh.
- A compatible bare-earth DTM or ground-height service for pedestrian-route placement, including its own vertical reference system. A roof-bearing DSM alone does not establish street height or traversability.

A supported I3S service, SLPK package or validated 3D Tiles delivery would be suitable. The intended display includes sourced place markers and an independent pedestrian-route overlay. It does not require access to restricted operational or personal data.

Please clarify the permitted domains/applications, public web display, commercial or hackathon use, attribution, caching, local conversion, derivative tiling, self-hosting, redistribution restrictions, update terms and any charges. Public portal item flags currently do not specify these reuse rights.

Before selecting a delivery, we need to inspect both landmarks' geometry, alignment and textures in a browser, verify that the model fits its ground surface and pedestrian routes, and test performance on a midrange mobile device. Please indicate the appropriate data owner/licensor and a technical contact for these questions.
