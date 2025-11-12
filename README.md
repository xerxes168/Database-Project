# HDB HomeFinder DB

A comprehensive database application for exploring Singapore's HDB resale market with integrated MySQL and MongoDB databases.

## 🏗️ Architecture

- **Backend**: Flask REST API
- **Frontend**: Vanilla JavaScript with Tailwind CSS
- **Databases**: 
  - MySQL (via Aiven) - Structured resale transaction data
  - MongoDB (Atlas) - Flexible GeoJSON amenity data & scenarios
- **Features**:
  - Advanced SQL queries with window functions
  - NoSQL GeoJSON storage with geospatial indexing
  - Real-time affordability calculator
  - Town comparison analytics
  - Interactive data visualizations

## 📋 Prerequisites

- Python 3.8+
- MySQL database (Aiven or local)
- MongoDB database (Atlas or local)
- CSV data files for resale prices

## 🚀 Setup Instructions

### 1. Clone and Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
# MySQL Configuration (Aiven)
MYSQL_HOST=your-mysql-host.aivencloud.com
MYSQL_PORT=12345
MYSQL_USER=avnadmin
MYSQL_PASSWORD=your-password
MYSQL_DB=homefinder
MYSQL_SSL_CA=/path/to/ca.pem

# MongoDB Configuration (Atlas)
MONGO_URL=mongodb+srv://username:password@cluster.mongodb.net/
MONGO_DB=homefinder
```

### 3. Prepare Data Files

Place your CSV files in the `data/` directory:

```
data/
├── resale_flat_prices.csv          (Required)
├── hdb_property_info.csv           (Optional)
├── household_income.csv            (Optional)
├── household_expenditure.csv       (Optional)
└── geojson/                        (Optional - for amenities)
    ├── MRTStations.geojson
    ├── Schools.geojson
    └── CHASClinics.geojson
```

### 4. Import Data

#### Import MySQL Data (Resale Prices)

```bash
# Analyze CSV structure first (optional)
python import_data.py --analyze

# Import all data
python import_data.py
```

This will:
- Create MySQL tables
- Import resale flat prices (217,253 records)
- Import property information (optional)
- Import income/expenditure data (optional)

#### Import MongoDB Data (Amenities)

```bash
# Import all GeoJSON files from a directory
python import_geojson_data.py --dir ./data/geojson

# Or import a single file
python import_geojson_data.py --file ./data/geojson/MRTStations.geojson

# Verify imports
python import_geojson_data.py --verify
```

### 5. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

## 📊 Database Schema

### MySQL Tables

#### `resale_flat_prices`
Primary table containing all HDB resale transactions:
- `id` (INT, PRIMARY KEY)
- `month` (VARCHAR) - Transaction month (YYYY-MM)
- `town` (VARCHAR) - HDB town name
- `flat_type` (VARCHAR) - e.g., "4 ROOM", "5 ROOM"
- `block` (VARCHAR) - Block number
- `street_name` (VARCHAR)
- `storey_range` (VARCHAR) - e.g., "10 TO 12"
- `floor_area_sqm` (INT)
- `flat_model` (VARCHAR)
- `lease_commence_date` (INT)
- `remaining_lease` (VARCHAR)
- `resale_price` (INT)

Indexes on: `month`, `town`, `flat_type`, `resale_price`

#### `hdb_property_information` (Optional)
Building-level information with room mix and facilities

#### `household_income` (Optional)
Historical median household income by year

#### `household_expenditure` (Optional)
Household expenditure patterns by category

### MongoDB Collections

#### `amenities`
GeoJSON Point features for amenities:
```json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [103.8198, 1.3521]
  },
  "properties": {
    "amenity_type": "MRT",
    "name": "ANG MO KIO",
    "loaded_at": "2025-01-15T10:30:00Z"
  },
  "amenity_key": "unique_hash"
}
```

Indexes: 2dsphere on `geometry`, unique on `amenity_key`

#### `scenarios`
Saved affordability calculations:
```json
{
  "_id": ObjectId("..."),
  "name": "Young Couple Budget",
  "income": 7500,
  "expenses": 2000,
  "interest": 2.6,
  "tenure_years": 25,
  "created_at": "2025-01-15T10:30:00Z"
}
```

## 🔍 Key Features

### 1. Advanced SQL Queries
- **Window Functions**: Median price calculation using `ROW_NUMBER()` and `PARTITION BY`
- **Aggregates**: Monthly statistics with `AVG()`, `MIN()`, `MAX()`, `COUNT()`
- **Trend Analysis**: Price per sqm trends over time

### 2. NoSQL Geospatial Queries
- **2dsphere Index**: Fast proximity searches for amenities
- **Flexible Schema**: Store varying GeoJSON properties
- **Upsert Operations**: Idempotent data imports

### 3. Affordability Calculator
- 30% income threshold rule
- Mortgage payment calculations
- Down payment considerations
- Save scenarios to MongoDB

### 4. Town Comparison
- Multi-town analysis
- Median vs average pricing
- Transaction volume comparison
- Amenity proximity scores

## 🎨 UI Features

- **Dark Theme**: Modern zinc color palette
- **Responsive Design**: Mobile-friendly layout
- **Interactive Charts**: Chart.js visualizations
- **Tab Navigation**: Multiple feature panels
- **Real-time Updates**: Dynamic data loading

## 🐛 Troubleshooting

### MySQL Connection Issues

1. Check SSL certificate path in `.env`
2. Verify firewall allows connection to Aiven
3. Test connection:
```python
from db_mysql import get_engine
engine = get_engine()
with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    print("Connected!")
```

### MongoDB Connection Issues

1. Whitelist your IP in MongoDB Atlas
2. Verify connection string format
3. Test connection:
```python
from db_mongo import get_db
db = get_db()
print(db.list_collection_names())
```

### Data Import Errors

1. **Block number errors**: Ensure `block` column is VARCHAR (some blocks have letters like "406A")
2. **Missing columns**: Check CSV column names match exactly
3. **Memory issues**: Import in batches if dataset is large

### Frontend Issues

1. **Charts not rendering**: Check Chart.js CDN is loaded
2. **No data in dropdowns**: Check `/api/meta` endpoint returns data
3. **CORS errors**: Add `flask-cors` if accessing from different domain

## 📝 API Endpoints

### Metadata
- `GET /api/meta` - Get towns, flat types, months

### Search & Analysis
- `POST /api/search/trends` - Get price trends with SQL window functions
- `POST /api/search/transactions` - Get recent transactions
- `POST /api/compare/towns` - Compare multiple towns

### Affordability
- `POST /api/affordability` - Calculate affordability
- `GET /api/scenarios` - List saved scenarios
- `POST /api/scenarios` - Save new scenario
- `DELETE /api/scenarios?id=...` - Delete scenario

### Amenities
- `POST /api/amenities/upload` - Upload GeoJSON file
- `GET /api/amenities/stats?town=...` - Get amenity statistics

### Health
- `GET /api/health` - System health check

## 🔐 Security Notes

- Never commit `.env` file
- Use environment variables for all credentials
- SSL required for production MySQL connections
- Validate all user inputs on server side

## 📦 Project Structure

```
hdb-homefinder-db/
├── app.py                      # Flask application
├── db_mysql.py                 # MySQL operations
├── db_mongo.py                 # MongoDB operations
├── import_data.py              # MySQL data import script
├── import_geojson_data.py      # MongoDB GeoJSON import script
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (not in git)
├── data/                       # CSV and GeoJSON files
├── static/
│   ├── css/
│   │   └── styles.css
│   └── js/
│       └── app.js              # Frontend JavaScript
└── templates/
    ├── base.html               # Base template
    └── index.html              # Main page
```

## 👥 Team

INF2003 Database Systems Project - Team 42

## 📄 License

Educational project for SIT INF2003

# INF2003 Database Systems Project Team Number 42

Group members: Gregory Tan, Lucas Ng Hong Wei, Tan Zheng Liang, Neo Chuan Zong, Cheok Zi Hin, Dion Ko

## Installing Requirements

To install the required Python packages, run:

```bash
pip install -r requirements.txt
```

### **Running the web application**

```python app.py```
