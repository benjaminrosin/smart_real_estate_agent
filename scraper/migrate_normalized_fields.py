"""
Backfill migration for normalized listing fields.

This migration updates existing MongoDB documents to match the newer
search-oriented schema introduced in the scraper parser.

Usage examples:
  python migrate_normalized_fields.py --dry-run
  python migrate_normalized_fields.py
  python migrate_normalized_fields.py --limit 500
    python migrate_normalized_fields.py --backup-collection listings_backup_before_norm
    python migrate_normalized_fields.py --skip-backup
        python migrate_normalized_fields.py --keep-url-id-listings
"""
import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pymongo import UpdateOne

from src.db_manager import MongoDBManager
from src.parser import Yad2Parser


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", ".")
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _build_normalized_update(doc: Dict[str, Any], parser: Yad2Parser) -> Dict[str, Any]:
    update: Dict[str, Any] = {}

    # Price fields
    price_raw = doc.get("price_raw")
    if not price_raw and isinstance(doc.get("price"), str):
        price_raw = doc.get("price")
        update["price_raw"] = price_raw

    has_price_source = (
        isinstance(price_raw, str)
        or "price" in doc
        or "price_nis" in doc
    )
    price_nis = doc.get("price_nis")
    if has_price_source and not isinstance(price_nis, (int, float)):
        parsed_price = parser._parse_price_nis(price_raw) if isinstance(price_raw, str) else None
        if parsed_price is None:
            parsed_price = _to_int(doc.get("price"))
        update["price_nis"] = parsed_price
        price_nis = parsed_price

    if has_price_source and doc.get("price") != price_nis:
        update["price"] = price_nis

    # Property type fields
    property_type_raw = doc.get("property_type_raw")
    current_property_type = doc.get("property_type")
    if not property_type_raw and isinstance(current_property_type, str):
        property_type_raw = current_property_type
        update["property_type_raw"] = property_type_raw

    if isinstance(property_type_raw, str):
        normalized_property_type = parser._normalize_property_type(property_type_raw)
    elif isinstance(current_property_type, str):
        normalized_property_type = parser._normalize_property_type(current_property_type)
    else:
        normalized_property_type = current_property_type

    if normalized_property_type != current_property_type:
        update["property_type"] = normalized_property_type

    # City and neighborhood normalized fields
    city = doc.get("city")
    city_norm = parser._normalize_text_token(city) if isinstance(city, str) else None
    if city_norm != doc.get("city_norm"):
        update["city_norm"] = city_norm

    neighborhood = doc.get("neighborhood")
    neighborhood_norm = parser._normalize_text_token(neighborhood) if isinstance(neighborhood, str) else None
    if neighborhood_norm != doc.get("neighborhood_norm"):
        update["neighborhood_norm"] = neighborhood_norm

    # Numeric listing attributes
    rooms = doc.get("rooms")
    has_rooms_source = (
        "rooms" in doc
        or "rooms_raw" in doc
        or isinstance(rooms, str)
    )
    if not doc.get("rooms_raw") and isinstance(rooms, str):
        update["rooms_raw"] = rooms
    if has_rooms_source and not isinstance(rooms, (int, float)):
        rooms_parsed = parser._parse_rooms(doc.get("rooms_raw")) if isinstance(doc.get("rooms_raw"), str) else None
        if rooms_parsed is None and isinstance(rooms, str):
            rooms_parsed = parser._parse_rooms(rooms)
        if rooms_parsed is None:
            rooms_parsed = _to_float(rooms)
        update["rooms"] = rooms_parsed

    floor = doc.get("floor")
    has_floor_source = (
        "floor" in doc
        or "floor_raw" in doc
        or isinstance(floor, str)
    )
    if not doc.get("floor_raw") and isinstance(floor, str):
        update["floor_raw"] = floor
    if has_floor_source and not isinstance(floor, int):
        floor_parsed = parser._parse_floor(doc.get("floor_raw")) if isinstance(doc.get("floor_raw"), str) else None
        if floor_parsed is None and isinstance(floor, str):
            floor_parsed = parser._parse_floor(floor)
        if floor_parsed is None:
            floor_parsed = _to_int(floor)
        update["floor"] = floor_parsed

    size_sqm = doc.get("size_sqm")
    has_size_source = (
        "size_sqm" in doc
        or "size_sqm_raw" in doc
        or isinstance(size_sqm, str)
    )
    if not doc.get("size_sqm_raw") and isinstance(size_sqm, str):
        update["size_sqm_raw"] = size_sqm
    if has_size_source and not isinstance(size_sqm, int):
        size_parsed = parser._parse_size_sqm(doc.get("size_sqm_raw")) if isinstance(doc.get("size_sqm_raw"), str) else None
        if size_parsed is None and isinstance(size_sqm, str):
            size_parsed = parser._parse_size_sqm(size_sqm)
        if size_parsed is None:
            size_parsed = _to_int(size_sqm)
        update["size_sqm"] = size_parsed
        size_sqm = size_parsed

    if not isinstance(size_sqm, int):
        size_sqm = doc.get("size_sqm") if isinstance(doc.get("size_sqm"), int) else None

    if isinstance(price_nis, (int, float)) and isinstance(size_sqm, int) and size_sqm > 0:
        ppsm = round(float(price_nis) / size_sqm, 2)
    else:
        ppsm = None

    should_emit_ppsm = has_price_source and has_size_source
    if should_emit_ppsm and doc.get("price_per_sqm") != ppsm:
        update["price_per_sqm"] = ppsm

    # Features normalization and derived booleans
    features = doc.get("features")
    features_norm: List[str] = []
    if isinstance(features, list):
        clean_features = [str(v) for v in features if isinstance(v, str)]
        features_norm = parser._normalize_features(clean_features)

    if isinstance(features, list) and features_norm != doc.get("features_norm"):
        update["features_norm"] = features_norm

    feature_set = set(features_norm)
    has_elevator = "מעלית" in feature_set
    has_parking = "חניה" in feature_set
    has_mamad = 'ממ"ד' in feature_set

    if doc.get("has_elevator") != has_elevator:
        update["has_elevator"] = has_elevator
    if doc.get("has_parking") != has_parking:
        update["has_parking"] = has_parking
    if doc.get("has_mamad") != has_mamad:
        update["has_mamad"] = has_mamad

    # Location enrichment prep fields
    street_norm = parser._normalize_text_token(doc.get("street")) if isinstance(doc.get("street"), str) else None
    building_number = doc.get("building_number")
    if building_number is not None:
        building_number = str(building_number).strip() or None

    location_parts = [city_norm, neighborhood_norm, street_norm, building_number]
    location_parts = [part for part in location_parts if part]
    location_key = "|".join(location_parts) if location_parts else None

    if location_key and doc.get("location_key") != location_key:
        update["location_key"] = location_key

    if location_key and not doc.get("location_point"):
        geocode_status = "pending"
        if doc.get("geocode_status") != geocode_status:
            update["geocode_status"] = geocode_status

    update["schema_migrated_at"] = datetime.utcnow()
    return update


def migrate(
    collection_name: str,
    dry_run: bool,
    limit: Optional[int],
    strict_validation: bool,
    backup_collection: Optional[str],
    skip_backup: bool,
    keep_url_id_listings: bool,
) -> None:
    db = MongoDBManager()
    if not db.connect(collection_name=collection_name):
        print("Failed to connect to MongoDB.")
        return

    parser = Yad2Parser("<html></html>")

    try:
        backup_name: Optional[str] = None
        if not dry_run and not skip_backup:
            backup_name = backup_collection or f"{collection_name}_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            print(f"Creating backup collection: {backup_name}")
            db.collection.aggregate([{"$match": {}}, {"$out": backup_name}])

        url_id_query: Dict[str, Any] = {
            "$and": [
                {"_id": {"$type": "string"}},
                {"_id": {"$regex": r"^https"}},
            ]
        }
        url_id_matches = db.collection.count_documents(url_id_query)
        url_id_deleted = 0
        if not keep_url_id_listings and url_id_matches > 0:
            if dry_run:
                print(f"Dry run: would delete {url_id_matches} documents where _id starts with https")
            else:
                delete_result = db.collection.delete_many(url_id_query)
                url_id_deleted = delete_result.deleted_count
                print(f"Deleted {url_id_deleted} documents where _id starts with https")

        query: Dict[str, Any] = {}
        cursor = db.collection.find(query)
        if limit and limit > 0:
            cursor = cursor.limit(limit)

        scanned = 0
        to_update = 0
        skipped_invalid = 0
        bulk_ops: List[UpdateOne] = []

        for doc in cursor:
            scanned += 1
            update_fields = _build_normalized_update(doc, parser)

            # Remove no-op timestamp-only updates
            keys_without_ts = [k for k in update_fields.keys() if k != "schema_migrated_at"]
            if not keys_without_ts:
                continue

            if strict_validation:
                candidate = dict(doc)
                candidate.update(update_fields)
                if not db._validate_listing_schema(candidate):
                    skipped_invalid += 1
                    continue

            to_update += 1
            if not dry_run:
                bulk_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": update_fields}))

            if not dry_run and len(bulk_ops) >= 500:
                db.collection.bulk_write(bulk_ops, ordered=False)
                bulk_ops = []

        if not dry_run and bulk_ops:
            db.collection.bulk_write(bulk_ops, ordered=False)

        print("=" * 80)
        print("Normalized Field Migration Summary")
        print("=" * 80)
        print(f"Collection: {collection_name}")
        print(f"Dry run: {dry_run}")
        print(f"Strict validation: {strict_validation}")
        print(f"Scanned: {scanned}")
        print(f"Eligible updates: {to_update}")
        print(f"Skipped (validation failed): {skipped_invalid}")
        if keep_url_id_listings:
            print(f"URL _id listings kept: {url_id_matches}")
        else:
            print(f"URL _id listings matched: {url_id_matches}")
            if not dry_run:
                print(f"URL _id listings deleted: {url_id_deleted}")
        if backup_name:
            print(f"Backup collection: {backup_name}")
        print("=" * 80)

    finally:
        db.disconnect()


def main() -> None:
    load_dotenv()

    arg_parser = argparse.ArgumentParser(
        description="Backfill normalized listing fields for the scraper schema"
    )
    arg_parser.add_argument(
        "--collection",
        default="listings",
        help="MongoDB collection name (default: listings)",
    )
    arg_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without writing to MongoDB",
    )
    arg_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of documents to process",
    )
    arg_parser.add_argument(
        "--strict-validation",
        action="store_true",
        help="Validate migrated docs against strict upsert schema before writing",
    )
    arg_parser.add_argument(
        "--backup-collection",
        default=None,
        help="Optional backup collection name (default: auto timestamped)",
    )
    arg_parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip creating a backup collection before writes",
    )
    arg_parser.add_argument(
        "--keep-url-id-listings",
        action="store_true",
        help="Do not delete documents whose _id is a full URL starting with https",
    )

    args = arg_parser.parse_args()
    migrate(
        collection_name=args.collection,
        dry_run=args.dry_run,
        limit=args.limit,
        strict_validation=args.strict_validation,
        backup_collection=args.backup_collection,
        skip_backup=args.skip_backup,
        keep_url_id_listings=args.keep_url_id_listings,
    )


if __name__ == "__main__":
    main()
