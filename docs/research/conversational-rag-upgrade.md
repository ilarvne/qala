# Conversational RAG implementation, 19 October 2026

The hackathon brief prioritizes relevance, current location, time, explicit constraints, concrete actions, and honest uncertainty. It requires automated POI collection; ratings are optional when actually available. The expanded city inventory is a source snapshot, not a claim that every current venue is mapped or verified open.

## Research and decision

Exa reviewed 10 search results across two workstreams: conversation/context/memory architecture and retrieval/evaluation. Technical conclusions use primary LangChain documentation; two third-party retrieval tutorials were discarded.

| Source | Design consequence |
| --- | --- |
| [LangChain retrieval architecture](https://docs.langchain.com/oss/python/langchain/retrieval) | Keep a bounded retrieval/validation workflow for predictable keyless operation. Do not describe it as an unconstrained model-driven tool agent. |
| [LangGraph custom RAG](https://docs.langchain.com/oss/python/langgraph/agentic-rag) | Use actual graph nodes and conditional edges; perform final validation before the response and expose real node boundaries to the UI. |
| [Context engineering](https://docs.langchain.com/oss/python/langchain/context-engineering) | Pass current constraints in a typed structure; separate runtime facts, previous conversational intent and durable preferences. |
| [LangGraph memory](https://docs.langchain.com/oss/python/langgraph/add-memory) | Separate conversational state from cross-session preferences. Avoid durable full-state checkpoints containing exact coordinates. |
| [Official hybrid-search reference](https://reference.langchain.com/python/langchain-google-vertexai/vectorstores/_searcher/VectorSearchSearcher/hybrid_search) | Fuse lexical and vector ranks rather than treating their score scales as interchangeable. The application implements provider-independent rank fusion over its real local LangChain store. |
| [LangSmith RAG evaluation](https://docs.langchain.com/langsmith/evaluate-rag-tutorial) | Measure source retrieval separately from answer constraints and grounding; retain inspectable queries, labels and responses. |

## Implemented changes

The graph now runs context resolution, eligible hybrid retrieval, budgeted planning, independent final validation, grounded presentation and minimized preference memory. No external model is required. The optional configured LLM can select validated presentation enums; it cannot invent factual prose or override constraints. The optional neural embedding provider remains explicit; default feature hashes are lexical vectors.

Retrieval applies radius, categories, exclusions, public-access metadata, indoor and wheelchair constraints before vector top-k. This matters for the larger city-wide inventory: geographically irrelevant documents no longer occupy all vector candidates. Weighted reciprocal ranks, intent overlap, geography and mapped names select candidates. The response includes per-query rejection counts and per-place retrieval evidence. Private and explicitly non-recommendable records remain in the inventory but never become itinerary recommendations.

Client-held conversational state carries canonical interests and constraints, not raw chat or invented venue facts. Follow-ups preserve category intent, enforce shorter budgets, add indoor constraints, cap cumulative walking, exclude previous suggestions and reset context. Current explicit category requests replace previous category intent unless the user asks to add one. Negative categories are actual exclusions. A flight-transfer clarification preserves the original flight deadline. Unrecognized phrasing does not become a claimed venue fact; typed filters remain available.

Available photos, rating source records, amenities, contacts and accessibility metadata are copied from normalized POIs. Unknown values stay empty. Real node-completion events feed the Assistant UI progress; complete responses contain a safe OpenUI program built from validated IDs and allowlisted components. Comparative layouts refer to the stops of the grounded plan.

Preference inspection/deletion remain available. An explicit consent-only edit endpoint accepts allowlisted preference fields without requiring a plan. Generation checks protect both deletion and edits from older requests writing stale preferences. Request-level opt-in memory retains only canonical preferences and coarse location; the explicit edit endpoint adds no location. Raw chat and exact user coordinates are not persisted.

## Verification and limits

`scripts/evaluate_conversation.py` evaluates nine manually labelled entity queries in English, Russian and Kazakh, plus multi-turn hard-constraint cases and an ablation that removes only prior structured context from the same implementation. The report records complete inputs, source IDs, ranks and outputs. It is a focused offline regression set, not an exhaustive human relevance benchmark or a live-provider test.

The application still cannot guarantee current openings, quiet seating, working outlets, live events, safe nighttime access or step-free streets. The schedule parser abstains on unsupported syntax; visits must fit every occupied minute in supported schedules. Airport reserves are a conservative planning floor and require the traveller's transfer estimate. These factual limitations belong in source/route interactions, not decorative UI captions.

## Optional keyless neural component

The subsequent implementation adds the official FastEmbed-supported multilingual MiniLM model as a real local CPU embedding provider. [Supported models](https://qdrant.github.io/fastembed/examples/Supported_Models/) lists its 384 dimensions and Apache-2.0 license; [FastEmbed's implementation](https://github.com/qdrant/fastembed/blob/main/fastembed/text/text_embedding.py) documents `local_files_only` and `specific_model_path`. The runtime passes both options, while a separate explicit maintenance command downloads public model files and precomputes corpus vectors. Content/model fingerprints prevent silently stale document embeddings. Two CPU threads bound inference resource use; unavailable caches fall back visibly to portable lexical vectors.

`scripts/evaluate_local_embeddings.py` measures the actual cached provider against the hash-vector component on implicit phrases outside the alias ontology. Real corpus records provide category labels. It blocks network connections during loading/querying and separately verifies the complete hybrid pipeline. This isolates semantic matching from the geographic and safety constraints measured elsewhere. Scores should be read with the report's narrow diagnostic limitations.
