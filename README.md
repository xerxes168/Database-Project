# 🏠 HDB HomeFinder DB

INF2003 Database Systems — Group 42
Full-Stack Housing Analytics Application using MySQL + MongoDB + Flask + HTML/CSS/JS

📌 Overview

HDB HomeFinder DB is a full-stack database application designed to help users and analysts explore Singapore’s HDB resale market.

The project integrates:

- a relational MySQL database for structured resale information, household income, expenditure, mortgage rules, user accounts and loggings.
- a MongoDB database for flexible and semi-structured datasets such as amenities (GeoJSON), listing remarks (text search), town metadata and saved scenarios.

The application features:

✔ Authentication & user management

✔ Resale price trend analysis (SQL window functions)

✔ Affordability calculator using income, expenditure, mortgage rules

✔ Town comparison engine enriched with MongoDB metadata

✔ Amenity map (GeoJSON)

✔ Saved scenarios (MongoDB)

✔ Admin analytics dashboard using MySQL views & logs

This README serves as the installation guide, project overview, and user manual.

## System Architecture

Frontend (HTML/CSS/JS) → Flask API → MySQL (Aiven) + MongoDB Atlas

1. Frontend

    - HTML templates (index.html, login.html, register.html, admin.html)
    - Custom CSS (styles.css)
    - JavaScript logic (app.js)
    - Chart.js for charts
    - Mapbox GL JS for amenities map

2. Backend (Flask)

    - Session management via Flask-Login
    - Password encryption with Flask-Bcrypt
    - MySQL queries via SQLAlchemy + PyMySQL
    - MongoDB interactions via PyMongo
    - REST endpoints returning JSON responses

3. Databases

    🔵 MySQL (Relational Database)

    Stores highly structured data with constraints, foreign keys, and advanced SQL logic.

    Used for:

    - Resale flat data
    - Household income & expenditure
    - Mortgage rules & interest rates
    - Authentication
    - Login logs & user activity
    - User preferences

    🟢 MongoDB (NoSQL Database)

    Stores semi-structured or flexible datasets:

    Used for:

    - Amenities (GeoJSON)
    - Listing remarks (text search)
    - Town metadata
    - Saved “What-If” scenarios
    - User profiles (search history, favourites)

## 📂 Project Structure

```text
├── app.py                     # Main Flask application
├── auth.py                    # Authentication routes
├── db_mysql.py                # MySQL connection + SQL queries
├── db_mongo.py                # MongoDB helpers + NoSQL queries
├── templates/                 # Frontend HTML pages
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── admin.html
├── static/
│   ├── css/styles.css
│   └── js/app.js
├── data/                      # CSV / JSON datasets 
├── README.md                  # This file
└── requirements.txt           # Python dependencies
```

## 🛠️ Installation & Setup

1️⃣ Clone and install Python dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt
```

2️⃣ Configure environment variables

Create a .env file:

```env
# Aiven → Service Overview → Connection info
MYSQL_HOST=mysql-310ddec4-greggyyy.k.aivencloud.com
MYSQL_PORT=27950
MYSQL_USER=avnadmin
MYSQL_PASSWORD=AVNS_mQhInc77FoEHAtcpQ1o
MYSQL_DB=defaultdb

# Path to the CA cert from Aiven
MYSQL_SSL_CA=./ca.pem

# Atlas MongoDB > MongoDB
MONGO_URL=mongodb+srv://greggy_dbuser:JesusKing@homefinder-mongo.7d67tvq.mongodb.net/
MONGO_DB=homefinder

# Flask Configuration
SECRET_KEY=92af2f20f6801794462986fa35bc90e7cdd35ff4a682bd632132f24783cb8c6f

# Session Configuration
SESSION_TYPE=filesystem
PERMANENT_SESSION_LIFETIME=3600

# Security Settings
BCRYPT_LOG_ROUNDS=12

# Application Settings
FLASK_ENV=production
FLASK_DEBUG=False
```

3️⃣ Launch the application

```bash
python app.py
```

Visit:

```arduino
http://localhost:5000
```

## 👨‍💻 User Manual

1. Register a new account

    - Visit /register.
    - Enter your email, name and password.

2. Log in

    - Visit /login.

3. Explore features

    - Once logged in:
    - Resale price trends
    - Resale transactions
    - Town comparison
    - Affordability calculator
    - Saved scenarios
    - Amenities map

4. Admin Dashboard

    - Only available to users with is_admin = TRUE.

## Features Summary

🔐 Authentication

- Secure login & registration
- Hashed passwords
- Account lockout + login logs
- Role-based access

📈 Resale Price Trends

- SQL window functions
- Month-wise median PSM
- Multi-line charts

🏘 Town Comparison

- SQL + Mongo hybrid query
- Median PSM, minimum, maximum, transaction volume
- Region + maturity + metadata

💰 Affordability Calculator

- Uses household income/expenditure
- Loan rules, interest rates
- Max loan, monthly instalment, estimated property budget
- Save scenarios (MongoDB)

🗺 Amenities Map

- MongoDB GeoJSON
- Filter by town
- Mapbox integration

🧠 Listing Remarks Search

- MongoDB full-text search

📊 Admin Dashboard

- View login logs, activity logs
- Views (user_statistics, activity_summary)

## Tech Stack

Backend

- Python 3
- Flask
- Flask-Login
- Flask-Bcrypt
- SQLAlchemy
- PyMySQL
- PyMongo

Frontend

- HTML5
- CSS3
- JavaScript (ES6)
- Chart.js
- Mapbox GL JS

Databases

- MySQL (Aiven)
- MongoDB Atlas

Infrastructure

- Aiven (managed MySQL)
- MongoDB Atlas cluster
- Environment-configurable .env

## 👥 Team 42 Members

- Gregory Tan
- Lucas Ng Hong Wei
- Tan Zheng Liang
- Neo Chuan Zong
- Cheok Zi Hin
- Dion Ko
