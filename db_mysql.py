# MySQL Database Operations for HDB HomeFinder DB
# Uses SQLAlchemy with PyMySQL driver for Aiven MySQL

import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

# ========== DATABASE CONNECTION ==========
def get_engine():
    # Create SQLAlchemy engine with SSL for Aiven MySQL
    url = URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        database=os.getenv("MYSQL_DB"),
        query={
            "ssl_ca": os.getenv("MYSQL_SSL_CA"),
            "charset": "utf8mb4"
        }
    )
    return create_engine(url, pool_pre_ping=True, echo=False)

engine = get_engine()

# ========== METADATA QUERIES ==========

def get_towns():
    # Get all unique towns from resale data
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT town 
            FROM resale_flat_prices 
            WHERE town IS NOT NULL
            ORDER BY town
        """))
        return [row[0] for row in result]

def get_flat_types():
    # Get all flat types (prioritize from specifications table if available)
    with engine.connect() as conn:
        # Try to get from flat_type_specifications first
        try:
            result = conn.execute(text("""
                SELECT flat_type
                FROM flat_type_specifications
                ORDER BY typical_area_sqm_min
            """))
            types = [row[0] for row in result]
            if types:
                return types
        except:
            pass
        
        # Fallback to resale_flat_prices
        result = conn.execute(text("""
            SELECT DISTINCT flat_type 
            FROM resale_flat_prices 
            WHERE flat_type IS NOT NULL
            ORDER BY 
                CASE flat_type
                    WHEN '1 ROOM' THEN 1
                    WHEN '2 ROOM' THEN 2
                    WHEN '3 ROOM' THEN 3
                    WHEN '4 ROOM' THEN 4
                    WHEN '5 ROOM' THEN 5
                    WHEN 'EXECUTIVE' THEN 6
                    WHEN 'MULTI-GENERATION' THEN 7
                    ELSE 8
                END
        """))
        return [row[0] for row in result]

def get_months():
    # Get available transaction months
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT month 
            FROM resale_flat_prices 
            WHERE month IS NOT NULL
            ORDER BY month DESC
        """))
        return [row[0] for row in result]

def get_total_transaction_count():
    # Get total number of transactions in database
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) as total
            FROM resale_flat_prices
        """))
        row = result.fetchone()
        return row[0] if row else 0

# ========== FLAT TYPE SPECIFICATIONS ==========

def get_flat_type_specs(flat_type=None):
    # Get flat type specifications
    with engine.connect() as conn:
        if flat_type:
            result = conn.execute(text("""
                SELECT flat_type, typical_area_sqm_min, typical_area_sqm_max,
                       typical_bedrooms, typical_bathrooms, description
                FROM flat_type_specifications
                WHERE flat_type = :flat_type
            """), {"flat_type": flat_type})
            row = result.fetchone()
            if row:
                return {
                    "flat_type": row[0],
                    "area_min": row[1],
                    "area_max": row[2],
                    "bedrooms": row[3],
                    "bathrooms": row[4],
                    "description": row[5]
                }
            return None
        else:
            result = conn.execute(text("""
                SELECT flat_type, typical_area_sqm_min, typical_area_sqm_max,
                       typical_bedrooms, typical_bathrooms
                FROM flat_type_specifications
                ORDER BY typical_area_sqm_min
            """))
            return [dict(row._mapping) for row in result]

# ========== MORTGAGE & LOAN QUERIES ==========

def get_current_mortgage_rate():
    # Get the most recent mortgage rates
    with engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT year, quarter, hdb_concessionary_rate, cpf_oa_rate, bank_floating_rate
                FROM mortgage_interest_rates
                ORDER BY year DESC, quarter DESC
                LIMIT 1
            """))
            row = result.fetchone()
            if row:
                return {
                    "year": row[0],
                    "quarter": row[1],
                    "hdb_rate": float(row[2]),
                    "cpf_rate": float(row[3]),
                    "bank_rate": float(row[4])
                }
        except:
            pass
    
    # Fallback default
    return {"year": 2024, "quarter": 4, "hdb_rate": 2.6, "cpf_rate": 2.7, "bank_rate": 3.2}

def get_current_loan_rules():
    # Get the most current HDB loan eligibility rules
    with engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT effective_date, max_loan_to_value_pct, mortgage_servicing_ratio_pct,
                       income_ceiling_sgd, max_loan_tenure_years, min_occupation_period_years
                FROM hdb_loan_eligibility_rules
                ORDER BY effective_date DESC
                LIMIT 1
            """))
            row = result.fetchone()
            if row:
                return {
                    "effective_date": str(row[0]),
                    "max_ltv_pct": row[1],
                    "msr_pct": row[2],
                    "income_ceiling": row[3],
                    "max_tenure_years": row[4],
                    "mop_years": row[5]
                }
        except:
            pass
    
    # Fallback default
    return {
        "effective_date": "2024-01-01",
        "max_ltv_pct": 80,
        "msr_pct": 30,
        "income_ceiling": 21000,
        "max_tenure_years": 25,
        "mop_years": 5
    }

# ========== INCOME & EXPENDITURE ==========

def get_latest_household_income():
    # Get the most recent household income data
    with engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT year, resident_avg, resident_median, employed_avg, employed_median
                FROM household_income
                ORDER BY year DESC
                LIMIT 1
            """))
            row = result.fetchone()
            if row:
                return {
                    "year": row[0],
                    "resident_avg": float(row[1]) if row[1] else None,
                    "resident_median": float(row[2]) if row[2] else None,
                    "employed_avg": float(row[3]) if row[3] else None,
                    "employed_median": float(row[4]) if row[4] else None
                }
        except:
            pass
    
    return None

def get_household_expenditure_latest():
    #Get the most recent household expenditure breakdown
    with engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT category, year_2023
                FROM household_expenditure
                WHERE year_2023 IS NOT NULL
                ORDER BY 
                    CASE category 
                        WHEN 'Total' THEN 0
                        ELSE 1
                    END,
                    year_2023 DESC
            """))
            return [{"category": row[0], "amount": float(row[1])} for row in result]
        except:
            pass
    
    return []

# ========== ADVANCED RESALE QUERIES ==========

def query_trends(town, flat_type, start_month, end_month):
    # Advanced SQL query with window functions and aggregates
    # Returns median, avg, percentiles and counts by month

    with engine.connect() as conn:
        result = conn.execute(text("""
            WITH price_data AS (
                SELECT 
                    month,
                    resale_price,
                    floor_area_sqm,
                    ROUND(resale_price / floor_area_sqm, 2) as price_per_sqm
                FROM resale_flat_prices
                WHERE town = :town 
                  AND flat_type = :flat_type
                  AND month BETWEEN :start_month AND :end_month
                  AND floor_area_sqm > 0
            ),
            ranked_prices AS (
                SELECT 
                    month,
                    price_per_sqm,
                    resale_price,
                    ROW_NUMBER() OVER (PARTITION BY month ORDER BY price_per_sqm) as rn,
                    COUNT(*) OVER (PARTITION BY month) as total_count
                FROM price_data
            ),
            monthly_stats AS (
                SELECT 
                    month,
                    ROUND(AVG(price_per_sqm), 2) as avg_psm,
                    MIN(resale_price) as min_price,
                    MAX(resale_price) as max_price,
                    COUNT(*) as count
                FROM price_data
                GROUP BY month
            ),
            median_calc AS (
                SELECT 
                    month,
                    ROUND(AVG(price_per_sqm), 2) as median_psm
                FROM ranked_prices
                WHERE rn IN (FLOOR((total_count + 1) / 2), CEIL((total_count + 1) / 2))
                GROUP BY month
            )
            SELECT 
                ms.month,
                COALESCE(mc.median_psm, ms.avg_psm) as median_psm,
                ms.avg_psm,
                ms.count,
                ms.min_price,
                ms.max_price
            FROM monthly_stats ms
            LEFT JOIN median_calc mc ON ms.month = mc.month
            ORDER BY ms.month
        """), {
            "town": town,
            "flat_type": flat_type,
            "start_month": start_month,
            "end_month": end_month
        })
        
        return [dict(row._mapping) for row in result]

def query_transactions(town, flat_type, limit=20):
    # Get recent transactions with enhanced property information
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                r.block,
                r.street_name as street,
                r.storey_range as storey,
                r.floor_area_sqm as floor_area,
                r.lease_commence_date as lease_start,
                r.remaining_lease,
                r.resale_price as price,
                r.month,
                ROUND(r.resale_price / r.floor_area_sqm, 0) as psm,
                p.year_completed,
                p.total_dwelling_units
            FROM resale_flat_prices r
            LEFT JOIN hdb_property_information p 
                ON r.block = p.blk_no 
                AND r.street_name = p.street
            WHERE r.town = :town 
              AND r.flat_type = :flat_type
              AND r.floor_area_sqm > 0
            ORDER BY r.month DESC, r.resale_price DESC
            LIMIT :limit
        """), {
            "town": town,
            "flat_type": flat_type,
            "limit": limit
        })
        
        return [dict(row._mapping) for row in result]

def query_town_comparison(towns, flat_type):
    # Compare multiple towns across various metrics
    if not towns:
        return []
    
    with engine.connect() as conn:
        placeholders = ', '.join([f':town{i}' for i in range(len(towns))])
        params = {f'town{i}': town for i, town in enumerate(towns)}
        params['flat_type'] = flat_type
        
        query_str = f"""
            WITH price_data AS (
                SELECT 
                    town,
                    resale_price,
                    ROUND(resale_price / floor_area_sqm, 2) as price_per_sqm
                FROM resale_flat_prices
                WHERE town IN ({placeholders})
                  AND flat_type = :flat_type
                  AND floor_area_sqm > 0
                  AND month >= DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 12 MONTH), '%Y-%m')
            ),
            ranked AS (
                SELECT 
                    town,
                    price_per_sqm,
                    ROW_NUMBER() OVER (PARTITION BY town ORDER BY price_per_sqm) as rn,
                    COUNT(*) OVER (PARTITION BY town) as total_count
                FROM price_data
            )
            SELECT 
                pd.town,
                COUNT(*) as transactions,
                ROUND(AVG(r.price_per_sqm), 2) as median_psm,
                ROUND(AVG(pd.resale_price), 0) as avg_price,
                MIN(pd.resale_price) as min_price,
                MAX(pd.resale_price) as max_price
            FROM price_data pd
            LEFT JOIN ranked r ON pd.town = r.town 
                AND r.rn IN (FLOOR((r.total_count + 1) / 2), CEIL((r.total_count + 1) / 2))
            GROUP BY pd.town
            ORDER BY median_psm DESC
        """
        
        result = conn.execute(text(query_str), params)
        return [dict(row._mapping) for row in result]

# ========== AFFORDABILITY CALCULATION ==========

def calculate_affordability_enhanced(
    income,
    expenses,
    loan_type="hdb",
    use_current_rates=True,
    override_interest_rate=None,
    override_tenure_years=None,
    override_down_payment_pct=None,
):
    """
    Enhanced affordability calculation using actual database data.

    The caller can optionally override:
      - interest rate (percent per year)
      - loan tenure (years)
      - down payment percentage of property value

    If overrides are not supplied, we fall back to the latest rules/rates from MySQL.
    """
    # Get current loan rules
    rules = get_current_loan_rules()

    # Effective interest rate
    if override_interest_rate is not None:
        try:
            interest_rate = float(override_interest_rate)
        except (TypeError, ValueError):
            # Fallback to DB rate if parsing fails
            interest_rate = None
    else:
        interest_rate = None

    if interest_rate is None:
        if use_current_rates:
            rates = get_current_mortgage_rate()
            interest_rate = rates["hdb_rate"] if loan_type == "hdb" else rates["bank_rate"]
        else:
            # basic default
            interest_rate = 2.6

    # Get latest income data for context
    income_data = get_latest_household_income()

    # Check eligibility
    eligible_for_hdb_loan = income <= rules["income_ceiling"]

    # Calculate based on MSR (mortgage servicing ratio)
    max_msr_pct = rules["msr_pct"] / 100.0
    max_monthly_payment = (income * max_msr_pct) - (expenses * 0.30)

    # Loan calculation
    tenure_years = override_tenure_years or rules["max_tenure_years"]
    try:
        tenure_years = int(tenure_years)
    except (TypeError, ValueError):
        tenure_years = rules["max_tenure_years"]

    monthly_rate = (interest_rate / 100.0) / 12.0
    num_payments = tenure_years * 12

    if monthly_rate > 0:
        max_loan = max_monthly_payment * (
            (1 - (1 + monthly_rate) ** -num_payments) / monthly_rate
        )
    else:
        max_loan = max_monthly_payment * num_payments

    # Calculate max property value based on LTV / down payment
    # If user provides a down-payment percentage, use that; otherwise fall back to rules.
    if override_down_payment_pct is not None:
        try:
            dp_pct = float(override_down_payment_pct) / 100.0
        except (TypeError, ValueError):
            dp_pct = None
    else:
        dp_pct = None

    rule_ltv_pct = rules["max_ltv_pct"] / 100.0

    if dp_pct is not None:
        # User-chosen down payment -> implied LTV
        # Clamp to the rule-based maximum LTV so we do not exceed policy.
        ltv_pct = 1.0 - dp_pct
        if ltv_pct > rule_ltv_pct:
            ltv_pct = rule_ltv_pct
    else:
        ltv_pct = rule_ltv_pct

    # Guard against invalid LTV
    if ltv_pct <= 0 or ltv_pct > 1:
        ltv_pct = rule_ltv_pct

    max_property_value = max_loan / ltv_pct if ltv_pct > 0 else 0.0

    # Calculate PSM assuming a typical flat size
    avg_flat_size_sqm = 90.0
    max_psm = max_property_value / avg_flat_size_sqm if max_property_value > 0 else 0.0

    # Down payment
    down_payment_required = max_property_value * (1.0 - ltv_pct)

    # Affordability (simple rule-of-thumb threshold)
    affordable = max_property_value >= 300000

    # Income comparison
    median_income_comparison = None
    if income_data and income_data.get("resident_median"):
        try:
            median_income_comparison = round(
                (income / income_data["resident_median"]) * 100.0, 1
            )
        except ZeroDivisionError:
            median_income_comparison = None

    return {
        "ok": True,
        "affordable": affordable,
        "max_property_value": round(max_property_value, 2),
        "max_loan_amount": round(max_loan, 2),
        "max_monthly_payment": round(max_monthly_payment, 2),
        "max_psm": round(max_psm, 2),
        "down_payment_required": round(down_payment_required, 2),
        "interest_rate": float(interest_rate),
        "loan_tenure_years": tenure_years,
        "msr_used_pct": rules["msr_pct"],
        "ltv_used_pct": rules["max_ltv_pct"],
        "eligible_for_hdb_loan": eligible_for_hdb_loan,
        "income_ceiling": rules["income_ceiling"],
        "median_income_comparison": median_income_comparison,
    }

# ========== MARKET STATISTICS ==========

def get_market_statistics():
    # Get overall market statistics
    with engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_transactions,
                    COUNT(DISTINCT town) as total_towns,
                    COUNT(DISTINCT flat_type) as total_flat_types,
                    MIN(month) as earliest_month,
                    MAX(month) as latest_month,
                    ROUND(AVG(resale_price), 0) as avg_price,
                    ROUND(AVG(resale_price / floor_area_sqm), 2) as avg_psm
                FROM resale_flat_prices
                WHERE floor_area_sqm > 0
            """))
            
            row = result.fetchone()
            if row:
                return dict(row._mapping)
        except:
            pass
    
    return {}

# Add these functions to your existing db_mysql.py file

# ========== USER MANAGEMENT FUNCTIONS ==========

def get_user_by_email(email):
    # Get user by email
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT user_id, email, full_name, is_admin, is_active, created_at, last_login
            FROM users
            WHERE email = :email
        """), {"email": email})
        
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return None

def get_user_by_id(user_id):
    # Get user by ID
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT user_id, email, full_name, is_admin, is_active, created_at, last_login
            FROM users
            WHERE user_id = :user_id
        """), {"user_id": user_id})
        
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return None

def get_user_preferences(user_id):
    # Get user preferences from MySQL
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT *
            FROM user_preferences
            WHERE user_id = :user_id
        """), {"user_id": user_id})
        
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return None

def save_user_preferences(user_id, preferences):
    # Save user preferences to MySQL
    import json
    
    with engine.connect() as conn:
        # Check if preferences exist
        existing = get_user_preferences(user_id)
        
        if existing:
            # Update existing
            conn.execute(text("""
                UPDATE user_preferences
                SET preferred_towns = :preferred_towns,
                    preferred_flat_types = :preferred_flat_types,
                    budget_min = :budget_min,
                    budget_max = :budget_max,
                    email_notifications = :email_notifications
                WHERE user_id = :user_id
            """), {
                "user_id": user_id,
                "preferred_towns": json.dumps(preferences.get("preferred_towns", [])),
                "preferred_flat_types": json.dumps(preferences.get("preferred_flat_types", [])),
                "budget_min": preferences.get("budget_min"),
                "budget_max": preferences.get("budget_max"),
                "email_notifications": preferences.get("email_notifications", True)
            })
        else:
            # Insert new
            conn.execute(text("""
                INSERT INTO user_preferences 
                (user_id, preferred_towns, preferred_flat_types, budget_min, budget_max, email_notifications)
                VALUES (:user_id, :preferred_towns, :preferred_flat_types, :budget_min, :budget_max, :email_notifications)
            """), {
                "user_id": user_id,
                "preferred_towns": json.dumps(preferences.get("preferred_towns", [])),
                "preferred_flat_types": json.dumps(preferences.get("preferred_flat_types", [])),
                "budget_min": preferences.get("budget_min"),
                "budget_max": preferences.get("budget_max"),
                "email_notifications": preferences.get("email_notifications", True)
            })
        
        conn.commit()
        return True

def get_user_login_history(user_id, limit=10):
    # Get user's login history
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT log_id, login_timestamp, ip_address, login_successful, failure_reason
            FROM login_logs
            WHERE user_id = :user_id
            ORDER BY login_timestamp DESC
            LIMIT :limit
        """), {"user_id": user_id, "limit": limit})
        
        return [dict(row._mapping) for row in result]

def get_user_activity_stats(user_id, days=30):
    # Get user's activity statistics
    with engine.connect() as conn:
        result = conn.execute(text("""
            CALL sp_get_user_activity_summary(:user_id, :days)
        """), {"user_id": user_id, "days": days})
        
        return [dict(row._mapping) for row in result]

# ========== ADMIN ANALYTICS FUNCTIONS ==========

def get_system_statistics():
    # Get overall system statistics (admin only)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                (SELECT COUNT(*) FROM users) as total_users,
                (SELECT COUNT(*) FROM users WHERE is_active = TRUE) as active_users,
                (SELECT COUNT(*) FROM users WHERE is_admin = TRUE) as admin_users,
                (SELECT COUNT(*) FROM login_logs WHERE login_successful = TRUE 
                 AND login_timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)) as logins_24h,
                (SELECT COUNT(DISTINCT user_id) FROM user_activity 
                 WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)) as active_users_7d,
                (SELECT COUNT(*) FROM user_activity) as total_activities,
                (SELECT COUNT(*) FROM resale_flat_prices) as total_transactions
        """))
        
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return {}

def get_popular_towns(limit=10):
    # Get most popular towns based on user searches
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                JSON_EXTRACT(activity_data, '$.town') as town,
                COUNT(*) as search_count
            FROM user_activity
            WHERE activity_type = 'search'
              AND JSON_EXTRACT(activity_data, '$.town') IS NOT NULL
              AND timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            GROUP BY JSON_EXTRACT(activity_data, '$.town')
            ORDER BY search_count DESC
            LIMIT :limit
        """), {"limit": limit})
        
        return [dict(row._mapping) for row in result]

def get_popular_flat_types(limit=10):
    # Get most popular flat types based on user searches
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                JSON_EXTRACT(activity_data, '$.flat_type') as flat_type,
                COUNT(*) as search_count
            FROM user_activity
            WHERE activity_type = 'search'
              AND JSON_EXTRACT(activity_data, '$.flat_type') IS NOT NULL
              AND timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            GROUP BY JSON_EXTRACT(activity_data, '$.flat_type')
            ORDER BY search_count DESC
            LIMIT :limit
        """), {"limit": limit})
        
        return [dict(row._mapping) for row in result]

def get_recent_user_registrations(days=7):
    # Get recent user registrations
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                DATE(created_at) as registration_date,
                COUNT(*) as new_users
            FROM users
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
            GROUP BY DATE(created_at)
            ORDER BY registration_date DESC
        """), {"days": days})
        
        return [dict(row._mapping) for row in result]