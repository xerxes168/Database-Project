import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from pymongo import MongoClient

# ---------- Load env ----------
load_dotenv()

HOST = os.getenv("MYSQL_HOST")
PORT = os.getenv("MYSQL_PORT")
USER = os.getenv("MYSQL_USER")
PWD  = os.getenv("MYSQL_PASSWORD")
DB   = os.getenv("MYSQL_DB", "defaultdb")
SSL_CA = os.getenv("MYSQL_SSL_CA")  # e.g., ./ca.pem

if not all([HOST, PORT, USER, PWD, DB, SSL_CA]):
    print("❌ Missing one or more required env vars: "
          "MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB, MYSQL_SSL_CA")
    sys.exit(1)


mongo_client = MongoClient(os.getenv("MONGO_URL"))
mongo_db = mongo_client[os.getenv("MONGO_DB", "homefinder")]

# ---------- Build SQLAlchemy URL ----------
# Aiven requires SSL; we pass CA via query string for pymysql
url = URL.create(
    drivername="mysql+pymysql",
    username=USER,
    password=PWD,
    host=HOST,
    port=int(PORT),
    database=DB,
    query={"ssl_ca": SSL_CA, "charset": "utf8mb4"}
)

# Engine with health checks
engine = create_engine(url, pool_pre_ping=True, future=True)

def mask(s: str, keep=4):
    if s is None: return ""
    return s[:keep] + "…" if len(s) > keep else s

def main():
    print("🔌 Connecting to Aiven MySQL…")
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  User: {USER}")
    print(f"  DB:   {DB}")
    print(f"  SSL:  {SSL_CA}")

    # 1) Simple connectivity check
    with engine.connect() as conn:
        one = conn.execute(text("SELECT 1 AS ok")).scalar_one()
        print(f"✅ SELECT 1 → {one}")

    # 2) Create a tiny healthcheck table
    with engine.begin() as conn:  # begin() auto-commits/rolls back
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS healthcheck (
                id INT AUTO_INCREMENT PRIMARY KEY,
                note VARCHAR(255) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        print("🧱 Ensured table 'healthcheck' exists.")

    # 3) Insert a row
    note = f"hello from main.py at {datetime.utcnow().isoformat()}Z"
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO healthcheck (note) VALUES (:note)"), {"note": note})
        print("✍️  Inserted a healthcheck row.")

    # 4) Read back the last few rows
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, note, created_at
            FROM healthcheck
            ORDER BY id DESC
            LIMIT 3
        """)).mappings().all()

    print("🔎 Recent healthcheck rows:")
    for r in rows:
        print(f"  - id={r['id']}, created_at={r['created_at']}, note={r['note']}")

    print("\n🎉 Success! main.py can talk to your Aiven MySQL over SSL.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("💥 Error while talking to MySQL:")
        print(f"   {type(e).__name__}: {e}")
        sys.exit(2)
