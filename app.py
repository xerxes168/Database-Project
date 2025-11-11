# app.py
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
import os, json
from datetime import datetime
from pymongo import MongoClient

# Database imports
from db_mysql import (
    get_towns, get_flat_types, get_months,
    query_trends, query_transactions, query_town_comparison,
    get_total_transaction_count, get_flat_type_specs,
    get_current_mortgage_rate, get_current_loan_rules,
    get_latest_household_income, get_household_expenditure_latest,
    calculate_affordability_enhanced, get_market_statistics
)
from db_mongo import (
    # Amenities
    save_geojson_amenities, get_amenity_stats_global, get_amenity_stats_by_town,
    # Listing Remarks
    save_listing_remark, search_listing_remarks, get_recent_listings,
    # User Profiles
    save_user_profile, get_user_profile, add_search_to_history, 
    save_listing_to_favorites, get_user_recommendations,
    # Town Metadata
    get_town_metadata, get_all_town_metadata, search_towns_by_characteristics,
    # Scenarios
    save_scenario, list_scenarios, get_scenario, delete_scenario,
    # Analytics
    get_popular_search_terms, get_listing_statistics,
    # Init
    initialize_mongodb
)
from bson import ObjectId

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config["UPLOAD_FOLDER"] = os.path.join("data", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://greggy_dbuser:JesusKing@homefinder-mongo.7d67tvq.mongodb.net/')
client = MongoClient(MONGO_URI)
db = client['homefinder']
collection = db['amenities']

# Initialize MongoDB on startup
try:
    initialize_mongodb()
    print("✓ MongoDB initialized successfully")
except Exception as e:
    print(f"✗ MongoDB initialization warning: {e}")

# Session management - simple demo user
DEMO_USER_EMAIL = "demo@hdbhomefinder.sg"


@app.route("/")
def index():
    return render_template("index.html")


# ==================== METADATA ====================
@app.route("/api/meta", methods=["GET"])
def api_meta():
    """Returns metadata for form dropdowns."""
    try:
        towns = get_towns()
        flat_types = get_flat_types()
        months = get_months()
        total_transactions = get_total_transaction_count()
        mortgage_rate = get_current_mortgage_rate()
        loan_rules = get_current_loan_rules()
        market_stats = get_market_statistics()
        
        return jsonify({
            "towns": towns,
            "flat_types": flat_types,
            "months": months,
            "total_transactions": total_transactions,
            "amenity_types": ["MRT_STATION", "SCHOOL", "CLINIC", "SUPERMARKET", "PARK"],
            "current_mortgage_rate": mortgage_rate,
            "current_loan_rules": loan_rules,
            "market_statistics": market_stats
        })
    except Exception as e:
        print(f"Error in /api/meta: {e}")
        return jsonify({
            "ok": False, 
            "error": str(e),
            "towns": [],
            "flat_types": [],
            "months": [],
            "total_transactions": 0
        }), 500


# ==================== SQL QUERIES ====================
@app.route("/api/search/trends", methods=["POST"])
def api_search_trends():
    """Advanced SQL query with window functions - Price trends analysis."""
    payload = request.get_json() or {}
    town = payload.get("town")
    flat_type = payload.get("flat_type")
    start_month = payload.get("start_month")
    end_month = payload.get("end_month")
    
    try:
        rows = query_trends(town, flat_type, start_month, end_month)
        
        # Track search in user history
        try:
            user_email = session.get("user_email", DEMO_USER_EMAIL)
            add_search_to_history(user_email, {
                "town": town,
                "flat_type": flat_type,
                "type": "trends"
            }, len(rows))
        except Exception as e:
            print(f"Warning: Could not track search history: {e}")
        
        return jsonify({
            "ok": True, 
            "rows": rows,
            "filters": {"town": town, "flat_type": flat_type, "start_month": start_month, "end_month": end_month}
        })
    except Exception as e:
        print(f"Error in /api/search/trends: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/search/transactions", methods=["POST"])
def api_search_transactions():
    """Get recent transactions with details."""
    payload = request.get_json() or {}
    town = payload.get("town")
    flat_type = payload.get("flat_type")
    limit = payload.get("limit", 20)
    
    try:
        transactions = query_transactions(town, flat_type, limit)
        
        # Track search
        try:
            user_email = session.get("user_email", DEMO_USER_EMAIL)
            add_search_to_history(user_email, {
                "town": town,
                "flat_type": flat_type,
                "type": "transactions"
            }, len(transactions))
        except Exception as e:
            print(f"Warning: Could not track search history: {e}")
        
        return jsonify({"ok": True, "transactions": transactions, "count": len(transactions)})
    except Exception as e:
        print(f"Error in /api/search/transactions: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/compare/towns", methods=["POST"])
def api_compare_towns():
    """Compare multiple towns with integrated data."""
    payload = request.get_json() or {}
    towns_list = payload.get("towns", [])
    flat_type = payload.get("flat_type")

    
    try:
        # Get SQL comparison data
        comparison = query_town_comparison(towns_list, flat_type)

        # Get income data for affordability context
        income_data = get_latest_household_income()
        
        # Enrich with MongoDB town metadata (homefinder.town_metadata)
        for town_data in comparison:
            town_name = town_data["town"]
            
            # Add town metadata
            try:
                metadata = get_town_metadata(town_name)
                if metadata:
                    town_data["region"] = metadata.get("region", "Unknown")
                    town_data["maturity"] = metadata.get("maturity", "Unknown")
                    town_data["characteristics"] = metadata.get("characteristics", [])
                    town_data["description"] = metadata.get("description", "")
                    # Optional geometry/center data for map highlighting
                    center = metadata.get("center") or metadata.get("centroid")
                    if isinstance(center, dict):
                        town_data["center_lat"] = center.get("lat") or center.get("latitude")
                        town_data["center_lng"] = center.get("lng") or center.get("longitude")
                    elif isinstance(center, (list, tuple)) and len(center) == 2:
                        # Assume [lng, lat] ordering
                        town_data["center_lat"], town_data["center_lng"] = center[1], center[0]
                    geometry = metadata.get("geometry") or metadata.get("boundary")
                    # Only attach if geometry looks like a GeoJSON object
                    if isinstance(geometry, dict) and "type" in geometry:
                        town_data["geometry"] = geometry
                else:
                    town_data["region"] = "Unknown"
                    town_data["maturity"] = "Unknown"
                    town_data["characteristics"] = []
            except Exception as e:
                print(f"Warning: Could not fetch metadata for {town_name}: {e}")
                town_data["region"] = "Unknown"
                town_data["maturity"] = "Unknown"
                town_data["characteristics"] = []
            
            # Calculate affordability score based on income
            median_psm = town_data.get('median_psm', 0)
            avg_price = town_data.get('avg_price', 0)

            if median_psm > 0 and income_data and income_data.get('resident_median'):
                # Convert to float to avoid Decimal type issues
                monthly_income = float(income_data['resident_median'])
                median_psm_float = float(median_psm)
                
                # Assume 90sqm flat
                estimated_flat_price = median_psm_float * 90
                
                # Affordability = income / (price/300) ratio, scaled to 10
                affordability_ratio = (monthly_income * 300) / estimated_flat_price if estimated_flat_price > 0 else 0
                town_data['affordability_score'] = round(min(10, max(1, affordability_ratio * 3)), 1)
            else:
                town_data['affordability_score'] = 5.0
            
            # Mock amenity counts (can be enhanced with actual queries)
            town_data['mrt_count'] = 2
            town_data['school_count'] = 5
        
        return jsonify({
            "ok": True, 
            "comparison": comparison
        })
    except Exception as e:
        print(f"Error in /api/compare/towns: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ==================== AFFORDABILITY ====================
@app.route("/api/affordability", methods=["POST"])
def api_affordability():
    """Calculate affordability with enhanced mortgage rules and rates"""
    payload = request.get_json() or {}
    
    try:
        income = float(payload.get("income", 0))
        expenses = float(payload.get("expenses", 0))
        loan_type = payload.get("loan_type", "hdb")  # "hdb" or "bank"
        
        # Use enhanced calculation from db_mysql
        result = calculate_affordability_enhanced(
            income=income,
            expenses=expenses,
            loan_type=loan_type,
            use_current_rates=True
        )
        
        # Get expenditure data for context
        expenditure_data = get_household_expenditure_latest()
        housing_expense = next((e for e in expenditure_data if "Housing" in e["category"]), None)
        
        # Add context
        result["housing_expense_avg"] = housing_expense["amount"] if housing_expense else None
        result["loan_type"] = loan_type
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in /api/affordability: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/affordability/context", methods=["GET"])
def api_affordability_context():
    """Get context data for affordability calculator"""
    try:
        current_rate = get_current_mortgage_rate()
        loan_rules = get_current_loan_rules()
        income_data = get_latest_household_income()
        expenditure_data = get_household_expenditure_latest()
        
        return jsonify({
            "ok": True,
            "current_rates": current_rate,
            "loan_rules": loan_rules,
            "income_data": income_data,
            "expenditure_breakdown": expenditure_data[:10]
        })
    except Exception as e:
        print(f"Error in /api/affordability/context: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/flat-specs", methods=["GET"])
def api_flat_specs():
    """Get flat type specifications"""
    flat_type = request.args.get("flat_type")
    
    try:
        if flat_type:
            specs = get_flat_type_specs(flat_type)
            if specs:
                return jsonify({"ok": True, "specs": specs})
            else:
                return jsonify({"ok": False, "error": "Flat type not found"}), 404
        else:
            all_specs = get_flat_type_specs()
            return jsonify({"ok": True, "specs": all_specs})
    except Exception as e:
        print(f"Error in /api/flat-specs: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ==================== AMENITIES (MongoDB GeoJSON) ====================
@app.route("/api/amenities")
def api_amenities():
    """Get amenities GeoJSON for map display."""
    amenity_class = request.args.get("class")
    query = {}

    if amenity_class:
        query["properties.CLASS"] = amenity_class

    try:
        docs = list(collection.find(query, {"_id": 0}).limit(1000))

        features = []
        for doc in docs:
            if doc.get("type") == "Feature" and "geometry" in doc:
                features.append(doc)

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        return jsonify(geojson)
    except Exception as e:
        print(f"Error in /api/amenities: {e}")
        return jsonify({
            "type": "FeatureCollection",
            "features": []
        })


@app.route("/api/amenities/upload", methods=["POST"])
def api_amenities_upload():
    """Upload and store GeoJSON amenity data."""
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "No file provided"}), 400
    
    if not f.filename.endswith(('.geojson', '.json')):
        return jsonify({"ok": False, "error": "Only GeoJSON files allowed"}), 400
    
    fn = secure_filename(f.filename)
    path = os.path.join(app.config["UPLOAD_FOLDER"], fn)
    f.save(path)
    
    try:
        with open(path, 'r') as fp:
            geojson_data = json.load(fp)
        
        features = geojson_data.get('features', [])
        result = save_geojson_amenities(features)
        
        return jsonify({
            "ok": True, 
            "filename": fn,
            "feature_count": len(features),
            "upserted": result.get("upserts", 0),
            "modified": result.get("modified", 0),
            "uploaded_at": datetime.utcnow().isoformat()
        })
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "Invalid JSON format"}), 400
    except Exception as e:
        print(f"Error in /api/amenities/upload: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/amenities/stats", methods=["GET"])
def api_amenities_stats():
    """Get amenity statistics."""
    town = request.args.get("town")
    
    try:
        if town:
            stats = get_amenity_stats_by_town(town)
        else:
            global_stats = get_amenity_stats_global()
            stats = {
                "town": "ALL",
                "total_amenities": sum(s.get("count", 0) for s in global_stats)
            }
            for s in global_stats:
                key = s.get("amenity_type", "other").lower() + "_count"
                stats[key] = s.get("count", 0)
        
        return jsonify({"ok": True, "stats": stats})
    except Exception as e:
        print(f"Error in /api/amenities/stats: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ==================== LISTING REMARKS (MongoDB TEXT SEARCH) ====================
@app.route("/api/listings/search", methods=["POST"])
def api_listings_search():
    """
    Full-text search on listing remarks.
    Demonstrates MongoDB text indexing and search capabilities.
    """
    payload = request.get_json() or {}
    query = payload.get("query", "")
    town = payload.get("town")
    flat_type = payload.get("flat_type")
    limit = payload.get("limit", 20)
    
    try:
        if not query:
            # If no search query, get recent listings
            results = get_recent_listings(town, limit)
        else:
            # Full-text search
            results = search_listing_remarks(query, town, flat_type, limit)
        
        return jsonify({
            "ok": True,
            "results": results,
            "count": len(results),
            "query": query
        })
    except Exception as e:
        print(f"Error in /api/listings/search: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/listings/recent", methods=["GET"])
def api_listings_recent():
    """Get recent listing remarks."""
    town = request.args.get("town")
    limit = int(request.args.get("limit", 10))
    
    try:
        results = get_recent_listings(town, limit)
        return jsonify({"ok": True, "results": results, "count": len(results)})
    except Exception as e:
        print(f"Error in /api/listings/recent: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ==================== TOWN METADATA ====================
@app.route("/api/towns/metadata", methods=["GET"])
def api_towns_metadata():
    """Get town metadata with optional filtering."""
    region = request.args.get("region")
    maturity = request.args.get("maturity")
    
    try:
        metadata = get_all_town_metadata(region, maturity)
        return jsonify({"ok": True, "towns": metadata, "count": len(metadata)})
    except Exception as e:
        print(f"Error in /api/towns/metadata: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/towns/<town_name>/metadata", methods=["GET"])
def api_town_metadata_detail(town_name):
    """Get detailed metadata for a specific town."""
    try:
        metadata = get_town_metadata(town_name)
        if metadata:
            return jsonify({"ok": True, "metadata": metadata})
        else:
            return jsonify({"ok": False, "error": "Town not found"}), 404
    except Exception as e:
        print(f"Error in /api/towns/{town_name}/metadata: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/towns/search-by-characteristics", methods=["POST"])
def api_towns_search_characteristics():
    """Search towns by characteristics/tags."""
    payload = request.get_json() or {}
    characteristics = payload.get("characteristics", [])
    
    try:
        towns = search_towns_by_characteristics(characteristics)
        return jsonify({"ok": True, "towns": towns, "count": len(towns)})
    except Exception as e:
        print(f"Error in /api/towns/search-by-characteristics: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ==================== USER PROFILES & RECOMMENDATIONS ====================
@app.route("/api/user/profile", methods=["GET", "POST"])
def api_user_profile():
    """Get or create user profile."""
    if request.method == "GET":
        user_email = session.get("user_email", DEMO_USER_EMAIL)
        try:
            profile = get_user_profile(user_email)
            if not profile:
                return jsonify({"ok": False, "error": "Profile not found"}), 404
            return jsonify({"ok": True, "profile": profile})
        except Exception as e:
            print(f"Error in GET /api/user/profile: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    
    else:  # POST
        payload = request.get_json() or {}
        try:
            profile_id = save_user_profile(payload)
            session["user_email"] = payload.get("email", DEMO_USER_EMAIL)
            return jsonify({"ok": True, "profile_id": profile_id})
        except Exception as e:
            print(f"Error in POST /api/user/profile: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/user/favorites", methods=["POST"])
def api_user_add_favorite():
    """Add listing to user favorites."""
    payload = request.get_json() or {}
    user_email = session.get("user_email", DEMO_USER_EMAIL)
    
    try:
        save_listing_to_favorites(
            user_email,
            payload.get("block"),
            payload.get("street"),
            payload.get("town")
        )
        return jsonify({"ok": True, "message": "Added to favorites"})
    except Exception as e:
        print(f"Error in /api/user/favorites: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/user/recommendations", methods=["GET"])
def api_user_recommendations():
    """Get personalized town recommendations."""
    user_email = session.get("user_email", DEMO_USER_EMAIL)
    
    try:
        recommendations = get_user_recommendations(user_email)
        return jsonify({"ok": True, "recommended_towns": recommendations})
    except Exception as e:
        print(f"Error in /api/user/recommendations: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ==================== SCENARIOS (MongoDB) ====================
@app.route("/api/scenarios", methods=["GET", "POST", "DELETE"])
def api_scenarios():
    """Manage affordability scenarios in MongoDB."""
    
    if request.method == "GET":
        user_email = request.args.get("user_id", session.get("user_email"))
        try:
            scenarios = list_scenarios(user_email)
            return jsonify({"ok": True, "items": scenarios})
        except Exception as e:
            print(f"Error in GET /api/scenarios: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    
    elif request.method == "POST":
        payload = request.get_json() or {}
        required = ["name", "income", "expenses"]
        if not all(k in payload for k in required):
            return jsonify({"ok": False, "error": "Missing required fields"}), 400
        
        try:
            payload["created_at"] = datetime.utcnow()
            payload["user_id"] = session.get("user_email", DEMO_USER_EMAIL)
            scenario_id = save_scenario(payload)
            payload["_id"] = scenario_id
            
            return jsonify({"ok": True, "item": payload})
        except Exception as e:
            print(f"Error in POST /api/scenarios: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    
    else:  # DELETE
        scenario_id = request.args.get("id")
        if not scenario_id:
            return jsonify({"ok": False, "error": "No ID provided"}), 400
        
        try:
            delete_scenario(scenario_id)
            return jsonify({"ok": True, "deleted": scenario_id})
        except Exception as e:
            print(f"Error in DELETE /api/scenarios: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500


# ==================== ANALYTICS & INSIGHTS ====================
@app.route("/api/analytics/popular-searches", methods=["GET"])
def api_analytics_popular_searches():
    """Get popular search terms from user history."""
    limit = int(request.args.get("limit", 10))
    
    try:
        results = get_popular_search_terms(limit)
        return jsonify({"ok": True, "popular_searches": results})
    except Exception as e:
        print(f"Error in /api/analytics/popular-searches: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/analytics/listings", methods=["GET"])
def api_analytics_listings():
    """Get listing statistics."""
    try:
        stats = get_listing_statistics()
        return jsonify({"ok": True, "statistics": stats})
    except Exception as e:
        print(f"Error in /api/analytics/listings: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ==================== HEALTH CHECK ====================
@app.route("/api/health", methods=["GET"])
def api_health():
    """System health check."""
    mysql_ok = False
    mongo_ok = False
    
    try:
        get_towns()
        mysql_ok = True
    except:
        pass
    
    try:
        from db_mongo import check_database_health
        mongo_ok = check_database_health()
    except:
        pass
    
    return jsonify({
        "status": "healthy" if (mysql_ok and mongo_ok) else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "mysql_connected": mysql_ok,
        "mongodb_connected": mongo_ok
    })


@app.route("/api/debug/town-metadata", methods=["GET"])
def api_debug_town_metadata():
    """Debug endpoint to check town metadata structure."""
    town_name = request.args.get("town", "ANG MO KIO")
    
    try:
        metadata = get_town_metadata(town_name)
        
        if not metadata:
            return jsonify({
                "ok": False,
                "error": f"No metadata found for {town_name}",
                "suggestion": "Check if town_metadata collection has this town"
            })
        
        # Check required fields
        has_boundary = "boundary" in metadata
        has_geometry = "geometry" in metadata
        has_center = "center_lat" in metadata and "center_lng" in metadata
        
        return jsonify({
            "ok": True,
            "town_name": town_name,
            "has_boundary": has_boundary,
            "has_geometry": has_geometry,
            "has_center": has_center,
            "metadata_keys": list(metadata.keys()),
            "sample_data": {
                "town": metadata.get("town"),
                "region": metadata.get("region"),
                "center_lat": metadata.get("center_lat"),
                "center_lng": metadata.get("center_lng"),
                "boundary_type": (
                    metadata.get("boundary", {}).get("type")
                    if has_boundary and isinstance(metadata.get("boundary"), dict)
                    else None
                ),
                "geometry_type": (
                    metadata.get("geometry", {}).get("type")
                    if has_geometry and isinstance(metadata.get("geometry"), dict)
                    else None
                )
            }
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"ok": False, "error": "Internal server error"}), 500


if __name__ == "__main__":
    print("🚀 Starting HDB HomeFinder DB...")
    print(f"📍 Server running on http://0.0.0.0:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)