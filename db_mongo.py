# MongoDB utilities for HDB HomeFinder DB.
# Handles amenities, scenarios, listing_remarks, user_profiles and town_metadata

import os
import hashlib
from datetime import datetime
from typing import Dict, Any, Iterable, List, Optional

from dotenv import load_dotenv
from pymongo import MongoClient, GEOSPHERE, ASCENDING, DESCENDING, TEXT, UpdateOne
from pymongo.errors import PyMongoError
from bson import ObjectId

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "homefinder")

_client: Optional[MongoClient] = None


# ========== CONNECTION ==========
def get_db():
    # Return a connected DB handle (reused client)
    global _client
    if _client is None:
        _client = MongoClient(
            MONGO_URL,
            serverSelectionTimeoutMS=5000,
            appname="homefinder"
        )
        _client.admin.command("ping")
    return _client[MONGO_DB]


# ========== INTIALIZATION ==========
def initialize_mongodb() -> bool:
    # Create collections + indexes if absent
    try:
        db = get_db()

        # ===== AMENITIES =====
        if "amenities" not in db.list_collection_names():
            db.create_collection("amenities")
        
        try:
            db.amenities.create_index([("geometry", GEOSPHERE)])
        except:
            pass
        
        try:
            db.amenities.create_index("amenity_key", unique=True)
        except:
            pass
        
        db.amenities.create_index([("properties.amenity_type", ASCENDING)])
        db.amenities.create_index([("properties.CLASS", ASCENDING)])
        db.amenities.create_index([("properties.name", ASCENDING)])

        # ===== LISTING REMARKS (TEXT SEARCH) =====
        if "listing_remarks" not in db.list_collection_names():
            db.create_collection("listing_remarks")
        
        try:
            db.listing_remarks.create_index([("remarks", TEXT)])
        except:
            pass
        
        db.listing_remarks.create_index([("town", ASCENDING)])
        db.listing_remarks.create_index([("flat_type", ASCENDING)])
        db.listing_remarks.create_index([("created_date", DESCENDING)])
        db.listing_remarks.create_index([("block", ASCENDING), ("street", ASCENDING)])

        # ===== USER PROFILES =====
        if "user_profiles" not in db.list_collection_names():
            db.create_collection("user_profiles")
        
        db.user_profiles.create_index([("email", ASCENDING)], unique=True)
        db.user_profiles.create_index([("registration_date", DESCENDING)])

        # ===== TOWN METADATA =====
        if "town_metadata" not in db.list_collection_names():
            db.create_collection("town_metadata")
        
        db.town_metadata.create_index([("town_name", ASCENDING)], unique=True)
        db.town_metadata.create_index([("region", ASCENDING)])
        db.town_metadata.create_index([("maturity", ASCENDING)])

        # ===== SCENARIOS =====
        if "scenarios" not in db.list_collection_names():
            db.create_collection("scenarios")
        db.scenarios.create_index([("created_at", DESCENDING)])
        db.scenarios.create_index([("name", ASCENDING)])
        db.scenarios.create_index([("user_id", ASCENDING)])

        return True
    except PyMongoError as e:
        print("Mongo init error:", e)
        return False


# ========== HELPERS ==========
def _norm_name(x: str) -> str:
    return " ".join(str(x or "").split()).upper()


def _amenity_key(amenity_type: str, name: str, lon: float, lat: float) -> str:
    s = f"{amenity_type}|{_norm_name(name)}|{round(lon,5)}|{round(lat,5)}"
    return hashlib.md5(s.encode()).hexdigest()


# ========== AMENITIES API ==========
def save_geojson_amenities(features: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    # Upsert a batch of GeoJSON features into 'amenities'
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
        a_type = props.get("amenity_type") or props.get("CLASS") or "OTHER"
        name = props.get("name") or props.get("NAME") or "UNKNOWN"

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


def get_amenities_near_location(longitude: float, latitude: float, 
                                max_distance_meters: int = 1000,
                                amenity_type: Optional[str] = None, 
                                limit: int = 50) -> List[Dict[str, Any]]:
    # Find amenities near (lon, lat). Uses 2dsphere index
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
    # Global counts by amenity_type
    db = get_db()
    pipeline = [
        {"$group": {"_id": "$properties.amenity_type", "count": {"$sum": 1}}},
        {"$project": {"_id": 0, "amenity_type": "$_id", "count": 1}},
        {"$sort": {"count": -1}},
    ]
    return list(db.amenities.aggregate(pipeline))


def get_amenity_stats_by_town(town: str) -> Dict[str, Any]:
    # Get amenity counts (simplified version)
    db = get_db()
    
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


# ========== LISTING REMARKS API (TEXT SEARCH) ==========
def save_listing_remark(remark_data: Dict[str, Any]) -> str:
    # Save a listing remark/description
    db = get_db()
    remark_data = dict(remark_data)
    remark_data.setdefault("created_date", datetime.utcnow())
    res = db.listing_remarks.insert_one(remark_data)
    return str(res.inserted_id)


def search_listing_remarks(query: str, town: Optional[str] = None, 
                          flat_type: Optional[str] = None, 
                          limit: int = 20) -> List[Dict[str, Any]]:
    db = get_db()
    
    search_filter: Dict[str, Any] = {"$text": {"$search": query}}
    
    if town:
        search_filter["town"] = town
    if flat_type:
        search_filter["flat_type"] = flat_type
    
    cursor = db.listing_remarks.find(
        search_filter,
        {"score": {"$meta": "textScore"}}
    ).sort([
        ("score", {"$meta": "textScore"}),
        ("created_date", DESCENDING),
        ("_id", ASCENDING),
    ]).limit(limit)
    
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    
    return results


def get_recent_listings(town: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    # Get recent listing remarks
    db = get_db()
    query = {"town": town} if town else {}
    
    cursor = db.listing_remarks.find(query).sort("created_date", DESCENDING).limit(limit)
    
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    
    return results


# ========== USER PROFILES API ==========
def save_user_profile(profile_data: Dict[str, Any]) -> str:
    # Save a user profile
    db = get_db()
    profile_data = dict(profile_data)
    profile_data.setdefault("registration_date", datetime.utcnow())
    
    try:
        res = db.user_profiles.insert_one(profile_data)
        return str(res.inserted_id)
    except:
        # If email already exists, update instead
        db.user_profiles.update_one(
            {"email": profile_data["email"]},
            {"$set": profile_data}
        )
        return profile_data["email"]


def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    # Get user profile by ID or email
    db = get_db()
    
    try:
        doc = db.user_profiles.find_one({"_id": ObjectId(user_id)})
    except:
        doc = db.user_profiles.find_one({"email": user_id})
    
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def add_search_to_history(user_id: str, search_query: Dict[str, Any], results_count: int):
    # Add a search to user's search history
    db = get_db()
    
    search_entry = {
        "timestamp": datetime.utcnow(),
        "search_query": search_query,
        "results_count": results_count
    }
    
    db.user_profiles.update_one(
        {"email": user_id},
        {
            "$push": {
                "search_history": {
                    "$each": [search_entry],
                    "$slice": -20  # Keep last 20 searches
                }
            }
        }
    )


def save_listing_to_favorites(user_id: str, block: str, street: str, town: str):
    # Save a listing to user's favorites
    db = get_db()
    
    favorite = {
        "block": block,
        "street": street,
        "town": town,
        "saved_at": datetime.utcnow()
    }
    
    db.user_profiles.update_one(
        {"email": user_id},
        {"$addToSet": {"saved_listings": favorite}}
    )


def get_user_recommendations(user_id: str) -> List[str]:
    #Get town recommendations based on user preferences and search history
    db = get_db()
    
    user = db.user_profiles.find_one({"email": user_id})
    if not user:
        return []
    
    # Get preferred towns from profile
    preferred_towns = user.get("preferences", {}).get("preferred_towns", [])
    
    # Analyze search history for frequently searched towns
    search_history = user.get("search_history", [])
    searched_towns = [s.get("search_query", {}).get("town") for s in search_history if s.get("search_query", {}).get("town")]
    
    # Combine and deduplicate
    all_towns = list(set(preferred_towns + searched_towns))
    
    return all_towns[:5]  # Return top 5


# ========== TOWN METADATA API ==========
def get_town_metadata(town_name: str) -> Optional[Dict[str, Any]]:
    # Get metadata for a specific town
    db = get_db()
    doc = db.town_metadata.find_one({"town_name": town_name})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def get_all_town_metadata(region: Optional[str] = None, 
                          maturity: Optional[str] = None) -> List[Dict[str, Any]]:
    # Get all town metadata with optional filtering
    db = get_db()
    
    query = {}
    if region:
        query["region"] = region
    if maturity:
        query["maturity"] = maturity
    
    cursor = db.town_metadata.find(query).sort("town_name", ASCENDING)
    
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    
    return results


def search_towns_by_characteristics(characteristics: List[str]) -> List[Dict[str, Any]]:
    # Find towns with specific characteristics (tags)
    db = get_db()
    
    cursor = db.town_metadata.find({
        "characteristics": {"$in": characteristics}
    }).sort("town_name", ASCENDING)
    
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    
    return results


# ========== SCENARIO MANAGEMENT ==========
def save_scenario(doc: Dict[str, Any]) -> str:
    # Save an affordability scenario
    db = get_db()
    doc = dict(doc)
    doc.setdefault("created_at", datetime.utcnow())
    res = db.scenarios.insert_one(doc)
    return str(res.inserted_id)


def list_scenarios(user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    # List all saved scenarios, optionally filtered by user
    db = get_db()
    
    query = {"user_id": user_id} if user_id else {}
    cursor = db.scenarios.find(query).sort("created_at", DESCENDING).limit(limit)
    
    scenarios = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        scenarios.append(doc)
    
    return scenarios


def get_scenario(scenario_id: str) -> Optional[Dict[str, Any]]:
    # Get a single scenario by ID
    db = get_db()
    try:
        doc = db.scenarios.find_one({"_id": ObjectId(scenario_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except:
        return None


def delete_scenario(scenario_id: str) -> bool:
    # Delete a scenario by ID
    db = get_db()
    try:
        result = db.scenarios.delete_one({"_id": ObjectId(scenario_id)})
        return result.deleted_count > 0
    except:
        return False


# ========== ANALYTICS ==========
def get_popular_search_terms(limit: int = 10) -> List[Dict[str, Any]]:
    # Get most popular search terms from user search history
    db = get_db()
    
    pipeline = [
        {"$unwind": "$search_history"},
        {"$group": {
            "_id": {
                "town": "$search_history.search_query.town",
                "flat_type": "$search_history.search_query.flat_type"
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit}
    ]
    
    return list(db.user_profiles.aggregate(pipeline))


def get_listing_statistics() -> Dict[str, Any]:
    # Get statistics about listing remarks
    db = get_db()
    
    total = db.listing_remarks.count_documents({})
    
    by_town = list(db.listing_remarks.aggregate([
        {"$group": {"_id": "$town", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]))
    
    by_flat_type = list(db.listing_remarks.aggregate([
        {"$group": {"_id": "$flat_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]))
    
    return {
        "total_listings": total,
        "by_town": by_town,
        "by_flat_type": by_flat_type
    }


def check_database_health() -> bool:
    # Check if MongoDB database is accessible
    try:
        db = get_db()
        db.command("ping")
        return True
    except:
        return False