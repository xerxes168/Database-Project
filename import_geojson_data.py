#!/usr/bin/env python3
# geojson_import_sanitised.py
# Self-contained, type-safe importer with one-time sanitisation and safe upserts.
# Usage examples:
#   python geojson_import_sanitised.py --dir ./data
#   python geojson_import_sanitised.py --file ./data/CHASClinics.geojson
#   python geojson_import_sanitised.py --verify
#   python geojson_import_sanitised.py --sanitize-existing

import os
import json
import argparse
from typing import Any, Dict, List, Union, Optional
from datetime import datetime

from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

# ----------------------------
# Mongo connection
# ----------------------------
def get_client() -> MongoClient:
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    return MongoClient(uri)

def get_db():
    db_name = os.getenv("DB_NAME", "local")
    return get_client()[db_name]

# ----------------------------
# Amenity type detection
# ----------------------------
def detect_amenity_type(filename: str) -> str:
    fname = filename.lower()
    if "mrt" in fname:
        return "MRT"
    if "clinic" in fname or "chas" in fname:
        return "CLINIC"
    if "school" in fname:
        return "SCHOOL_ZONE"
    if "park" in fname:
        return "PARK"
    if "supermarket" in fname:
        return "SUPERMARKET"
    return "OTHER"

def _name_from_props(props: Dict[str, Any], default_name: str) -> str:
    for k in ("name", "Name", "NAME", "STN_NAME", "STATION", "HCI_NAME", "FACILITY", "BLDG_NAME", "POI_NAME"):
        if k in props and props[k] not in (None, ""):
            return str(props[k])
    return default_name

# ----------------------------
# Coercion helpers (robust for mixed types)
# ----------------------------
def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)

def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        s = str(value).strip().replace(",", "")
        if s.startswith("+"):
            s = s[1:]
        f = float(s)
        if int(f) == f:
            return int(f)
        return int(round(f))
    except Exception:
        return None

def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        s = str(value).strip().replace(",", "")
        return float(s)
    except Exception:
        return None

def _coerce_coords(x: Any) -> Any:
    if isinstance(x, list):
        return [_coerce_coords(i) for i in x]
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        f = _to_float(x)
        return f if f is not None else x
    return x

# Known-property coercion rules (broad-safe set)
_STR_KEYS = {
    "name", "Name", "NAME", "Description", "CLASS", "UNIQUEID",
    "STN_NAME", "STATION", "HCI_NAME", "FACILITY", "BLDG_NAME", "POI_NAME",
}
_INT_KEYS = {"OBJECTID"}
_OPTIONAL_STR_KEYS = {"ADDITIONAL_INFO"}

def normalize_feature_types(feat: Dict[str, Any], default_type: str, default_name: str) -> Optional[Dict[str, Any]]:
    if not isinstance(feat, dict) or feat.get("type") != "Feature":
        return None

    props: Dict[str, Any] = feat.setdefault("properties", {}) or {}

    # Coerce known keys
    for k in list(props.keys()):
        if k in _STR_KEYS:
            props[k] = _to_str(props[k])
        elif k in _INT_KEYS:
            iv = _to_int(props[k])
            props[k] = iv if iv is not None else _to_str(props[k])
        elif k in _OPTIONAL_STR_KEYS:
            v = props[k]
            props[k] = "" if v is None else _to_str(v)

    # Standardise 'amenity_type' and 'name'
    a_type = props.get("amenity_type") or default_type or "OTHER"
    props["amenity_type"] = _to_str(a_type).upper().strip() or "OTHER"

    canonical_name = _name_from_props(props, default_name)
    props["name"] = _to_str(canonical_name).strip() or default_name

    # Geometry
    geom = feat.get("geometry") or {}
    if not geom or "type" not in geom or "coordinates" not in geom:
        return None
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    geom["coordinates"] = _coerce_coords(coords)

    if gtype == "Point":
        if not (isinstance(geom["coordinates"], list) and len(geom["coordinates"]) >= 2):
            return None

    feat["properties"] = props
    feat["geometry"] = geom
    return feat

# ----------------------------
# Indices
# ----------------------------
def initialize_mongodb():
    db = get_db()
    points = db["amenities"]
    zones = db["amenity_zones"]
    # Points
    try:
        points.create_index([("geometry", "2dsphere")])
        points.create_index([("properties.amenity_type", 1)])
        points.create_index([("properties.name", 1)])
        points.create_index([("amenity_key", 1)], unique=True)
    except Exception:
        pass
    # Zones
    try:
        zones.create_index([("geometry", "2dsphere")])
        zones.create_index([("properties.amenity_type", 1)])
        zones.create_index([("properties.name", 1)])
        zones.create_index([("properties.amenity_type", 1), ("properties.name", 1)], unique=True)
    except Exception:
        pass

# ----------------------------
# One-time sanitiser for legacy docs
# ----------------------------
def sanitize_existing_collections():
    db = get_db()
    for colname in ("amenities", "amenity_zones"):
        col = db[colname]
        # Use pipeline update if supported (MongoDB 4.2+)
        try:
            res = col.update_many(
                { "properties": { "$not": { "$type": "object" } } },
                [ { "$set": { "properties": {} } } ]
            )
            print(f"[sanitiser] {colname}: pipeline update matched={res.matched_count}, modified={res.modified_count}")
        except Exception as e:
            # Fallback: iterative fix
            bad = list(col.find({ "properties": { "$not": { "$type": "object" } } }, { "_id": 1 }))
            for d in bad:
                col.update_one({ "_id": d["_id"] }, { "$set": { "properties": {} } })
            print(f"[sanitiser:fallback] {colname}: fixed {len(bad)} docs")

# ----------------------------
# Save helpers
# ----------------------------
def _stable_key_for_point(feat: Dict[str, Any]) -> str:
    props = feat.get("properties", {})
    a_type = (props.get("amenity_type") or "OTHER").upper()
    name = props.get("name") or "UNKNOWN"
    # Optional: include rounded coordinates for extra uniqueness
    geom = feat.get("geometry", {})
    coords = geom.get("coordinates", [])
    if isinstance(coords, list) and len(coords) >= 2 and all(isinstance(c, (int, float)) for c in coords[:2]):
        lng, lat = coords[0], coords[1]
        return f"{a_type}::{name}::{round(lat,6)},{round(lng,6)}"
    return f"{a_type}::{name}"

def save_points(features: List[Dict[str, Any]]):
    db = get_db()
    col = db["amenities"]
    ts = datetime.utcnow()
    ops = []
    for feat in features:
        props = feat.get("properties") or {}
        amenity_key = props.get("amenity_key") or _stable_key_for_point(feat)
        update_doc = {
            "$set": {
                "type": "Feature",
                "geometry": feat.get("geometry", {}),
                "properties": props,
                "meta": { "loaded_at": ts },
            }
        }
        ops.append(
            UpdateOne(
                { "amenity_key": amenity_key },
                update_doc,
                upsert=True
            )
        )
    if not ops:
        return {"upserts": 0, "modified": 0}
    try:
        result = col.bulk_write(ops, ordered=False)
        upserts = len(getattr(result, "upserted_ids", {}) or {})
        modified = getattr(result, "modified_count", 0) or 0
        return {"upserts": upserts, "modified": modified}
    except BulkWriteError as bwe:
        print("[bulk_write:error]", bwe.details)
        raise

def save_nonpoints(features: List[Dict[str, Any]]):
    db = get_db()
    col = db["amenity_zones"]
    ts = datetime.utcnow()
    ops = []
    for feat in features:
        props = feat.get("properties") or {}
        a_type = (props.get("amenity_type") or "OTHER").upper()
        name = props.get("name") or "UNKNOWN"
        key = {
            "properties.amenity_type": a_type,
            "properties.name": name,
        }
        update_doc = {
            "$set": {
                "type": "Feature",
                "geometry": feat.get("geometry", {}),
                "properties": props,
                "meta": { "loaded_at": ts },
            }
        }
        ops.append(UpdateOne(key, update_doc, upsert=True))
    if not ops:
        return {"upserts": 0, "modified": 0}
    try:
        result = col.bulk_write(ops, ordered=False)
        upserts = len(getattr(result, "upserted_ids", {}) or {})
        modified = getattr(result, "modified_count", 0) or 0
        return {"upserts": upserts, "modified": modified}
    except BulkWriteError as bwe:
        print("[bulk_write:error]", bwe.details)
        raise

# ----------------------------
# Core importers
# ----------------------------
def import_single_geojson(file_path: str, amenity_type: Optional[str] = None) -> int:
    filename = os.path.basename(file_path)
    if not amenity_type:
        amenity_type = detect_amenity_type(filename)

    print(f"\n📂 Processing: {filename}")
    print(f"   Type: {amenity_type}")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"   ❌ Invalid JSON: {e}")
        return 0

    # Normalise to features list
    if isinstance(data, dict):
        if data.get("type") == "FeatureCollection":
            features = data.get("features", [])
        elif data.get("type") == "Feature":
            features = [data]
        else:
            features = data.get("features", [])
    elif isinstance(data, list):
        features = data
    else:
        features = []

    print(f"   Found: {len(features)} features")

    default_name = os.path.splitext(filename)[0]
    cleaned_points: List[Dict[str, Any]] = []
    cleaned_nonpoints: List[Dict[str, Any]] = []
    for feat in features:
        cleaned = normalize_feature_types(feat, amenity_type, default_name)
        if not cleaned:
            continue
        gtype = cleaned["geometry"].get("type")
        if gtype == "Point":
            cleaned_points.append(cleaned)
        else:
            cleaned_nonpoints.append(cleaned)

    total = 0
    if cleaned_points:
        res = save_points(cleaned_points)
        print(f"   ✅ Points -> amenities | Upserted: {res.get('upserts',0)}, Modified: {res.get('modified',0)}")
        total += res.get("upserts",0) + res.get("modified",0)
    if cleaned_nonpoints:
        res = save_nonpoints(cleaned_nonpoints)
        print(f"   ✅ Non-points -> amenity_zones | Upserted: {res.get('upserts',0)}, Modified: {res.get('modified',0)}")
        total += res.get("upserts",0) + res.get("modified",0)
    if not cleaned_points and not cleaned_nonpoints:
        print("   ⚠️  No valid features with geometry. Skipping.")
    return total

def import_geojson_dir(dir_path: str) -> int:
    if not os.path.isdir(dir_path):
        print(f"❌ Not a directory: {dir_path}")
        return 0
    total = 0
    for name in sorted(os.listdir(dir_path)):
        if not name.lower().endswith((".geojson", ".json")):
            continue
        path = os.path.join(dir_path, name)
        total += import_single_geojson(path)
    print(f"\n📦 Total upserted/modified across all files: {total}")
    return total

# ----------------------------
# Verify
# ----------------------------
def verify():
    db = get_db()
    col = db["amenities"]
    zones = db["amenity_zones"]

    # totals
    try:
        total_points = col.estimated_document_count()
    except AttributeError:
        total_points = col.count_documents({})
    try:
        total_zones = zones.estimated_document_count()
    except AttributeError:
        total_zones = zones.count_documents({})

    print(f"\n📊 amenities (points) total: {total_points}")
    print(f"📊 amenity_zones (non-points) total: {total_zones}")

    # breakdown by type (points)
    pipeline = [
        {"$group": {"_id": "$properties.amenity_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    try:
        print("\n🧾 Count by amenity_type (points):")
        for doc in col.aggregate(pipeline):
            print(f"   {doc.get('_id') or 'UNKNOWN'} : {doc.get('count', 0)}")
    except Exception as e:
        print(f"   ⚠️ aggregate error (points): {e}")

    # breakdown by type (zones)
    try:
        print("\n🧾 Count by amenity_type (zones):")
        for doc in zones.aggregate(pipeline):
            print(f"   {doc.get('_id') or 'UNKNOWN'} : {doc.get('count', 0)}")
    except Exception as e:
        print(f"   ⚠️ aggregate error (zones): {e}")

    # Samples
    print("\n🔎 Sample docs (points):")
    for d in col.find({}, {"properties.name": 1, "properties.amenity_type": 1, "geometry.type": 1}).limit(5):
        props = d.get("properties", {}) or {}
        print(f"   [{props.get('amenity_type')}] {props.get('name')} ({d.get('geometry',{}).get('type')})")

    print("\n🔎 Sample docs (zones):")
    for d in zones.find({}, {"properties.name": 1, "properties.amenity_type": 1, "geometry.type": 1}).limit(5):
        props = d.get("properties", {}) or {}
        print(f"   [{props.get('amenity_type')}] {props.get('name')} ({d.get('geometry',{}).get('type')})")

    # Indexes
    print("\n🧭 Indexes (amenities):")
    for idx in col.list_indexes():
        print("   ", idx)
    print("\n🧭 Indexes (amenity_zones):")
    for idx in zones.list_indexes():
        print("   ", idx)

# ----------------------------
# CLI
# ----------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Import GeoJSON amenities into MongoDB (sanitised & type-safe)")
    p.add_argument("--file", help="Path to a single .geojson")
    p.add_argument("--dir", help="Path to a folder containing .geojson/.json files")
    p.add_argument("--type", help="Override amenity_type for --file import")
    p.add_argument("--verify", action="store_true", help="Verify counts & sample docs")
    p.add_argument("--sanitize-existing", action="store_true", help="Sanitise legacy docs where properties is not an object")
    return p.parse_args()

def main():
    args = parse_args()
    initialize_mongodb()
    if args.sanitize_existing:
        sanitize_existing_collections()
    if args.verify:
        verify()
        return
    if args.file:
        import_single_geojson(args.file, args.type)
    elif args.dir:
        import_geojson_dir(args.dir)
    else:
        print("Usage:")
        print("  python geojson_import_sanitised.py --file /path/to/file.geojson [--type MRT]")
        print("  python geojson_import_sanitised.py --dir /path/to/folder")
        print("  python geojson_import_sanitised.py --sanitize-existing")
        print("  python geojson_import_sanitised.py --verify")

if __name__ == "__main__":
    main()
