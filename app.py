# app.py
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import os, json
from datetime import datetime
from pymongo import MongoClient
from functools import wraps

# Database imports
from db_mysql import (
    get_towns, get_flat_types, get_months,
    query_trends, query_transactions, query_town_comparison,
    get_total_transaction_count, get_flat_type_specs,
    get_current_mortgage_rate, get_current_loan_rules,
    get_latest_household_income, get_household_expenditure_latest,
    calculate_affordability_enhanced, get_market_statistics,
    # NEW: Auth-related imports
    get_user_by_id, get_user_preferences, save_user_preferences,
    get_user_login_history, get_user_activity_stats,
    get_system_statistics, get_popular_towns, get_popular_flat_types,
    get_recent_user_registrations
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

# NEW: Authentication imports
from auth import (
    login_manager, bcrypt,
    register_user, authenticate_user, log_user_activity,
    admin_required, change_password,
    get_all_users, get_activity_summary, toggle_user_active_status
)

from bson import ObjectId

# ========== FLASK APP INITIALIZATION ==========
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config["UPLOAD_FOLDER"] = os.path.join("data", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Initialize Flask-Login
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Initialize Flask-Bcrypt
bcrypt.init_app(app)

# MongoDB connection
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

# ==================== PUBLIC ROUTES ====================

@app.route("/")
def index():
    """Home page - accessible to all"""
    if current_user.is_authenticated:
        return render_template("index.html", user=current_user)
    return render_template("index.html")

@app.route("/login")
def login_page():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template("login.html")

@app.route("/register")
def register_page():
    """Registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template("register.html")

# ==================== AUTHENTICATION API ====================

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    """User registration endpoint"""
    data = request.get_json() or {}
    
    email = data.get("email", "").strip()
    password = data.get("password", "")
    full_name = data.get("full_name", "").strip()
    
    if not email or not password or not full_name:
        return jsonify({"ok": False, "error": "All fields are required"}), 400
    
    success, result = register_user(email, password, full_name)
    
    if success:
        return jsonify({
            "ok": True, 
            "message": "Registration successful! Please log in.",
            "user_id": result
        })
    else:
        return jsonify({"ok": False, "error": result}), 400

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """User login endpoint"""
    data = request.get_json() or {}
    
    email = data.get("email", "").strip()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"ok": False, "error": "Email and password required"}), 400
    
    # Get client info
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')[:255]
    
    success, result = authenticate_user(email, password, ip_address, user_agent)
    
    if success:
        user = result
        login_user(user, remember=True)
        
        return jsonify({
            "ok": True,
            "message": "Login successful",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "is_admin": user.is_admin
            }
        })
    else:
        return jsonify({"ok": False, "error": result}), 401

@app.route("/api/auth/logout", methods=["POST"])
@login_required
def api_logout():
    """User logout endpoint"""
    logout_user()
    return jsonify({"ok": True, "message": "Logged out successfully"})

@app.route("/api/auth/me", methods=["GET"])
def api_current_user():
    """
    Get current user info or return unauthenticated status
    This endpoint works for both authenticated and unauthenticated users
    """
    if current_user.is_authenticated:
        # User is logged in
        return jsonify({
            "ok": True,
            "authenticated": True,
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "full_name": current_user.full_name,
                "is_admin": current_user.is_admin,
                "is_active": current_user.is_active
            }
        }), 200
    else:
        # User is not authenticated
        return jsonify({
            "ok": False,
            "authenticated": False,
            "user": None
        }), 401
    
# ========== ADDITIONAL HELPER FUNCTION FOR PROTECTED API ROUTES ==========

def require_auth(f):
    """
    Decorator to require authentication for API endpoints
    Returns 401 if user is not authenticated
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                "ok": False,
                "error": "Authentication required",
                "authenticated": False
            }), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route("/api/auth/change-password", methods=["POST"])
@login_required
def api_change_password():
    """Change user password"""
    data = request.get_json() or {}
    
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    
    if not old_password or not new_password:
        return jsonify({"ok": False, "error": "Both passwords required"}), 400
    
    success, message = change_password(current_user.id, old_password, new_password)
    
    if success:
        return jsonify({"ok": True, "message": message})
    else:
        return jsonify({"ok": False, "error": message}), 400

# ==================== USER PROFILE & PREFERENCES ====================

@app.route("/api/user/profile", methods=["GET"])
@login_required
def api_get_user_profile():
    """Get user profile and preferences"""
    try:
        # Get MySQL user data
        user_data = get_user_by_id(current_user.id)
        
        # Get MySQL preferences
        preferences = get_user_preferences(current_user.id) or {}
        
        # Get MongoDB profile
        mongo_profile = get_user_profile(current_user.email) or {}
        
        return jsonify({
            "ok": True,
            "profile": {
                **user_data,
                "preferences": preferences,
                "search_history": mongo_profile.get("search_history", [])[-10:],  # Last 10
                "saved_listings": mongo_profile.get("saved_listings", [])
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/user/preferences", methods=["POST"])
@login_required
def api_save_user_preferences():
    """Save user preferences"""
    try:
        data = request.get_json() or {}
        
        # Save to MySQL
        save_user_preferences(current_user.id, data)
        
        # Also update MongoDB profile
        mongo_profile = get_user_profile(current_user.email) or {}
        mongo_profile["preferences"] = data
        save_user_profile(mongo_profile)
        
        return jsonify({"ok": True, "message": "Preferences saved"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/user/activity", methods=["GET"])
@login_required
def api_get_user_activity():
    """Get user activity history"""
    try:
        days = int(request.args.get("days", 30))
        
        activity_stats = get_user_activity_stats(current_user.id, days)
        login_history = get_user_login_history(current_user.id, 10)
        
        return jsonify({
            "ok": True,
            "activity_stats": activity_stats,
            "login_history": login_history
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ==================== METADATA (AUTH-AWARE) ====================

@app.route("/api/meta", methods=["GET"])
def api_meta():
    """Returns metadata for form dropdowns - accessible to all but logs if authenticated"""
    try:
        towns = get_towns()
        flat_types = get_flat_types()
        months = get_months()
        total_transactions = get_total_transaction_count()
        mortgage_rate = get_current_mortgage_rate()
        loan_rules = get_current_loan_rules()
        market_stats = get_market_statistics()
        
        # Log activity if user is authenticated
        if current_user.is_authenticated:
            log_user_activity(current_user.id, 'view_amenities', {"action": "get_metadata"})
        
        return jsonify({
            "towns": towns,
            "flat_types": flat_types,
            "months": months,
            "total_transactions": total_transactions,
            "amenity_types": ["MRT_STATION", "SCHOOL", "CLINIC", "SUPERMARKET", "PARK"],
            "current_mortgage_rate": mortgage_rate,
            "current_loan_rules": loan_rules,
            "market_statistics": market_stats,
            "authenticated": current_user.is_authenticated,
            "user": {
                "full_name": current_user.full_name if current_user.is_authenticated else None,
                "is_admin": current_user.is_admin if current_user.is_authenticated else False
            }
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

# ==================== SQL QUERIES (WITH ACTIVITY LOGGING) ====================

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
        
        # Log activity if authenticated
        if current_user.is_authenticated:
            log_user_activity(current_user.id, 'search', {
                "town": town,
                "flat_type": flat_type,
                "type": "trends"
            })
            add_search_to_history(current_user.email, {
                "town": town,
                "flat_type": flat_type,
                "type": "trends"
            }, len(rows))
        
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
        
        # Log activity ONLY if user is authenticated
        if current_user.is_authenticated:  # ← ADD THIS CHECK
            log_user_activity(current_user.id, 'search', {
                "town": town,
                "flat_type": flat_type,
                "type": "transactions"
            })
            
            add_search_to_history(current_user.email, {
                "town": town,
                "flat_type": flat_type,
                "type": "transactions"
            }, len(transactions))
        
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
        comparison = query_town_comparison(towns_list, flat_type)
        income_data = get_latest_household_income()
        
        # Enrich with MongoDB town metadata
        for town_data in comparison:
            town_name = town_data["town"]
            
            try:
                metadata = get_town_metadata(town_name)
                if metadata:
                    town_data["region"] = metadata.get("region", "Unknown")
                    town_data["maturity"] = metadata.get("maturity", "Unknown")
                    town_data["characteristics"] = metadata.get("characteristics", [])
                    town_data["description"] = metadata.get("description", "")
                    
                    center = metadata.get("center") or metadata.get("centroid")
                    if isinstance(center, dict):
                        town_data["center_lat"] = center.get("lat") or center.get("latitude")
                        town_data["center_lng"] = center.get("lng") or center.get("longitude")
                    elif isinstance(center, (list, tuple)) and len(center) == 2:
                        town_data["center_lat"], town_data["center_lng"] = center[1], center[0]
                    
                    geometry = metadata.get("geometry") or metadata.get("boundary")
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
            
            # Calculate affordability score
            median_psm = town_data.get('median_psm', 0)
            if median_psm > 0 and income_data and income_data.get('resident_median'):
                monthly_income = float(income_data['resident_median'])
                median_psm_float = float(median_psm)
                estimated_flat_price = median_psm_float * 90
                affordability_ratio = (monthly_income * 300) / estimated_flat_price if estimated_flat_price > 0 else 0
                town_data['affordability_score'] = round(min(10, max(1, affordability_ratio * 3)), 1)
            else:
                town_data['affordability_score'] = 5.0
            
            town_data['mrt_count'] = 2
            town_data['school_count'] = 5
        
        # Log activity (only if logged in)
        if current_user.is_authenticated:
            log_user_activity(current_user.id, 'comparison', {
                "towns": towns_list,
                "flat_type": flat_type
            })
        
        return jsonify({
            "ok": True, 
            "comparison": comparison
        })
    except Exception as e:
        print(f"Error in /api/compare/towns: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ==================== AFFORDABILITY (WITH LOGGING) ====================

@app.route("/api/affordability", methods=["POST"])
@require_auth 
def api_affordability():
    """
    Calculate affordability with enhanced mortgage rules and rates
    RESTRICTED: Only authenticated users can access this
    """
    payload = request.get_json() or {}
    
    try:
        income = float(payload.get("income", 0))
        expenses = float(payload.get("expenses", 0))
        loan_type = payload.get("loan_type", "hdb")
        
        result = calculate_affordability_enhanced(
            income=income,
            expenses=expenses,
            loan_type=loan_type,
            use_current_rates=True
        )
        
        # Log activity (user is guaranteed to be authenticated)
        log_user_activity(current_user.id, 'affordability_calc', {
            "income": income,
            "expenses": expenses,
            "affordable": result.get("affordable")
        })
        
        expenditure_data = get_household_expenditure_latest()
        housing_expense = next((e for e in expenditure_data if "Housing" in e["category"]), None)
        
        result["housing_expense_avg"] = housing_expense["amount"] if housing_expense else None
        result["loan_type"] = loan_type
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in /api/affordability: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/affordability/context", methods=["GET"])
@require_auth 
def api_affordability_context():
    """
    Get context data for affordability calculator
    RESTRICTED: Only authenticated users can access this
    """
    try:
        current_rate = get_current_mortgage_rate()
        loan_rules = get_current_loan_rules()
        income_data = get_latest_household_income()
        expenditure_data = get_household_expenditure_latest()
        
        # Log access
        log_user_activity(current_user.id, 'affordability_context', {
            "action": "view_context"
        })
        
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

# ==================== AMENITIES (WITH LOGGING) ====================

@app.route("/api/amenities")
def api_amenities():
    """Get amenities GeoJSON for map display."""
    amenity_class = request.args.get("class")
    query = {}

    if amenity_class:
        query["properties.CLASS"] = amenity_class

    try:
        docs = list(collection.find(query, {"_id": 0}).limit(1000))
        features = [doc for doc in docs if doc.get("type") == "Feature" and "geometry" in doc]
        
        # Log if authenticated
        if current_user.is_authenticated:
            log_user_activity(current_user.id, 'view_amenities', {"class": amenity_class})
        
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

# ==================== LISTING REMARKS SEARCH ====================

@app.route("/api/listings/search", methods=["POST"])
def api_listings_search():
    """Full-text search on listing remarks."""
    payload = request.get_json() or {}
    query = payload.get("query", "")
    town = payload.get("town")
    flat_type = payload.get("flat_type")
    limit = payload.get("limit", 20)
    
    try:
        if not query:
            results = get_recent_listings(town, limit)
        else:
            results = search_listing_remarks(query, town, flat_type, limit)
        
        # Log activity (only if logged in)
        if current_user.is_authenticated:
            log_user_activity(current_user.id, 'search', {
                "query": query,
                "town": town,
                "flat_type": flat_type,
                "type": "listings"
            })
        
        return jsonify({
            "ok": True,
            "results": results,
            "count": len(results),
            "query": query
        })
    except Exception as e:
        print(f"Error in /api/listings/search: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/user/favorites", methods=["POST"])
@login_required
def api_user_add_favorite():
    """Add listing to user favorites."""
    payload = request.get_json() or {}
    
    try:
        save_listing_to_favorites(
            current_user.email,
            payload.get("block"),
            payload.get("street"),
            payload.get("town")
        )
        
        # Log activity
        log_user_activity(current_user.id, 'save_favorite', {
            "town": payload.get("town"),
            "block": payload.get("block")
        })
        
        return jsonify({"ok": True, "message": "Added to favorites"})
    except Exception as e:
        print(f"Error in /api/user/favorites: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ==================== SCENARIOS ====================

@app.route("/api/scenarios", methods=["GET", "POST", "DELETE"])
def api_scenarios():
    """
    Manage affordability scenarios
    
    GET: List scenarios for current user (auth required)
    POST: Create scenario (auth required)
    DELETE: Delete scenario (auth required)
    """
    
    # RESTRICT ALL OPERATIONS TO AUTHENTICATED USERS
    if not current_user.is_authenticated:
        return jsonify({
            "ok": False,
            "error": "Authentication required to manage scenarios",
            "authenticated": False
        }), 401
    
    if request.method == "GET":
        try:
            user_email = current_user.email
            scenarios = list_scenarios(user_email)
            
            # Log activity
            log_user_activity(current_user.id, 'view_scenarios', {
                "count": len(scenarios)
            })
            
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
            payload["user_id"] = current_user.email
            payload["is_guest"] = False
            
            scenario_id = save_scenario(payload)
            payload["_id"] = scenario_id
            
            # Log activity
            log_user_activity(current_user.id, 'create_scenario', {
                "scenario_id": scenario_id,
                "name": payload.get("name")
            })
            
            return jsonify({"ok": True, "item": payload})
        except Exception as e:
            print(f"Error in POST /api/scenarios: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    
    else:  # DELETE
        scenario_id = request.args.get("id")
        if not scenario_id:
            return jsonify({"ok": False, "error": "No ID provided"}), 400
        
        try:
            # Verify ownership before deleting
            scenario = get_scenario(scenario_id)
            if not scenario:
                return jsonify({"ok": False, "error": "Scenario not found"}), 404
            
            if scenario.get("user_id") != current_user.email:
                return jsonify({"ok": False, "error": "Unauthorized"}), 403
            
            delete_scenario(scenario_id)
            
            # Log activity
            log_user_activity(current_user.id, 'delete_scenario', {
                "scenario_id": scenario_id
            })
            
            return jsonify({"ok": True, "deleted": scenario_id})
        except Exception as e:
            print(f"Error in DELETE /api/scenarios: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500


# ==================== ADMIN ROUTES ====================

@app.route("/admin")
@login_required
def admin_dashboard():
    """Admin dashboard page"""
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    return render_template("admin.html", user=current_user)

@app.route("/api/admin/stats", methods=["GET"])
@admin_required
def api_admin_stats():
    """Get system statistics (admin only)"""
    try:
        system_stats = get_system_statistics()
        popular_towns = get_popular_towns(10)
        popular_flat_types = get_popular_flat_types(10)
        recent_registrations = get_recent_user_registrations(30)
        
        return jsonify({
            "ok": True,
            "system_stats": system_stats,
            "popular_towns": popular_towns,
            "popular_flat_types": popular_flat_types,
            "recent_registrations": recent_registrations
        })
    except Exception as e:
        print(f"Error in /api/admin/stats: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def api_admin_users():
    """Get all users (admin only)"""
    try:
        users = get_all_users()
        return jsonify({"ok": True, "users": users})
    except Exception as e:
        print(f"Error in /api/admin/users: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/admin/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def api_admin_toggle_user(user_id):
    """Activate/deactivate user (admin only)"""
    try:
        data = request.get_json() or {}
        is_active = data.get("is_active", True)
        
        success, message = toggle_user_active_status(user_id, is_active)
        
        if success:
            return jsonify({"ok": True, "message": message})
        else:
            return jsonify({"ok": False, "error": message}), 400
    except Exception as e:
        print(f"Error in /api/admin/users/{user_id}/toggle: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/admin/activity", methods=["GET"])
@admin_required
def api_admin_activity():
    """Get activity summary (admin only)"""
    try:
        activity = get_activity_summary()
        return jsonify({"ok": True, "activity": activity})
    except Exception as e:
        print(f"Error in /api/admin/activity: {e}")
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
        "mongodb_connected": mongo_ok,
        "authenticated_users": 1 if current_user.is_authenticated else 0
    })

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": "Endpoint not found"}), 404

@app.errorhandler(401)
def unauthorized(e):
    return jsonify({"ok": False, "error": "Unauthorized - login required"}), 401

@app.errorhandler(403)
def forbidden(e):
    return jsonify({"ok": False, "error": "Forbidden - insufficient permissions"}), 403

@app.errorhandler(500)
def server_error(e):
    return jsonify({"ok": False, "error": "Internal server error"}), 500

# ==================== STARTUP ====================

if __name__ == "__main__":
    print("🚀 Starting HDB HomeFinder DB with Authentication...")
    print(f"📍 Server running on http://0.0.0.0:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)