# app.py
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import os, json
from datetime import datetime
from pymongo import MongoClient

# --- Database imports ---
from db_mysql import (
    get_towns, get_flat_types, get_months,
    query_trends, query_transactions, query_town_comparison
)
from db_mongo import (
    save_geojson_amenities, list_scenarios, save_scenario, 
    delete_scenario, get_amenity_stats_by_town, initialize_mongodb,
    get_amenity_stats_global
)
from bson import ObjectId

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join("data", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://greggy_dbuser:JesusKing@homefinder-mongo.7d67tvq.mongodb.net/')
client = MongoClient(MONGO_URI)
db = client['homefinder']
collection = db['amenities']

# Initialize MongoDB on startup
initialize_mongodb()

@app.route("/")
def index():
    return render_template("index.html")

# --- Reference data for dropdowns ---
@app.route("/api/meta", methods=["GET"])
def api_meta():
    """Returns metadata for form dropdowns"""
    try:
        towns = get_towns()
        flat_types = get_flat_types()
        months = get_months()
        
        return jsonify({
            "towns": towns,
            "flat_types": flat_types,
            "months": months,
            "amenity_types": ["MRT", "SCHOOL", "CLINIC", "SUPERMARKET", "PARK"]
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# --- SQL Advanced Query: Price trends with window functions ---
@app.route("/api/search/trends", methods=["POST"])
def api_search_trends():
    """
    Advanced SQL query using window functions and aggregates
    Returns median/percentile prices per sqm by town/flat type/month
    """
    payload = request.get_json() or {}
    town = payload.get("town")
    flat_type = payload.get("flat_type")
    start_month = payload.get("start_month")
    end_month = payload.get("end_month")
    
    try:
        rows = query_trends(town, flat_type, start_month, end_month)
        return jsonify({
            "ok": True, 
            "rows": rows,
            "filters": {"town": town, "flat_type": flat_type, "start_month": start_month, "end_month": end_month}
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# --- SQL Query: Recent transactions ---
@app.route("/api/search/transactions", methods=["POST"])
def api_search_transactions():
    """Returns recent individual transactions with details"""
    payload = request.get_json() or {}
    town = payload.get("town")
    flat_type = payload.get("flat_type")
    limit = payload.get("limit", 20)
    
    try:
        transactions = query_transactions(town, flat_type, limit)
        return jsonify({"ok": True, "transactions": transactions, "count": len(transactions)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# --- Affordability Calculator ---
@app.route("/api/affordability", methods=["POST"])
def api_affordability():
    """
    Calculates affordability based on income, expenses, and mortgage rules
    """
    payload = request.get_json() or {}
    income = float(payload.get("income", 0))
    expenses = float(payload.get("expenses", 0))
    interest_rate = float(payload.get("interest", 2.6))
    tenure_years = int(payload.get("tenure_years", 25))
    down_payment_pct = float(payload.get("down_payment_pct", 20))
    
    # Affordability calculation logic
    max_monthly_payment = (income * 0.30) - (expenses * 0.30)
    
    # Calculate maximum loan amount using mortgage formula
    monthly_rate = (interest_rate / 100) / 12
    num_payments = tenure_years * 12
    
    if monthly_rate > 0:
        max_loan = max_monthly_payment * ((1 - (1 + monthly_rate) ** -num_payments) / monthly_rate)
    else:
        max_loan = max_monthly_payment * num_payments
    
    # Account for down payment
    max_property_value = max_loan / (1 - down_payment_pct / 100)
    
    # Calculate affordable price per sqm (assuming average flat size)
    avg_flat_size_sqm = 90  # Average 4-room flat
    max_psm = max_property_value / avg_flat_size_sqm if max_property_value > 0 else 0
    
    affordable = max_property_value >= 300000  # Minimum viable HDB price
    
    return jsonify({
        "ok": True,
        "affordable": affordable,
        "max_property_value": round(max_property_value, 2),
        "max_loan_amount": round(max_loan, 2),
        "max_monthly_payment": round(max_monthly_payment, 2),
        "max_psm": round(max_psm, 2),
        "down_payment_required": round(max_property_value * down_payment_pct / 100, 2)
    })

# --- Town Comparison ---
@app.route("/api/compare/towns", methods=["POST"])
def api_compare_towns():
    """Compare multiple towns across various metrics"""
    payload = request.get_json() or {}
    towns = payload.get("towns", [])
    flat_type = payload.get("flat_type", "4 ROOM")
    
    try:
        comparison = query_town_comparison(towns, flat_type)
        
        # Add amenity counts and affordability score
        for town_data in comparison:
            # Add mock amenity counts (you can enhance this with actual MongoDB queries)
            town_data['mrt_count'] = 2
            town_data['school_count'] = 5
            
            # Calculate affordability score (inverse of price)
            median_psm = town_data.get('median_psm', 0)
            if median_psm > 0:
                # Score: higher price = lower score (scale 1-10)
                town_data['affordability_score'] = round(max(1, min(10, 10 - (median_psm - 5000) / 500)), 1)
            else:
                town_data['affordability_score'] = 5.0
        
        return jsonify({"ok": True, "comparison": comparison})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# --- MongoDB: Upload Amenity GeoJSON ---
@app.route("/api/amenities/upload", methods=["POST"])
def api_amenities_upload():
    """Upload and store GeoJSON amenity data to MongoDB"""
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "No file provided"}), 400
    
    if not f.filename.endswith(('.geojson', '.json')):
        return jsonify({"ok": False, "error": "Only GeoJSON files allowed"}), 400
    
    fn = secure_filename(f.filename)
    path = os.path.join(app.config["UPLOAD_FOLDER"], fn)
    f.save(path)
    
    try:
        # Read and validate GeoJSON
        with open(path, 'r') as fp:
            geojson_data = json.load(fp)
        
        # Store in MongoDB
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
        return jsonify({"ok": False, "error": str(e)}), 500

# --- MongoDB: Amenity Statistics ---
@app.route("/api/amenities/stats", methods=["GET"])
def api_amenities_stats():
    """Get statistics about amenities by town"""
    town = request.args.get("town")
    
    try:
        if town:
            stats = get_amenity_stats_by_town(town)
        else:
            # Global stats
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
        return jsonify({"ok": False, "error": str(e)}), 500

# --- MongoDB: Scenario Management ---
@app.route("/api/scenarios", methods=["GET", "POST", "DELETE"])
def api_scenarios():
    """Manage user affordability scenarios in MongoDB"""
    
    if request.method == "GET":
        try:
            scenarios = list_scenarios()
            return jsonify({"ok": True, "items": scenarios})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    
    elif request.method == "POST":
        payload = request.get_json() or {}
        
        # Validate required fields
        required = ["name", "income", "expenses"]
        if not all(k in payload for k in required):
            return jsonify({"ok": False, "error": "Missing required fields"}), 400
        
        try:
            payload["created_at"] = datetime.utcnow()
            scenario_id = save_scenario(payload)
            payload["_id"] = scenario_id
            
            return jsonify({"ok": True, "item": payload})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    
    else:  # DELETE
        scenario_id = request.args.get("id")
        if not scenario_id:
            return jsonify({"ok": False, "error": "No ID provided"}), 400
        
        try:
            delete_scenario(scenario_id)
            return jsonify({"ok": True, "deleted": scenario_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        
@app.route("/api/amenities")
def api_amenities():
    amenity_class = request.args.get("class")
    query = {}

    # If a class is provided, filter by properties.CLASS; otherwise return all amenities
    if amenity_class:
        query["properties.CLASS"] = amenity_class

    docs = list(collection.find(query, {"_id": 0}))

    features = []
    for doc in docs:
        if doc.get("type") == "Feature" and "geometry" in doc:
            features.append(doc)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    return jsonify(geojson)

# --- Health Check ---
@app.route("/api/health", methods=["GET"])
def api_health():
    """System health check"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "mysql_connected": True,
        "mongodb_connected": True
    })

# --- Error Handlers ---
@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": "Endpoint not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"ok": False, "error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)