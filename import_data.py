# import_exact_data.py
"""
Import data EXACTLY as-is into MySQL
No modifications, just direct CSV to database table mapping
"""

import pandas as pd
import os
from sqlalchemy import text
from db_mysql import get_engine

def analyze_csv_structure(csv_path):
    """
    Analyze CSV structure and suggest data types
    Returns DataFrame info for review
    """
    print(f"📋 Analyzing: {csv_path}")
    df = pd.read_csv(csv_path, nrows=10)  # Read first 10 rows
    
    print(f"\n   Columns found: {len(df.columns)}")
    print(f"\n   Column Details:")
    print("   " + "-" * 80)
    
    for col in df.columns:
        dtype = str(df[col].dtype)
        sample = df[col].iloc[0] if len(df) > 0 else "N/A"
        # Truncate long samples
        if isinstance(sample, str) and len(sample) > 40:
            sample = sample[:37] + "..."
        print(f"   {col:30} | Type: {dtype:15} | Sample: {sample}")
    
    print("   " + "-" * 80)
    print(f"\n   Total rows in file: {len(pd.read_csv(csv_path)):,}")
    return df

def create_resale_table_exact():
    """
    Create table matching EXACT structure of your resale CSV
    Updated: block as VARCHAR since some blocks have letters (e.g., "406A")
    """
    engine = get_engine()
    
    print("\n📊 Creating resale_flat_prices table...")
    
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS resale_flat_prices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                month VARCHAR(10),
                town VARCHAR(50),
                flat_type VARCHAR(30),
                block VARCHAR(10),
                street_name VARCHAR(100),
                storey_range VARCHAR(20),
                floor_area_sqm INT,
                flat_model VARCHAR(50),
                lease_commence_date INT,
                remaining_lease VARCHAR(30),
                resale_price INT,
                INDEX idx_month (month),
                INDEX idx_town (town),
                INDEX idx_flat_type (flat_type),
                INDEX idx_price (resale_price)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
    
    print("   ✅ Table created: resale_flat_prices")
    print("   Capacity: 217,253 rows")

def create_property_table_exact():
    """
    Create table matching EXACT structure of your HDB property CSV
    Based on columns you showed:
    - blk_no, street, max_floor_lvl, year_completed, residential, commercial, 
      market_hawker, miscellaneous, multistorey_carpark, precinct_pavilion,
      bldg_contract_town, total_dwelling_units, 1room_sold, 2room_sold, etc.
    """
    engine = get_engine()
    
    print("\n📊 Creating hdb_property_information table...")
    
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hdb_property_information (
                id INT AUTO_INCREMENT PRIMARY KEY,
                blk_no VARCHAR(10),
                street VARCHAR(100),
                max_floor_lvl INT,
                year_completed INT,
                residential VARCHAR(1),
                commercial VARCHAR(1),
                market_hawker VARCHAR(1),
                miscellaneous VARCHAR(1),
                multistorey_carpark VARCHAR(1),
                precinct_pavilion VARCHAR(1),
                bldg_contract_town VARCHAR(10),
                total_dwelling_units INT,
                `1room_sold` INT,
                `2room_sold` INT,
                `3room_sold` INT,
                `4room_sold` INT,
                `5room_sold` INT,
                exec_sold INT,
                multigen_sold INT,
                studio_apartment_sold INT,
                `1room_rental` INT,
                `2room_rental` INT,
                `3room_rental` INT,
                other_room_rental INT,
                INDEX idx_blk_street (blk_no, street)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
    
    print("   ✅ Table created: hdb_property_information")

def create_income_table_exact():
    """
    Create table for household income data
    Based on your image: Dollar, ResidentHouseholds_Average, ResidentHouseholds_Median1, 
                        ResidentEmployedHouseholds_Average, ResidentEmployedHouseholds_Median1
    """
    engine = get_engine()
    
    print("\n📊 Creating household_income table...")
    
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS household_income (
                year INT PRIMARY KEY,
                resident_avg DECIMAL(10,2),
                resident_median DECIMAL(10,2),
                employed_avg DECIMAL(10,2),
                employed_median DECIMAL(10,2)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
    
    print("   ✅ Table created: household_income")

def create_expenditure_table_exact():
    """
    Create table for household expenditure data
    Based on your image: DataSeries (categories), 2023, 2018, 2013, 2008, 2003, 1998, 1993
    Structure: category name + values per year
    """
    engine = get_engine()
    
    print("\n📊 Creating household_expenditure table...")
    
    with engine.begin() as conn:
        # Create a normalized table for expenditure
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS household_expenditure (
                id INT AUTO_INCREMENT PRIMARY KEY,
                category VARCHAR(100),
                year_2023 DECIMAL(10,2),
                year_2018 DECIMAL(10,2),
                year_2013 DECIMAL(10,2),
                year_2008 DECIMAL(10,2),
                year_2003 DECIMAL(10,2),
                year_1998 DECIMAL(10,2),
                year_1993 DECIMAL(10,2),
                INDEX idx_category (category)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
    
    print("   ✅ Table created: household_expenditure")

def import_resale_prices_exact(csv_path="data/resale_flat_prices.csv"):
    """
    Import resale prices EXACTLY as-is from CSV
    No transformations, direct insert
    """
    print("\n" + "=" * 80)
    print("📥 IMPORTING RESALE FLAT PRICES (EXACT)")
    print("=" * 80)
    
    if not os.path.exists(csv_path):
        print(f"❌ File not found: {csv_path}")
        return False
    
    # Read CSV
    print(f"\n📂 Reading {csv_path}...")
    df = pd.read_csv(csv_path)
    print(f"   Rows: {len(df):,}")
    
    # Show columns
    print(f"\n   Columns in CSV:")
    for col in df.columns:
        print(f"      • {col}")
    
    # Create table
    create_resale_table_exact()
    
    # Import data in batches
    engine = get_engine()
    batch_size = 1000
    total_inserted = 0
    
    print(f"\n💾 Inserting data...")
    
    with engine.begin() as conn:
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            
            # Insert batch
            for _, row in batch.iterrows():
                try:
                    conn.execute(text("""
                        INSERT INTO resale_flat_prices 
                        (month, town, flat_type, block, street_name, storey_range, 
                         floor_area_sqm, flat_model, lease_commence_date, remaining_lease, resale_price)
                        VALUES (:month, :town, :flat_type, :block, :street_name, :storey_range,
                                :floor_area_sqm, :flat_model, :lease_commence_date, :remaining_lease, :resale_price)
                    """), {
                        "month": str(row['month']) if pd.notna(row['month']) else None,
                        "town": str(row['town']) if pd.notna(row['town']) else None,
                        "flat_type": str(row['flat_type']) if pd.notna(row['flat_type']) else None,
                        "block": str(row['block']) if pd.notna(row['block']) else None,
                        "street_name": str(row['street_name']) if pd.notna(row['street_name']) else None,
                        "storey_range": str(row['storey_range']) if pd.notna(row['storey_range']) else None,
                        "floor_area_sqm": int(row['floor_area_sqm']) if pd.notna(row['floor_area_sqm']) else None,
                        "flat_model": str(row['flat_model']) if pd.notna(row['flat_model']) else None,
                        "lease_commence_date": int(row['lease_commence_date']) if pd.notna(row['lease_commence_date']) else None,
                        "remaining_lease": str(row['remaining_lease']) if pd.notna(row['remaining_lease']) else None,
                        "resale_price": int(row['resale_price']) if pd.notna(row['resale_price']) else None
                    })
                    total_inserted += 1
                except Exception as e:
                    print(f"   ⚠️  Error on row {i}: {str(e)[:100]}")
            
            # Progress
            if (i + batch_size) % 10000 == 0:
                print(f"      Progress: {i + batch_size:,}/{len(df):,}")
    
    print(f"\n✅ Imported {total_inserted:,} rows")
    return True

def import_property_info_exact(csv_path="data/hdb_property_info.csv"):
    """
    Import HDB property info EXACTLY as-is
    """
    print("\n" + "=" * 80)
    print("📥 IMPORTING HDB PROPERTY INFORMATION (EXACT)")
    print("=" * 80)
    
    if not os.path.exists(csv_path):
        print(f"⚠️  File not found: {csv_path}")
        print("   Skipping (optional)")
        return False
    
    print(f"\n📂 Reading {csv_path}...")
    df = pd.read_csv(csv_path)
    print(f"   Rows: {len(df):,}")
    
    # Create table
    create_property_table_exact()
    
    # Import
    engine = get_engine()
    total_inserted = 0
    
    print(f"\n💾 Inserting data...")
    
    with engine.begin() as conn:
        for _, row in df.iterrows():
            try:
                conn.execute(text("""
                    INSERT INTO hdb_property_information 
                    (blk_no, street, max_floor_lvl, year_completed, residential, commercial,
                     market_hawker, miscellaneous, multistorey_carpark, precinct_pavilion,
                     bldg_contract_town, total_dwelling_units, `1room_sold`, `2room_sold`, 
                     `3room_sold`, `4room_sold`, `5room_sold`, exec_sold, multigen_sold,
                     studio_apartment_sold, `1room_rental`, `2room_rental`, `3room_rental`, 
                     other_room_rental)
                    VALUES (:blk_no, :street, :max_floor_lvl, :year_completed, :residential, :commercial,
                            :market_hawker, :miscellaneous, :multistorey_carpark, :precinct_pavilion,
                            :bldg_contract_town, :total_dwelling_units, :r1_sold, :r2_sold,
                            :r3_sold, :r4_sold, :r5_sold, :exec_sold, :multigen_sold,
                            :studio_sold, :r1_rental, :r2_rental, :r3_rental, :other_rental)
                """), {
                    "blk_no": str(row['blk_no']) if pd.notna(row['blk_no']) else None,
                    "street": str(row['street']) if pd.notna(row['street']) else None,
                    "max_floor_lvl": int(row['max_floor_lvl']) if pd.notna(row['max_floor_lvl']) else None,
                    "year_completed": int(row['year_completed']) if pd.notna(row['year_completed']) else None,
                    "residential": str(row['residential']) if pd.notna(row['residential']) else None,
                    "commercial": str(row['commercial']) if pd.notna(row['commercial']) else None,
                    "market_hawker": str(row['market_hawker']) if pd.notna(row['market_hawker']) else None,
                    "miscellaneous": str(row['miscellaneous']) if pd.notna(row['miscellaneous']) else None,
                    "multistorey_carpark": str(row['multistorey_carpark']) if pd.notna(row['multistorey_carpark']) else None,
                    "precinct_pavilion": str(row['precinct_pavilion']) if pd.notna(row['precinct_pavilion']) else None,
                    "bldg_contract_town": str(row['bldg_contract_town']) if pd.notna(row['bldg_contract_town']) else None,
                    "total_dwelling_units": int(row['total_dwelling_units']) if pd.notna(row['total_dwelling_units']) else None,
                    "r1_sold": int(row['1room_sold']) if pd.notna(row['1room_sold']) else None,
                    "r2_sold": int(row['2room_sold']) if pd.notna(row['2room_sold']) else None,
                    "r3_sold": int(row['3room_sold']) if pd.notna(row['3room_sold']) else None,
                    "r4_sold": int(row['4room_sold']) if pd.notna(row['4room_sold']) else None,
                    "r5_sold": int(row['5room_sold']) if pd.notna(row['5room_sold']) else None,
                    "exec_sold": int(row['exec_sold']) if pd.notna(row['exec_sold']) else None,
                    "multigen_sold": int(row['multigen_sold']) if pd.notna(row['multigen_sold']) else None,
                    "studio_sold": int(row['studio_apartment_sold']) if pd.notna(row['studio_apartment_sold']) else None,
                    "r1_rental": int(row['1room_rental']) if pd.notna(row['1room_rental']) else None,
                    "r2_rental": int(row['2room_rental']) if pd.notna(row['2room_rental']) else None,
                    "r3_rental": int(row['3room_rental']) if pd.notna(row['3room_rental']) else None,
                    "other_rental": int(row['other_room_rental']) if pd.notna(row['other_room_rental']) else None
                })
                total_inserted += 1
            except Exception as e:
                print(f"   ⚠️  Error: {str(e)[:100]}")
    
    print(f"\n✅ Imported {total_inserted:,} rows")
    return True

def import_income_exact(csv_path="data/household_income.csv"):
    """
    Import household income data exactly
    Expected CSV format based on your image:
    year, resident_avg, resident_median, employed_avg, employed_median
    """
    print("\n" + "=" * 80)
    print("📥 IMPORTING HOUSEHOLD INCOME (EXACT)")
    print("=" * 80)
    
    if not os.path.exists(csv_path):
        print(f"⚠️  File not found: {csv_path}")
        print("\n💡 Create this file with columns:")
        print("   year,resident_avg,resident_median,employed_avg,employed_median")
        print("   2000,1586,1125,1735,1236")
        print("   2001,1792,1250,1925,1352")
        print("   ... (data from your PDF)")
        return False
    
    df = pd.read_csv(csv_path)
    print(f"   Rows: {len(df):,}")
    print(f"   Years: {df['year'].min()} to {df['year'].max()}")
    
    create_income_table_exact()
    
    engine = get_engine()
    
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT INTO household_income 
                (year, resident_avg, resident_median, employed_avg, employed_median)
                VALUES (:year, :res_avg, :res_med, :emp_avg, :emp_med)
                ON DUPLICATE KEY UPDATE 
                    resident_avg = :res_avg,
                    resident_median = :res_med,
                    employed_avg = :emp_avg,
                    employed_median = :emp_med
            """), {
                "year": int(row['year']),
                "res_avg": float(row['resident_avg']) if pd.notna(row['resident_avg']) else None,
                "res_med": float(row['resident_median']) if pd.notna(row['resident_median']) else None,
                "emp_avg": float(row['employed_avg']) if pd.notna(row['employed_avg']) else None,
                "emp_med": float(row['employed_median']) if pd.notna(row['employed_median']) else None
            })
    
    print(f"✅ Imported {len(df)} years of income data")
    return True

def import_expenditure_exact(csv_path="data/household_expenditure.csv"):
    """
    Import household expenditure data exactly
    Expected CSV format based on your image (wide format with years as columns):
    category,year_2023,year_2018,year_2013,year_2008,year_2003,year_1998,year_1993
    Total,7118.7,6160.8,5815.3,4432.5,3797.8,3627.6,3033.4
    Food And Food Serving Services,1421.7,1203.9,1197.4,956.3,806.1,862.2,800.4
    ... etc
    """
    print("\n" + "=" * 80)
    print("📥 IMPORTING HOUSEHOLD EXPENDITURE (EXACT)")
    print("=" * 80)
    
    if not os.path.exists(csv_path):
        print(f"⚠️  File not found: {csv_path}")
        print("\n💡 Create this file with columns:")
        print("   category,year_2023,year_2018,year_2013,year_2008,year_2003,year_1998,year_1993")
        print("   Total,7118.7,6160.8,5815.3,4432.5,3797.8,3627.6,3033.4")
        print("   Food And Food Serving Services,1421.7,1203.9,1197.4,956.3,806.1,862.2,800.4")
        print("   ... (data from your PDF)")
        return False
    
    df = pd.read_csv(csv_path)
    print(f"   Rows: {len(df):,}")
    print(f"   Categories: {df['category'].tolist()[:5]}...")
    
    create_expenditure_table_exact()
    
    engine = get_engine()
    
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT INTO household_expenditure 
                (category, year_2023, year_2018, year_2013, year_2008, year_2003, year_1998, year_1993)
                VALUES (:category, :y2023, :y2018, :y2013, :y2008, :y2003, :y1998, :y1993)
                ON DUPLICATE KEY UPDATE 
                    year_2023 = :y2023,
                    year_2018 = :y2018,
                    year_2013 = :y2013,
                    year_2008 = :y2008,
                    year_2003 = :y2003,
                    year_1998 = :y1998,
                    year_1993 = :y1993
            """), {
                "category": str(row['category']),
                "y2023": float(row['year_2023']) if pd.notna(row['year_2023']) else None,
                "y2018": float(row['year_2018']) if pd.notna(row['year_2018']) else None,
                "y2013": float(row['year_2013']) if pd.notna(row['year_2013']) else None,
                "y2008": float(row['year_2008']) if pd.notna(row['year_2008']) else None,
                "y2003": float(row['year_2003']) if pd.notna(row['year_2003']) else None,
                "y1998": float(row['year_1998']) if pd.notna(row['year_1998']) else None,
                "y1993": float(row['year_1993']) if pd.notna(row['year_1993']) else None
            })
    
    print(f"✅ Imported {len(df)} expenditure categories")
    return True

def verify_imports():
    """Verify all imports"""
    print("\n" + "=" * 80)
    print("🔍 VERIFICATION")
    print("=" * 80)
    
    engine = get_engine()
    
    with engine.connect() as conn:
        tables = {
            "resale_flat_prices": "SELECT COUNT(*) FROM resale_flat_prices",
            "hdb_property_information": "SELECT COUNT(*) FROM hdb_property_information",
            "household_income": "SELECT COUNT(*) FROM household_income",
            "household_expenditure": "SELECT COUNT(*) FROM household_expenditure"
        }
        
        print("\n📊 Record Counts:")
        for table, query in tables.items():
            try:
                count = conn.execute(text(query)).scalar()
                print(f"   • {table:30} : {count:,} rows")
            except:
                print(f"   • {table:30} : Table not found")
        
        # Show sample from resale prices
        print("\n📋 Sample Resale Transaction:")
        try:
            result = conn.execute(text("""
                SELECT month, town, flat_type, resale_price 
                FROM resale_flat_prices 
                LIMIT 1
            """)).fetchone()
            if result:
                print(f"   {result[0]} | {result[1]} | {result[2]} | ${result[3]:,}")
        except:
            pass

def main():
    """Main import workflow"""
    print("=" * 80)
    print("HDB HOMEFINDER DB - EXACT DATA IMPORT")
    print("Data imported AS-IS with no modifications")
    print("=" * 80)
    
    # Show expected files
    print("\n📁 Expected files:")
    print("   • data/resale_flat_prices.csv       (Required)")
    print("   • data/hdb_property_info.csv        (Optional)")
    print("   • data/household_income.csv         (Optional)")
    print("   • data/household_expenditure.csv    (Optional)")
    
    # Check files
    print("\n🔍 Checking files...")
    files_found = []
    if os.path.exists("data/resale_flat_prices.csv"):
        print("   ✅ resale_flat_prices.csv")
        files_found.append("resale")
    else:
        print("   ❌ resale_flat_prices.csv (REQUIRED)")
    
    if os.path.exists("data/hdb_property_info.csv"):
        print("   ✅ hdb_property_info.csv")
        files_found.append("property")
    else:
        print("   ⚠️  hdb_property_info.csv (optional)")
    
    if os.path.exists("data/household_income.csv"):
        print("   ✅ household_income.csv")
        files_found.append("income")
    else:
        print("   ⚠️  household_income.csv (optional)")
    
    if os.path.exists("data/household_expenditure.csv"):
        print("   ✅ household_expenditure.csv")
        files_found.append("expenditure")
    else:
        print("   ⚠️  household_expenditure.csv (optional)")
    
    if "resale" not in files_found:
        print("\n❌ Missing required file: resale_flat_prices.csv")
        print("   Please export your Excel file to CSV and place in data/ folder")
        return
    
    print()
    proceed = input("Proceed with import? (yes/no): ").strip().lower()
    
    if proceed != 'yes':
        print("Import cancelled.")
        return
    
    # Import data
    if "resale" in files_found:
        import_resale_prices_exact()
    
    if "property" in files_found:
        import_property_info_exact()
    
    if "income" in files_found:
        import_income_exact()
    
    if "expenditure" in files_found:
        import_expenditure_exact()
    
    # Verify
    verify_imports()
    
    print("\n" + "=" * 80)
    print("🎉 IMPORT COMPLETE!")
    print("=" * 80)
    print("\nNext: python app.py")

if __name__ == "__main__":
    # Option to analyze before import
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--analyze":
        print("📊 ANALYZING CSV STRUCTURES")
        print("=" * 80)
        
        if os.path.exists("data/resale_flat_prices.csv"):
            analyze_csv_structure("data/resale_flat_prices.csv")
        
        if os.path.exists("data/hdb_property_info.csv"):
            analyze_csv_structure("data/hdb_property_info.csv")
    else:
        main()