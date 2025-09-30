import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB  = os.getenv("MONGO_DB", "homefinder")

client = MongoClient(MONGO_URL)
db = client[MONGO_DB]

# Write a test doc
doc = {"type": "HEALTHCHECK", "note": "Hello from MongoDB!", "ok": True}
db.activity_logs.insert_one(doc)

# Read it back
print("Recent logs:")
for log in db.activity_logs.find().sort("_id", -1).limit(3):
    print(log)
