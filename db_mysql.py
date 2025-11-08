# db_mysql.py
"""
MySQL Database Operations for HDB HomeFinder DB
Uses SQLAlchemy with PyMySQL driver for Aiven MySQL
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

# ========== DATABASE CONNECTION ==========
def get_engine():
    """Create SQLAlchemy engine with SSL for Aiven MySQL"""
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

# ========== READ OPERATIONS ==========

def get_towns():
    """Get all unique towns from resale data"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT town 
            FROM resale_flat_prices 
            WHERE town IS NOT NULL
            ORDER BY town
        """))
        return [row[0] for row in result]

def get_flat_types():
    """Get all unique flat types"""
    with engine.connect() as conn:
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
    """Get available transaction months"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT month 
            FROM resale_flat_prices 
            WHERE month IS NOT NULL
            ORDER BY month DESC
        """))
        return [row[0] for row in result]

def get_total_transaction_count():
    """Get total number of transactions in database"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) as total
            FROM resale_flat_prices
        """))
        row = result.fetchone()
        return row[0] if row else 0

# ========== ADVANCED QUERIES ==========

def query_trends(town, flat_type, start_month, end_month):
    """
    Advanced SQL query with window functions and aggregates
    Returns: median, avg, percentiles, counts by month
    """
    with engine.connect() as conn:
        # Using percentile approximation with row numbers
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
    """
    Get recent transactions with full details
    """
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                block,
                street_name as street,
                storey_range as storey,
                floor_area_sqm as floor_area,
                lease_commence_date as lease_start,
                remaining_lease,
                resale_price as price,
                month,
                ROUND(resale_price / floor_area_sqm, 0) as psm
            FROM resale_flat_prices
            WHERE town = :town 
              AND flat_type = :flat_type
              AND floor_area_sqm > 0
            ORDER BY month DESC, resale_price DESC
            LIMIT :limit
        """), {
            "town": town,
            "flat_type": flat_type,
            "limit": limit
        })
        
        return [dict(row._mapping) for row in result]

def query_town_comparison(towns, flat_type):
    """
    Compare multiple towns across various metrics
    """
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