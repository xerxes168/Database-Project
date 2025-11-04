# db_mongo.py
"""
MongoDB utilities for HDB HomeFinder DB.
Handles amenities, scenarios, and geospatial queries
"""

import os
import hashlib
from datetime import datetime
from typing import Dict, Any, Iterable, List, Optional

from dotenv import load_dotenv
from pymongo import MongoClient, GEOSPHERE, ASCENDING, DESCENDING, UpdateOne
from pymongo.errors import PyMongoError
from bson import ObjectId

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "homefinder")

_client: Optional[MongoClient] = None


# ---------- connection ----------
def get_db():
    """Return a connected DB handle (reused client)."""
    global _client
    if _client is None:
        _client = MongoClient(
            MONGO_URL,
            serverSelectionTimeoutMS=5000,
            appname="homefinder"
        )
        # sanity: trigger server selection once
        _client.admin.command("ping")
    return _client[MONGO_DB]


# ---------- initialization ----------
def initialize_mongodb() -> bool:
    """
    Create collections + indexes if absent. Safe to call multiple times.
    """
    try:
        db = get_db()

        # ===== AMENITIES =====
        if "amenities" not in db.list_collection_names():
            db.create_collection("amenities")
        
        # Create indexes
        try:
            db.amenities.create_index([("geometry", GEOSPHERE)])
        except:
            pass
        
        try:
            db.amenities.create_index("amenity_key", unique=True)
        except:
            pass
        
        db.amenities.create_index([("properties.amenity_type", ASCENDING)])
        db.amenities.create_index([("properties.name", ASCENDING)])

        # ===== SCENARIOS =====
        if "scenarios" not in db.list_collection_names():
            db.create_collection("scenarios")
        db.scenarios.create_index([("created_at", DESCENDING)])
        db.scenarios.create_index([("name", ASCENDING)])

        return True
    except PyMongoError as e:
        print("Mongo init error:", e)
        return False


# ---------- helpers ----------
def _norm_name(x: str) -> str:
    return " ".join(str(x or "").split()).upper()


def _amenity_key(amenity_type: str, name: str, lon: float, lat: float) -> str:
    s = f"{amenity_type}|{_norm_name(name)}|{round(lon,5)}|{round(lat,5)}"
    return hashlib.md5(s.encode()).hexdigest()


# ---------- write API ----------
def save_geojson_amenities(features: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """
    Upsert a batch of GeoJSON features into 'amenities'.
    """
    db = get_db()
    ops: List[UpdateOne] = []
    now = datetime.utcnow()

    for f in features:
        if not isinstance(f, dict) or f.get("type") != "Feature":
            continue
        geom = f.get("geometry") or {}
        if not (isinstance(geom, dict) and geom.get("type") == "Point"):
            continue
        coords = geom.get("coordinates")
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            continue
        
        lon, lat = float(coords[0]), float(coords[1])
        props = f.get("properties") or {}
        a_type = props.get("amenity_type") or "OTHER"
        name = props.get("name") or "UNKNOWN"

        akey = _amenity_key(a_type, name, lon, lat)
        
        doc = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                **props,
                "amenity_type": a_type,
                "name": _norm_name(name),
                "loaded_at": now,
            },
            "amenity_key": akey,
        }
        
        ops.append(
            UpdateOne(
                {"amenity_key": akey},
                {"$set": doc},
                upsert=True,
            )
        )

    if not ops:
        return {"upserts": 0, "modified": 0}

    try:
        res = db.amenities.bulk_write(ops, ordered=False)
        return {
            "upserts": len(res.upserted_ids or {}),
            "modified": res.modified_count or 0
        }
    except Exception as e:
        print(f"Bulk write error: {e}")
        return {"upserts": 0, "modified": 0}


# ---------- read API ----------
def get_amenities_near_location(longitude: float, latitude: float, 
                                max_distance_meters: int = 1000,
                                amenity_type: Optional[str] = None, 
                                limit: int = 50) -> List[Dict[str, Any]]:
    """
    Find amenities near (lon, lat). Uses 2dsphere index on 'geometry'.
    """
    db = get_db()
    query: Dict[str, Any] = {
        "geometry": {
            "$near": {
                "$geometry": {"type": "Point", "coordinates": [float(longitude), float(latitude)]},
                "$maxDistance": int(max_distance_meters),
            }
        }
    }
    if amenity_type:
        query["properties.amenity_type"] = amenity_type

    cur = db.amenities.find(query).limit(int(limit))
    return list(cur)


def get_amenity_stats_global() -> List[Dict[str, Any]]:
    """
    Global counts by amenity_type.
    """
    db = get_db()
    pipeline = [
        {"$group": {"_id": "$properties.amenity_type", "count": {"$sum": 1}}},
        {"$project": {"_id": 0, "amenity_type": "$_id", "count": 1}},
        {"$sort": {"count": -1}},
    ]
    return list(db.amenities.aggregate(pipeline))


def get_amenity_stats_by_town(town: str) -> Dict[str, Any]:
    """
    Get amenity counts for a specific town
    Note: This is a simplified version. For actual town-based queries,
    you'd need to store town data in the amenity properties or do geospatial lookups
    """
    db = get_db()
    
    # Get counts by type
    pipeline = [
        {"$group": {"_id": "$properties.amenity_type", "count": {"$sum": 1}}},
    ]
    
    results = list(db.amenities.aggregate(pipeline))
    
    stats = {
        "town": town,
        "total_amenities": sum(r["count"] for r in results)
    }
    
    for r in results:
        key = r["_id"].lower() + "_count" if r["_id"] else "other_count"
        stats[key] = r["count"]
    
    return stats


# ---------- scenario management ----------
def save_scenario(doc: Dict[str, Any]) -> str:
    """Save an affordability scenario"""
    db = get_db()
    doc = dict(doc)
    doc.setdefault("created_at", datetime.utcnow())
    res = db.scenarios.insert_one(doc)
    return str(res.inserted_id)


def list_scenarios(limit: int = 50) -> List[Dict[str, Any]]:
    """List all saved scenarios"""
    db = get_db()
    cursor = db.scenarios.find().sort("created_at", DESCENDING).limit(limit)
    scenarios = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        scenarios.append(doc)
    return scenarios


def get_scenario(scenario_id: str) -> Optional[Dict[str, Any]]:
    """Get a single scenario by ID"""
    db = get_db()
    try:
        doc = db.scenarios.find_one({"_id": ObjectId(scenario_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except:
        return None


def delete_scenario(scenario_id: str) -> bool:
    """Delete a scenario by ID"""
    db = get_db()
    try:
        result = db.scenarios.delete_one({"_id": ObjectId(scenario_id)})
        return result.deleted_count > 0
    except:
        return False


def check_database_health() -> bool:
    """Check if MongoDB is accessible"""
    try:
        db = get_db()
        db.command("ping")
        return True
    except:
        return False