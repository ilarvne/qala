"""LangChain vector + BM25 + geographic and intent retrieval.

The offline embedding is an explicit feature-hashed lexical vector, expanded by
a multilingual city-interest ontology. It is not sold as a neural semantic model.
Replace Embeddings with a trusted local/pretrained provider for larger corpora.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import re

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from rank_bm25 import BM25Okapi

from .localembeddings import CachedFastEmbedEmbeddings, poi_document_text

ALIASES = {
    "coffee": ("coffee", "cafe", "café", "кофе", "кафе", "кофей", "кофе", "кофе"),
    "nature": ("nature", "park", "parks", "garden", "green", "парк", "сквер", "природ", "саябақ", "табиғат", "бақ"),
    "culture": ("culture", "art", "architecture", "landmark", "photo", "photography", "history", "культур", "искусств", "архитектур", "мәдени", "сәулет", "тарих", "сурет"),
    "museum": ("museum", "exhibition", "interactive", "музей", "музе", "выставк", "интерактив", "мұражай", "көрме"),
    "family": ("family", "child", "children", "kids", "playground", "ребен", "ребён", "дет", "площадк", "семь", "балам", "бала", "отбас"),
    "shopping": ("shop", "shopping", "mall", "торгов", "магаз", "сауда"),
    "walk": ("walk", "walking", "stroll", "strolling", "scenic", "promenade", "прогул", "серуен"),
    "quiet": ("quiet", "calm", "тих", "спокой", "тыныш"),
    "night": ("night", "nightlife", "late", "ноч", "позд", "түн"),
    "indoor": ("indoor", "indoors", "inside", "внутри", "помещен", "жабық", "ішінде"),
    "accessible": ("wheelchair", "accessible", "step-free", "коляск", "доступн", "арбамен", "кедергісіз"),
    "dining": ("dining", "restaurant", "restaurants", "lunch", "dinner", "food", "eat", "ресторан", "поесть", "обед", "ужин", "тамақ", "мейрамхана"),
    "sport": ("sport", "sports", "fitness", "workout", "exercise", "спортив", "спорт", "жаттығу"),
    "nightlife": ("bar", "bars", "pub", "pubs", "nightclub", "бар", "паб", "клуб", "түнгі клуб"),
    "cinema": ("cinema", "cinemas", "movie", "movies", "film", "films", "кино", "фильм"),
    "library": ("library", "libraries", "reading", "read a book", "библиотек", "кітапхана"),
    "theatre": ("theatre", "theater", "theatres", "theaters", "performance", "театр", "спектакл", "қойылым"),
    "events": ("event", "events", "what's on", "concert", "concerts", "афиша", "афиш", "событи", "мероприят", "концерт", "іс-шара"),
}

INTEREST_CATEGORIES = {
    "coffee": {"cafe"}, "museum": {"museum"}, "nature": {"park"}, "shopping": {"shopping"},
    "family": {"park", "playground", "museum"}, "culture": {"culture", "museum", "viewpoint"},
    "walk": {"park", "culture", "viewpoint"}, "dining": {"dining"}, "sport": {"sport"}, "nightlife": {"nightlife"},
    "cinema": {"culture"}, "library": {"culture"}, "theatre": {"culture"},
}

FINE_TYPES = {"cinema", "library", "theatre"}
WALK_TYPES = {"attraction", "monument", "memorial", "artwork", "fountain", "archaeological_site", "place_of_worship"}


def interest_mentions(text: str) -> tuple[list[str], list[str]]:
    """Separate explicit negative categories from positive intent.

    Deliberately bounded negation rather than asking an LLM to reinterpret hard
    constraints. Unknown phrasing is left unclaimed; callers can send filters.
    """
    positive, negative = [], []
    normalized = text.casefold()
    for key, aliases in ALIASES.items():
        for alias in aliases:
            # Cyrillic/Kazakh aliases are stems, so allow inflection at the
            # end while still requiring a word start: транспорт is not спорт.
            pattern = r"(?<!\w)" + re.escape(alias) + r"s?(?!\w)" if alias.isascii() else r"(?<!\w)" + re.escape(alias)
            for match in re.finditer(pattern, normalized):
                prefix = normalized[max(0, match.start() - 40):match.start()]
                prefix = re.split(r"[,;.!?]|\b(?:but|instead|and|а|но|и)\b", prefix)[-1]
                denied = bool(re.search(r"(?:\b(?:no|not|without|avoid|skip|exclude)\b(?!\s+(?:just|only)\b)|\b(?:без|кроме|никаких|не)\b)(?:\s+[\w-]+){0,3}\s*$", prefix))
                target = negative if denied else positive
                if key not in target:
                    target.append(key)
    return positive, negative


def infer_interests(text: str) -> list[str]:
    return interest_mentions(text)[0]


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[\w]+", text.casefold())
    return tokens + infer_interests(text)


class LocalLexicalEmbeddings(Embeddings):
    dimension = 512

    def embed_query(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            vec[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1
        return [x / norm for x in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    x = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(x), math.sqrt(max(0, 1 - x)))


class HybridPOIRetriever:
    def __init__(self, pois: list[dict]):
        self.pois = pois
        self.by_id = {p["id"]: p for p in pois}
        self.documents = [Document(page_content=poi_document_text(p), metadata={"poi_id": p["id"], "category": p["category"], "source": p["source"]["url"]}) for p in pois]
        self.lexical = BM25Okapi([tokenize(doc.page_content) or ["poi"] for doc in self.documents]) if self.documents else None
        self.embedding_mode = "local-feature-hash"
        embeddings = LocalLexicalEmbeddings()
        if os.getenv("QALA_EMBEDDINGS") in {"local", "fastembed"}:
            try:
                embeddings = CachedFastEmbedEmbeddings(Path(os.getenv("QALA_EMBEDDING_CACHE", Path(__file__).resolve().parents[1] / ".local/embeddings")), [doc.page_content for doc in self.documents])
                self.embedding_mode = "fastembed-local-neural"
            except Exception:
                self.embedding_mode = "local-feature-hash-cache-unavailable"
        if os.getenv("QALA_EMBEDDINGS") == "openai" and os.getenv("OPENAI_API_KEY"):
            from langchain_openai import OpenAIEmbeddings
            embeddings = OpenAIEmbeddings(model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"), request_timeout=15, max_retries=1)
            self.embedding_mode = "openai-neural"
        self.vector = InMemoryVectorStore(embeddings)
        try:
            if self.documents:
                self.vector.add_documents(self.documents)
        except Exception:
            # Explicit provider failure cannot stop the source-grounded demo.
            self.embedding_mode = "local-feature-hash-provider-fallback"
            self.vector = InMemoryVectorStore(LocalLexicalEmbeddings())
            if self.documents:
                self.vector.add_documents(self.documents)

    def search(self, query: str, location: tuple[float, float], interests: list[str], accessible: bool, indoor: bool, max_distance: float,
               excluded_ids: list[str] | None = None, excluded_categories: list[str] | None = None) -> list[dict]:
        return self.search_with_report(query, location, interests, accessible, indoor, max_distance, excluded_ids, excluded_categories)[0]

    def search_with_report(self, query: str, location: tuple[float, float], interests: list[str], accessible: bool, indoor: bool, max_distance: float,
                           excluded_ids: list[str] | None = None, excluded_categories: list[str] | None = None) -> tuple[list[dict], dict]:
        """Filter geographically before vector top-k, then fuse eligible ranks.

        Reciprocal rank fusion avoids comparing arbitrary BM25 magnitudes with
        cosine scores. Explicit categories/accessibility remain hard constraints.
        Per-call reports never mutate shared retriever state during concurrent
        users' requests.
        """
        requested = set().union(*(INTEREST_CATEGORIES.get(key, set()) for key in interests)) if interests else set()
        denied_ids, denied_categories = set(excluded_ids or []), set(excluded_categories or [])
        if "family" in interests:
            denied_categories.add("nightlife")
        fine_types = set(interests) & FINE_TYPES
        architecture_walk = "walk" in interests or bool(re.search(r"architect|landmarks?|histor(?:y|ic)|архитект|достопримеч|сәулет|тарих", query, re.I))
        rejected = {"distance": 0, "category": 0, "accessibility": 0, "indoor": 0, "excluded": 0}
        eligible = []
        for index, poi in enumerate(self.pois):
            distance = distance_m(location, (poi["lat"], poi["lon"])) * 1.3
            kind = poi.get("poi_type", poi.get("raw_tags", {}).get("amenity"))
            if poi.get("recommendable") is False or poi.get("amenities", {}).get("access") in {"private", "no"} or poi["id"] in denied_ids or poi["category"] in denied_categories or kind in denied_categories:
                rejected["excluded"] += 1
            elif distance > max_distance:
                rejected["distance"] += 1
            elif (requested and poi["category"] not in requested) or (not requested and poi["category"] in {"utility", "transport", "accommodation"}):
                rejected["category"] += 1
            elif poi["category"] == "culture" and ((fine_types and kind not in fine_types and "culture" not in interests and "walk" not in interests) or
                (architecture_walk and kind not in WALK_TYPES and kind not in fine_types) or
                (kind in {"cinema", "theatre", "events_venue", "exhibition_centre"} and kind not in fine_types)):
                rejected["category"] += 1
            elif architecture_walk and poi["category"] == "museum" and "museum" not in interests:
                rejected["category"] += 1
            elif accessible and poi.get("wheelchair") != "yes":
                rejected["accessibility"] += 1
            elif indoor and not poi.get("indoor"):
                rejected["indoor"] += 1
            else:
                eligible.append((index, poi, distance))
        report = {"corpus_count": len(self.pois), "eligible_count": len(eligible), "radius_m": round(max_distance),
                  "excluded_counts": rejected, "method": "eligible BM25 + LangChain vector reciprocal-rank fusion + intent + geography", "embedding_mode": self.embedding_mode}
        if not eligible or self.lexical is None:
            return [], {**report, "returned_count": 0}
        search_text = query + " " + " ".join(interests)
        lexical_scores = self.lexical.get_scores(tokenize(search_text))
        eligible_ids = {poi["id"] for _, poi, _ in eligible}
        try:
            vector_matches = self.vector.similarity_search_with_score(search_text, k=min(200, len(eligible)), filter=lambda doc: doc.metadata["poi_id"] in eligible_ids)
            report["vector_query_status"] = "ok"
        except Exception:
            # BM25 + metadata/geography remain useful if a query-time embedding
            # provider fails. No false claim that neural retrieval succeeded.
            vector_matches = []
            report["vector_query_status"] = "unavailable; lexical and metadata retrieval used"
        vector_scores = {doc.metadata["poi_id"]: max(0, float(score)) for doc, score in vector_matches}
        lexical_order = sorted(eligible, key=lambda item: float(lexical_scores[item[0]]), reverse=True)
        lexical_ranks = {poi["id"]: rank for rank, (index, poi, _) in enumerate(lexical_order, 1) if lexical_scores[index] > 0}
        vector_ranks = {doc.metadata["poi_id"]: rank for rank, (doc, score) in enumerate(vector_matches, 1) if score > .02}
        candidates = []
        query_tokens = set(tokenize(query))
        for index, poi, distance in eligible:
            tag_overlap = len(set(poi["tags"]) & set(interests)) / max(1, len(interests))
            name_tokens = set(tokenize(" ".join([poi["name"], *poi.get("names", {}).values()])))
            name_match = len(name_tokens & query_tokens) / max(1, len(name_tokens))
            reciprocal = sum(61 / (60 + ranks[poi["id"]]) for ranks in (lexical_ranks, vector_ranks) if poi["id"] in ranks) / 2
            proximity = 1 / (1 + distance / 700)
            score = .35 * reciprocal + .22 * tag_overlap + .28 * proximity + .15 * name_match
            evidence = {"bm25": round(float(lexical_scores[index]), 4), "vector_similarity": round(vector_scores.get(poi["id"], 0), 4),
                        "rank_fusion": round(reciprocal, 4), "matched_interests": sorted(set(poi["tags"]) & set(interests)), "name_match": round(name_match, 4)}
            candidates.append({**poi, "retrieval_score": round(score, 4), "retrieval_evidence": evidence, "distance_m": round(distance)})
        ranked = sorted(candidates, key=lambda p: (-p["retrieval_score"], p["distance_m"], p["id"]))[:60]
        return ranked, {**report, "returned_count": len(ranked), "vector_candidates": len(vector_matches)}
