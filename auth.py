# auth.py
"""
Authentication and Authorization Module for HDB HomeFinder DB
Handles user registration, login, password hashing, and session management
"""

import os
from datetime import datetime
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from flask_login import LoginManager, UserMixin, current_user
from flask_bcrypt import Bcrypt
from sqlalchemy import text
from db_mysql import engine

bcrypt = Bcrypt()
login_manager = LoginManager()

# ========== USER MODEL ==========
class User(UserMixin):
    """User model for Flask-Login"""
    def __init__(self, user_id, email, full_name, is_admin, is_active):
        self.id = user_id
        self.email = email
        self.full_name = full_name
        self.is_admin = is_admin
        self._is_active = is_active
    
    def get_id(self):
        return str(self.id)
    
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    @property
    def is_active(self):
        return self._is_active
    
    @is_active.setter
    def is_active(self, value):
        self._is_active = value

# ========== FLASK-LOGIN CONFIGURATION ==========
@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT user_id, email, full_name, is_admin, is_active
                FROM users
                WHERE user_id = :user_id AND is_active = TRUE
            """), {"user_id": user_id})
            
            row = result.fetchone()
            if row:
                return User(
                    user_id=row[0],
                    email=row[1],
                    full_name=row[2],
                    is_admin=row[3],
                    is_active=row[4]
                )
    except Exception as e:
        print(f"Error loading user: {e}")
    
    return None

# ========== AUTHENTICATION FUNCTIONS ==========

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.generate_password_hash(password).decode('utf-8')

def check_password(password_hash, password):
    """Verify a password against its hash"""
    return bcrypt.check_password_hash(password_hash, password)

def register_user(email, password, full_name):
    """
    Register a new user
    Returns: (success, user_id or error_message)
    """
    try:
        # Validate email format
        if '@' not in email or '.' not in email:
            return False, "Invalid email format"
        
        # Validate password strength
        if len(password) < 8:
            return False, "Password must be at least 8 characters"
        
        # Hash password
        password_hash = hash_password(password)
        
        with engine.connect() as conn:
            # Check if email already exists
            check_result = conn.execute(text("""
                SELECT user_id FROM users WHERE email = :email
            """), {"email": email})
            
            if check_result.fetchone():
                return False, "Email already registered"
            
            # Insert new user
            result = conn.execute(text("""
                INSERT INTO users (email, password_hash, full_name, is_admin, is_active)
                VALUES (:email, :password_hash, :full_name, FALSE, TRUE)
            """), {
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name
            })
            
            conn.commit()
            user_id = result.lastrowid
            
            # Create MongoDB user profile
            from db_mongo import save_user_profile
            save_user_profile({
                "email": email,
                "user_id": user_id,
                "full_name": full_name,
                "registration_date": datetime.utcnow(),
                "preferences": {},
                "search_history": [],
                "saved_listings": []
            })
            
            return True, user_id
            
    except Exception as e:
        print(f"Registration error: {e}")
        return False, str(e)

def authenticate_user(email, password, ip_address=None, user_agent=None):
    """
    Authenticate user with email and password
    Returns: (success, user_object or error_message)
    """
    try:
        with engine.connect() as conn:
            # Check and unlock expired locks
            conn.execute(text("CALL sp_check_and_unlock_account(:user_id)"), 
                        {"user_id": 0})  # Will unlock all expired
            conn.commit()
            
            # Get user
            result = conn.execute(text("""
                SELECT user_id, email, password_hash, full_name, is_admin, is_active,
                       account_locked_until, failed_login_attempts
                FROM users
                WHERE email = :email
            """), {"email": email})
            
            row = result.fetchone()
            
            if not row:
                # User not found - log failed attempt with NULL user_id
                log_login_attempt(None, False, "User not found", ip_address, user_agent)
                return False, "Invalid email or password"
            
            user_id, email, password_hash, full_name, is_admin, is_active, locked_until, failed_attempts = row
            
            # Check if account is locked
            if locked_until and locked_until > datetime.now():
                log_login_attempt(user_id, False, "Account locked", ip_address, user_agent)
                return False, f"Account locked until {locked_until.strftime('%H:%M:%S')}"
            
            # Check if account is active
            if not is_active:
                log_login_attempt(user_id, False, "Account inactive", ip_address, user_agent)
                return False, "Account is inactive"
            
            # Verify password
            if not check_password(password_hash, password):
                # Increment failed attempts
                conn.execute(text("""
                    UPDATE users 
                    SET failed_login_attempts = failed_login_attempts + 1
                    WHERE user_id = :user_id
                """), {"user_id": user_id})
                conn.commit()
                
                # Check if should lock account
                if failed_attempts + 1 >= 5:
                    conn.execute(text("CALL sp_lock_account_on_failed_login(:user_id)"),
                               {"user_id": user_id})
                    conn.commit()
                    log_login_attempt(user_id, False, "Account locked after 5 failed attempts", ip_address, user_agent)
                    return False, "Too many failed attempts. Account locked for 30 minutes."
                
                log_login_attempt(user_id, False, "Invalid password", ip_address, user_agent)
                return False, "Invalid email or password"
            
            # Successful login - reset failed attempts and update last login
            conn.execute(text("""
                UPDATE users 
                SET failed_login_attempts = 0,
                    last_login = NOW(),
                    account_locked_until = NULL
                WHERE user_id = :user_id
            """), {"user_id": user_id})
            conn.commit()
            
            # Log successful login
            log_login_attempt(user_id, True, None, ip_address, user_agent)
            
            # Create User object
            user = User(user_id, email, full_name, is_admin, is_active)
            return True, user
            
    except Exception as e:
        print(f"Authentication error: {e}")
        return False, str(e)

def log_login_attempt(user_id, success, failure_reason=None, ip_address=None, user_agent=None):
    """Log login attempt to database"""
    try:
        with engine.connect() as conn:
            # If user_id is None, skip logging (user not found scenario)
            if user_id is None:
                return
            
            conn.execute(text("""
                INSERT INTO login_logs (user_id, login_successful, failure_reason, ip_address, user_agent)
                VALUES (:user_id, :success, :failure_reason, :ip_address, :user_agent)
            """), {
                "user_id": user_id,
                "success": success,
                "failure_reason": failure_reason,
                "ip_address": ip_address,
                "user_agent": user_agent
            })
            conn.commit()
    except Exception as e:
        print(f"Error logging login attempt: {e}")

def log_user_activity(user_id, activity_type, activity_data=None):
    """Log user activity to database"""
    try:
        import json
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO user_activity (user_id, activity_type, activity_data)
                VALUES (:user_id, :activity_type, :activity_data)
            """), {
                "user_id": user_id,
                "activity_type": activity_type,
                "activity_data": json.dumps(activity_data) if activity_data else None
            })
            conn.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")

def change_password(user_id, old_password, new_password):
    """Change user password"""
    try:
        with engine.connect() as conn:
            # Verify old password
            result = conn.execute(text("""
                SELECT password_hash FROM users WHERE user_id = :user_id
            """), {"user_id": user_id})
            
            row = result.fetchone()
            if not row or not check_password(row[0], old_password):
                return False, "Current password is incorrect"
            
            # Validate new password
            if len(new_password) < 8:
                return False, "New password must be at least 8 characters"
            
            # Update password
            new_hash = hash_password(new_password)
            conn.execute(text("""
                UPDATE users 
                SET password_hash = :password_hash
                WHERE user_id = :user_id
            """), {
                "user_id": user_id,
                "password_hash": new_hash
            })
            conn.commit()
            
            return True, "Password changed successfully"
    
    except Exception as e:
        print(f"Error changing password: {e}")
        return False, str(e)

# ========== DECORATORS ==========

def login_required(f):
    """Decorator to require login for a route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"ok": False, "error": "Login required"}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"ok": False, "error": "Login required"}), 401
        if not current_user.is_admin:
            return jsonify({"ok": False, "error": "Admin privileges required"}), 403
        return f(*args, **kwargs)
    return decorated_function

# ========== ADMIN FUNCTIONS ==========

def get_all_users():
    """Get all users (admin only)"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM user_statistics
                ORDER BY created_at DESC
            """))
            
            users = []
            for row in result:
                users.append(dict(row._mapping))
            
            return users
    except Exception as e:
        print(f"Error getting users: {e}")
        return []

def get_activity_summary():
    """Get activity summary (admin only)"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM activity_summary
                WHERE activity_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                ORDER BY activity_date DESC, total_count DESC
                LIMIT 100
            """))
            
            activities = []
            for row in result:
                activities.append(dict(row._mapping))
            
            return activities
    except Exception as e:
        print(f"Error getting activity summary: {e}")
        return []

def toggle_user_active_status(user_id, is_active):
    """Activate or deactivate a user account (admin only)"""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE users 
                SET is_active = :is_active
                WHERE user_id = :user_id
            """), {
                "user_id": user_id,
                "is_active": is_active
            })
            conn.commit()
            
            return True, "User status updated"
    except Exception as e:
        print(f"Error toggling user status: {e}")
        return False, str(e)