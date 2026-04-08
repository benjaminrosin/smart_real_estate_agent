"""Listing search service used by the chat agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import logging
import re
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

from . import config

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Container returned by the listing search service."""

    listings: List[Dict[str, Any]]
    used_filters: Dict[str, Any]
    relaxed_filters: List[str]
    total_candidates: int


class ListingSearchService:
    """Query and rank rental listings for conversational search."""

    def __init__(
        self,
        connection_string: str,
        database_name: str,
        collection_name: str,
        fetch_limit: int,
        result_limit: int,
    ) -> None:
        self.client = MongoClient(connection_string)
        self.collection = self.client[database_name][collection_name]
        self.fetch_limit = max(5, fetch_limit)
        self.result_limit = max(1, result_limit)

    def _normalize_text(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip().lower()
        return cleaned or None

    def _normalize_letters_only(self, value: Optional[str]) -> Optional[str]:
        """Normalize to letters-only words for robust city matching."""
        if not value:
            return None
        cleaned = str(value).lower().replace('״', '"').replace('׳', "'")
        cleaned = re.sub(r"[^a-zA-Zא-ת]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or None

    def _city_flexible_regex(self, normalized_city: str) -> str:
        """Match city names approximately (non-exact), tolerant to separators/extra words."""
        tokens = [token for token in normalized_city.split(" ") if token]
        if not tokens:
            return re.escape(normalized_city)
        # Example: "תל אביב" should also match "תל אביב יפו" / "תל-אביב".
        return r".*" + r"[^a-zA-Zא-ת]*".join(re.escape(token) for token in tokens) + r".*"

    def _build_city_clause(self, city_value: Optional[str]) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_letters_only(city_value)
        if not normalized:
            return None

        regex = self._city_flexible_regex(normalized)
        return {
            "$or": [
                {"city_norm": {"$regex": regex, "$options": "i"}},
                {"city": {"$regex": regex, "$options": "i"}},
            ]
        }

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_int(self, value: Any) -> Optional[int]:
        parsed = self._to_float(value)
        if parsed is None:
            return None
        return int(parsed)

    def _build_query(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        query: Dict[str, Any] = {"deleted": {"$ne": True}}

        city = filters.get("city")
        neighborhood = self._normalize_text(filters.get("neighborhood"))
        property_type = self._normalize_text(filters.get("property_type"))

        city_clause = self._build_city_clause(city)
        if city_clause:
            query.update(city_clause)
        if neighborhood:
            query["neighborhood_norm"] = neighborhood
        if property_type:
            query["property_type"] = property_type

        price_min = self._to_int(filters.get("price_min"))
        price_max = self._to_int(filters.get("price_max"))
        if price_min is not None or price_max is not None:
            query["price_nis"] = {}
            if price_min is not None:
                query["price_nis"]["$gte"] = price_min
            if price_max is not None:
                query["price_nis"]["$lte"] = price_max

        rooms_min = self._to_float(filters.get("rooms_min"))
        rooms_max = self._to_float(filters.get("rooms_max"))
        if rooms_min is not None or rooms_max is not None:
            query["rooms"] = {}
            if rooms_min is not None:
                query["rooms"]["$gte"] = rooms_min
            if rooms_max is not None:
                query["rooms"]["$lte"] = rooms_max

        size_min = self._to_int(filters.get("size_min"))
        size_max = self._to_int(filters.get("size_max"))
        if size_min is not None or size_max is not None:
            query["size_sqm"] = {}
            if size_min is not None:
                query["size_sqm"]["$gte"] = size_min
            if size_max is not None:
                query["size_sqm"]["$lte"] = size_max

        if filters.get("has_parking") is True:
            query["has_parking"] = True
        if filters.get("has_elevator") is True:
            query["has_elevator"] = True
        if filters.get("has_mamad") is True:
            query["has_mamad"] = True

        logger.debug("Built Mongo query=%s from filters=%s", query, filters)
        return query

    def _fetch_candidates(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        projection = {
            "_id": 1,
            "url": 1,
            "image_url": 1,
            "street": 1,
            "price_nis": 1,
            "rooms": 1,
            "size_sqm": 1,
            "city": 1,
            "city_norm": 1,
            "neighborhood": 1,
            "neighborhood_norm": 1,
            "property_type": 1,
            "features_norm": 1,
            "has_parking": 1,
            "has_elevator": 1,
            "has_mamad": 1,
            "price_per_sqm": 1,
            "last_seen": 1,
            "floor": 1,
        }
        try:
            cursor = (
                self.collection.find(query, projection)
                .sort("last_seen", -1)
                .limit(self.fetch_limit)
            )
            candidates = list(cursor)
            logger.debug("Fetched candidates count=%s for query=%s", len(candidates), query)
            return candidates
        except Exception:
            logger.exception("Mongo candidate fetch failed query=%s", query)
            return []

    def _score_listing(self, listing: Dict[str, Any], user_filters: Dict[str, Any], ppsqm_span: Dict[str, float]) -> float:
        target_budget = self._to_int(user_filters.get("price_max"))
        budget_weight = config.WEIGHT_BUDGET_FIT
        rooms_weight = config.WEIGHT_ROOMS_FIT
        value_weight = config.WEIGHT_VALUE_PER_SQM
        recency_weight = config.WEIGHT_RECENCY

        # Budget fit: prefers entries under/near the user's max budget.
        budget_score = 0.5
        price = self._to_int(listing.get("price_nis"))
        if target_budget and target_budget > 0 and price is not None:
            if price <= target_budget:
                budget_score = max(0.0, min(1.0, 1.0 - ((target_budget - price) / max(target_budget, 1)) * 0.35))
            else:
                over_ratio = (price - target_budget) / max(target_budget, 1)
                budget_score = max(0.0, 0.6 - over_ratio)

        # Rooms fit: hard penalty below minimum, smooth reward above.
        rooms_score = 0.5
        rooms_min = self._to_float(user_filters.get("rooms_min"))
        rooms = self._to_float(listing.get("rooms"))
        if rooms_min is not None and rooms is not None:
            if rooms < rooms_min:
                rooms_score = max(0.0, rooms / max(rooms_min, 0.5))
            else:
                rooms_score = min(1.0, 0.7 + min(rooms - rooms_min, 2.0) * 0.15)

        # Value score: lower price per sqm is better when available.
        value_score = 0.5
        ppsqm = self._to_float(listing.get("price_per_sqm"))
        min_ppsqm = ppsqm_span.get("min")
        max_ppsqm = ppsqm_span.get("max")
        if ppsqm is not None and min_ppsqm is not None and max_ppsqm is not None and max_ppsqm > min_ppsqm:
            value_score = 1.0 - ((ppsqm - min_ppsqm) / (max_ppsqm - min_ppsqm))

        # Recency score: decays with age of last_seen.
        recency_score = 0.5
        last_seen = listing.get("last_seen")
        if isinstance(last_seen, datetime):
            now = datetime.now(timezone.utc)
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            days_old = max((now - last_seen).total_seconds() / 86400.0, 0.0)
            recency_score = max(0.0, 1.0 - (days_old / 14.0))

        return (
            budget_weight * budget_score
            + rooms_weight * rooms_score
            + value_weight * value_score
            + recency_weight * recency_score
        )

    def _rank(self, listings: List[Dict[str, Any]], user_filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        ppsqm_values = [self._to_float(item.get("price_per_sqm")) for item in listings]
        ppsqm_values = [value for value in ppsqm_values if value is not None]
        ppsqm_span: Dict[str, float] = {}
        if ppsqm_values:
            ppsqm_span = {"min": min(ppsqm_values), "max": max(ppsqm_values)}

        scored: List[Dict[str, Any]] = []
        for item in listings:
            score = self._score_listing(item, user_filters, ppsqm_span)
            enriched = dict(item)
            enriched["_score"] = score
            scored.append(enriched)

        scored.sort(
            key=lambda item: (
                -item.get("_score", 0.0),
                self._to_int(item.get("price_nis")) or 99999999,
                -(item.get("last_seen").timestamp() if isinstance(item.get("last_seen"), datetime) else 0),
            )
        )
        logger.debug("Ranked listings count=%s using filters=%s", len(scored), user_filters)
        return scored

    def _relax_filters(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        variants: List[Dict[str, Any]] = [dict(filters)]

        for amenity in ("has_parking", "has_elevator", "has_mamad"):
            if filters.get(amenity) is True:
                relaxed = dict(filters)
                relaxed.pop(amenity, None)
                variants.append(relaxed)

        if filters.get("neighborhood"):
            relaxed = dict(filters)
            relaxed.pop("neighborhood", None)
            variants.append(relaxed)

        if filters.get("property_type"):
            relaxed = dict(filters)
            relaxed.pop("property_type", None)
            variants.append(relaxed)

        rooms_min = self._to_float(filters.get("rooms_min"))
        if rooms_min is not None and rooms_min >= 2.0:
            relaxed = dict(filters)
            relaxed["rooms_min"] = max(1.0, rooms_min - 0.5)
            variants.append(relaxed)

        return variants

    def search(self, filters: Dict[str, Any]) -> SearchResult:
        logger.info("Starting listing search filters=%s", filters)
        variants = self._relax_filters(filters)
        seen_queries = set()
        logger.debug("Generated filter variants count=%s", len(variants))

        for idx, variant in enumerate(variants):
            query = self._build_query(variant)
            serialized = str(query)
            if serialized in seen_queries:
                continue
            seen_queries.add(serialized)

            candidates = self._fetch_candidates(query)
            if not candidates:
                logger.debug("No candidates for variant_index=%s variant=%s", idx, variant)
                continue

            ranked = self._rank(candidates, variant)
            top = ranked[: self.result_limit]
            relaxed = [] if idx == 0 else ["filters_relaxed"]
            logger.info(
                "Search success variant_index=%s candidates=%s returned=%s relaxed=%s",
                idx,
                len(ranked),
                len(top),
                relaxed,
            )
            return SearchResult(
                listings=top,
                used_filters=variant,
                relaxed_filters=relaxed,
                total_candidates=len(ranked),
            )

        logger.info("Search finished with no results filters=%s", filters)
        return SearchResult(listings=[], used_filters=filters, relaxed_filters=["no_results"], total_candidates=0)

    def _format_listing_location(self, item: Dict[str, Any]) -> str:
        city = item.get("city") or item.get("city_norm") or "לא צוין"
        neighborhood = item.get("neighborhood") or item.get("neighborhood_norm") or ""
        location = city if not neighborhood else f"{city}, {neighborhood}"
        return html.escape(str(location))

    def _format_listing_title(self, item: Dict[str, Any]) -> str:
        prop_type = item.get("property_type") or "נכס"
        return f"{html.escape(str(prop_type))} - {self._format_listing_location(item)}"

    def _format_main_features(self, item: Dict[str, Any]) -> List[str]:
        features: List[str] = []
        price = self._to_int(item.get("price_nis"))
        rooms = self._to_float(item.get("rooms"))
        size = self._to_int(item.get("size_sqm"))
        floor = self._to_int(item.get("floor"))
        street = item.get("street")

        features.append(f"מחיר: {price:,} ₪" if price is not None else "מחיר: לא צוין")
        if street:
            features.append(f"רחוב: {html.escape(str(street))}")
        if rooms is not None:
            features.append(f"חדרים: {rooms:g}")
        if size is not None:
            features.append(f"שטח: {size} מ\"ר")
        if floor is not None:
            features.append(f"קומה: {floor}")

        amenities: List[str] = []
        if item.get("has_parking"):
            amenities.append("חניה")
        if item.get("has_elevator"):
            amenities.append("מעלית")
        if item.get("has_mamad"):
            amenities.append('ממ\"ד')
        if not amenities:
            raw_features = item.get("features_norm") or []
            amenities = [str(feature) for feature in raw_features[:3]]

        if amenities:
            safe_amenities = ", ".join(html.escape(value) for value in amenities)
            features.append(f"מאפיינים: {safe_amenities}")

        return features

    def _build_primary_caption(self, item: Dict[str, Any]) -> str:
        lines: List[str] = [f"<b>{self._format_listing_title(item)}</b>", ""]
        for feature in self._format_main_features(item):
            lines.append(f"• {feature}")

        url = item.get("url")
        if url:
            safe_url = html.escape(str(url), quote=True)
            lines.append("")
            lines.append(f'<a href="{safe_url}">לצפייה במודעה המלאה</a>')

        return "\n".join(lines).strip()

    def format_search_response(self, result: SearchResult) -> Dict[str, Any]:
        if not result.listings:
            return {
                "assistant_text": (
                    "לא מצאתי כרגע מודעות פעילות שמתאימות בדיוק לסינון הזה. "
                    "אפשר להרחיב קצת תקציב, אזור או מספר חדרים ואחפש שוב."
                ),
                "primary_listing": None,
                "listing_cards": [],
                "suggestions": [],
            }

        listing_cards = [
            {
                "caption": self._build_primary_caption(item),
                "image_url": item.get("image_url"),
                "url": item.get("url"),
            }
            for item in result.listings
        ]

        primary = result.listings[0]
        primary_payload = {
            "caption": self._build_primary_caption(primary),
            "image_url": primary.get("image_url"),
            "url": primary.get("url"),
        }

        suggestion_lines: List[str] = []
        for idx, item in enumerate(result.listings[1:4], start=2):
            title = self._format_listing_title(item)
            url = item.get("url")
            if url:
                safe_url = html.escape(str(url), quote=True)
                suggestion_lines.append(f'• {idx}) <a href="{safe_url}">{title}</a>')
            else:
                suggestion_lines.append(f"• {idx}) {title}")

        lines: List[str] = [
            "<b>מצאתי התאמות לפי הקריטריונים שלך.</b>",
            "מעל מופיעה ההמלצה המובילה שלי.",
        ]
        if suggestion_lines:
            lines.append("")
            lines.append("עוד אפשרויות טובות:")
            lines.extend(suggestion_lines)
            lines.append("")
            lines.append("רוצה שאציג את האפשרות הבאה בפירוט מלא?")

        if result.relaxed_filters:
            lines.append("")
            lines.append("<i>שחררתי חלק מהפילטרים האופציונליים כדי להציג יותר תוצאות.</i>")

        return {
            "assistant_text": "\n".join(lines).strip(),
            "primary_listing": primary_payload,
            "listing_cards": listing_cards,
            "suggestions": suggestion_lines,
        }