import os
import re
import csv
import math
import time
import io
import json
import base64
import threading
import random
import hashlib
import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
import urllib.request
import urllib.parse
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file, session
from database import get_db, init_db
from seed_data import seed as seed_database
from brand import BRAND, SUB_BRAND, SLOGAN, SUPPORT_EMAIL, CITY, T, format_pickup_code, calculate_green_points, calculate_co2_impact
from sklearn.cluster import KMeans
import numpy as np
import qrcode

# Auto-load .env file if present
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nagarloop-municipal-secret-key-2026')

# Session security configuration (Req #10)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

# OTP Security Configuration (Req #4)
OTP_EXPIRY_MINUTES = int(os.environ.get('OTP_EXPIRY_MINUTES', 5))
OTP_MAX_ATTEMPTS = int(os.environ.get('OTP_MAX_ATTEMPTS', 5))
OTP_RESEND_COOLDOWN_SECONDS = int(os.environ.get('OTP_RESEND_COOLDOWN_SECONDS', 60))

# Email Provider Configuration (Google App Password / SMTP)
MAIL_SERVER = os.environ.get('MAIL_SERVER', '')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_FROM = os.environ.get('MAIL_FROM', MAIL_USERNAME or 'noreply@nagarloop.in')
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'

# Ensure uploads folder exists
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.context_processor
def inject_brand_and_i18n():
    lang = session.get('lang', 'en')
    def tr(key):
        return T.get(lang, {}).get(key, T.get('en', {}).get(key, key))
    return {
        'lang': lang,
        'tr': tr,
        'BRAND': BRAND,
        'SUB_BRAND': SUB_BRAND,
        'CITY': CITY,
        'SLOGAN': SLOGAN,
        'SUPPORT_EMAIL': SUPPORT_EMAIL,
        'format_pickup_code': format_pickup_code
    }

# ----------------------------------------------------
# AUTHENTICATION & NOTIFICATION HELPERS
# ----------------------------------------------------

def login_required(roles=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            is_api = request.path.startswith('/api/') or request.is_json
            
            if not user and not session.get('user_id'):
                if is_api:
                    return jsonify({'success': False, 'message': 'Authentication required. Please log in.'}), 401
                flash("Please log in or register to access this service.", "warning")
                target_role = roles[0] if roles else 'citizen'
                return redirect(url_for('login_page', role=target_role))
            
            user_role = session.get('role') or (user.get('role') if user else 'citizen')
            if roles and user_role not in roles:
                if is_api:
                    return jsonify({'success': False, 'message': f'Access denied. Account role "{user_role}" is not authorized for this action.'}), 403
                flash("Access denied for your account role.", "danger")
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def validate_indian_phone(phone_str):
    """
    Validate and normalize Indian mobile numbers.
    Accepted formats:
      - 10 digits starting with 6, 7, 8, 9 (e.g. 9825012345)
      - With +91 or 91 or 0 prefix (e.g. +919825012345, 919825012345, 09825012345)
      - With spaces or hyphens (e.g. 98250-12345, +91 98250 12345)
    Returns:
      Normalized 10-digit string if valid, else None.
    """
    if not phone_str:
        return None
    # Strip spaces, hyphens, parentheses, plus
    clean = re.sub(r'[\s\-\(\)\+]', '', str(phone_str).strip())
    # Strip +91, 91, or leading 0
    if clean.startswith('91') and len(clean) == 12:
        clean = clean[2:]
    elif clean.startswith('0') and len(clean) == 11:
        clean = clean[1:]
    
    # Must be exactly 10 digits and start with 6, 7, 8, or 9
    if re.match(r'^[6-9]\d{9}$', clean):
        return clean
    return None

def log_sms(phone, message, event_type, pickup_id=None, db_conn=None):
    """Unified Notification & SMS Simulation Engine with duplicate prevention (Phase 3 Spec)"""
    try:
        conn = db_conn if db_conn is not None else get_db()
        should_close = (db_conn is None)
        
        # Check for duplicates on single-occurrence events for the same pickup/phone
        if pickup_id and event_type in ['day_before', 'booking_confirmed', 'truck_nearby', 'society_registered', 'citizen_registered']:
            existing = conn.execute("""
                SELECT id FROM sms_logs WHERE recipient_phone = ? AND event_type = ? AND pickup_id = ?
            """, (str(phone), str(event_type), pickup_id)).fetchone()
            if existing:
                if should_close:
                    conn.close()
                return existing['id']

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sms_logs (recipient_phone, message, event_type, pickup_id)
            VALUES (?, ?, ?, ?)
        """, (str(phone), str(message), str(event_type), pickup_id))
        new_id = cursor.lastrowid

        if should_close:
            conn.commit()
            conn.close()
        return new_id
    except Exception as e:
        print(f"Error logging simulated SMS: {e}")
        return None

def generate_secure_otp():
    """Generate cryptographically secure 6-digit OTP (Req #3)"""
    return f"{secrets.SystemRandom().randint(100000, 999999)}"

def hash_otp(otp_str):
    """Store salted SHA-256 hash of OTP (Req #3)"""
    return hashlib.sha256((str(otp_str).strip() + app.secret_key).encode('utf-8')).hexdigest()

def send_otp_email(recipient_email, otp):
    """Send clean NagarLoop OTP email via SMTP / Google App Password (Req #5, #13)"""
    subject = "NagarLoop — Your Verification Code"
    body = f"""Hello,

Your NagarLoop verification code is:

{otp}

This code expires in {OTP_EXPIRY_MINUTES} minutes.

If you did not request this code, you can safely ignore this email.

Regards,
NagarLoop Team"""

    if MAIL_SERVER and MAIL_USERNAME:
        try:
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = MAIL_FROM or MAIL_USERNAME
            msg['To'] = recipient_email
            msg.set_content(body)

            with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=10) as server:
                if MAIL_USE_TLS:
                    server.starttls()
                if MAIL_USERNAME and MAIL_PASSWORD:
                    server.login(MAIL_USERNAME, MAIL_PASSWORD)
                server.send_message(msg)
            print(f"NagarLoop Email: Successfully sent OTP email to {recipient_email}")
            return True
        except Exception as e:
            print(f"NagarLoop Email Delivery Error ({recipient_email}): {e}")

    # Development / Offline Fallback Simulation
    print(f"NagarLoop Simulated OTP Email -> Recipient: {recipient_email} | OTP Code: {otp}")
    log_sms(recipient_email, f"NagarLoop Verification Code: {otp}. Expires in {OTP_EXPIRY_MINUTES} minutes.", "otp_email")
    return True

# ----------------------------------------------------
# 4R FORMULAS & CO2 ESTIMATES
# ----------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    """Calculate great circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_co2_impact(wet_kg, dry_kg, ewaste_kg, residual_kg):
    """
    Municipal CO2 Reduction Estimates (kg CO2e):
    - Wet (Landfill diversion -> Bio-CNG / Compost): 0.85 kg CO2e / kg
    - Dry (Mechanical recycling vs virgin production): 1.95 kg CO2e / kg
    - E-Waste (Circular metals & plastics recovery): 3.20 kg CO2e / kg
    - Residual (RDF replacing fossil coal in cement kiln): 0.60 kg CO2e / kg
    """
    co2 = (wet_kg * 0.85) + (dry_kg * 1.95) + (ewaste_kg * 3.20) + (residual_kg * 0.60)
    return round(co2, 2)

def generate_qr_base64(pickup_id, host_url):
    """Generate a base64 encoded QR Code data URI for pickup manifest."""
    manifest_url = f"{host_url.rstrip('/')}/manifest/{pickup_id}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=2,
    )
    qr.add_data(manifest_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{img_str}"

# ----------------------------------------------------
# ROUTE CALCULATION & RECOMMENDATION ENGINE
# ----------------------------------------------------

def calculate_route_metrics(van_pos, stops, facility_pos=None):
    if not stops:
        return 0.0, 0.0, 0.0, []

    # 1. Naive Route Distance
    naive_dist = 0.0
    curr_pos = van_pos
    for s in stops:
        naive_dist += haversine(curr_pos[0], curr_pos[1], s['lat'], s['lng'])
        curr_pos = (s['lat'], s['lng'])
    if facility_pos:
        naive_dist += haversine(curr_pos[0], curr_pos[1], facility_pos[0], facility_pos[1])

    # 2. Nearest Neighbor Optimization
    unvisited = list(stops)
    optimized_stops = []
    opt_dist = 0.0
    curr_pos = van_pos
    seq = 1

    while unvisited:
        nearest_idx = 0
        min_d = float('inf')
        for i, s in enumerate(unvisited):
            d = haversine(curr_pos[0], curr_pos[1], s['lat'], s['lng'])
            if d < min_d:
                min_d = d
                nearest_idx = i

        chosen = unvisited.pop(nearest_idx)
        chosen_dict = dict(chosen)
        chosen_dict['sequence'] = seq
        seq += 1
        optimized_stops.append(chosen_dict)
        opt_dist += min_d
        curr_pos = (chosen['lat'], chosen['lng'])

    if facility_pos:
        opt_dist += haversine(curr_pos[0], curr_pos[1], facility_pos[0], facility_pos[1])

    saved_pct = 0.0
    if naive_dist > 0:
        saved_pct = round(max(0.0, ((naive_dist - opt_dist) / naive_dist) * 100), 1)

    return round(naive_dist, 2), round(opt_dist, 2), saved_pct, optimized_stops

# ----------------------------------------------------
# PUBLIC PAGES & AUTHENTICATION
# ----------------------------------------------------

@app.route('/')
def home():
    """Public Landing Page"""
    return render_template('home.html')

@app.route('/set-lang', methods=['POST'])
def set_lang():
    """Toggle language between English and Gujarati"""
    lang = request.form.get('lang', 'en')
    if lang in ['en', 'gu']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('home'))

# ----------------------------------------------------
# EMAIL OTP AUTHENTICATION & RBAC ENDPOINTS
# ----------------------------------------------------

@app.route('/api/auth/send-otp', methods=['POST'])
def send_otp_api():
    """Generate and dispatch secure email OTP (Req #1, #2, #3, #4, #5)"""
    data = request.get_json(silent=True) or request.form
    email = data.get('email', '').strip().lower()
    target_role = data.get('role', 'citizen').strip()
    if target_role == 'society':
        target_role = 'society_manager'

    # Validate email format
    if not email or not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({'success': False, 'message': 'Please enter a valid email address.'}), 400

    conn = get_db()
    
    # Check rate limiting / resend cooldown (Req #4)
    recent_otp = conn.execute("""
        SELECT created_at FROM email_otps 
        WHERE email = ? AND datetime(created_at) > datetime('now', '-' || ? || ' seconds')
        ORDER BY id DESC LIMIT 1
    """, (email, OTP_RESEND_COOLDOWN_SECONDS)).fetchone()

    if recent_otp:
        conn.close()
        return jsonify({'success': False, 'message': f'Please wait {OTP_RESEND_COOLDOWN_SECONDS} seconds before requesting another OTP.'}), 429

    # Check user existence & role authorization (Req #2, #7)
    user = conn.execute("SELECT * FROM users WHERE email = ? OR username = ?", (email, email)).fetchone()

    # Security: Do not allow public users to claim privileged roles (Req #7)
    if user and user['role'] != target_role and not (user['role'] == 'society_manager' and target_role in ['society', 'society_manager']):
        conn.close()
        # Return generic success without dispatching OTP to prevent account enumeration / role escalation
        return jsonify({'success': True, 'message': 'OTP sent to your email address.'})

    if not user and target_role in ['admin', 'driver', 'society_manager']:
        conn.close()
        # Privileged accounts must be pre-provisioned. Return generic response (Req #2).
        return jsonify({'success': True, 'message': 'OTP sent to your email address.'})

    # Generate cryptographically secure OTP & Hash
    otp_code = generate_secure_otp()
    otp_hashed = hash_otp(otp_code)
    expires_at = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')

    conn.execute("""
        INSERT INTO email_otps (email, otp_hash, expires_at, attempts, used)
        VALUES (?, ?, ?, 0, 0)
    """, (email, otp_hashed, expires_at))
    conn.commit()
    conn.close()

    # Send Email
    send_otp_email(email, otp_code)

    return jsonify({'success': True, 'message': 'OTP sent to your email address.'})

@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp_api():
    """Verify Email OTP and establish authenticated session (Req #1, #3, #4, #10, #11)"""
    data = request.get_json(silent=True) or request.form
    email = data.get('email', '').strip().lower()
    otp_input = data.get('otp', '').strip()
    target_role = data.get('role', 'citizen').strip()
    if target_role == 'society':
        target_role = 'society_manager'

    if not email or not otp_input:
        return jsonify({'success': False, 'message': 'Email address and OTP code are required.'}), 400

    conn = get_db()
    # Find latest active OTP record for email
    otp_record = conn.execute("""
        SELECT * FROM email_otps 
        WHERE email = ? AND used = 0
        ORDER BY id DESC LIMIT 1
    """, (email,)).fetchone()

    if not otp_record:
        conn.close()
        return jsonify({'success': False, 'message': 'Incorrect OTP. Please try again.'}), 400

    # 1. Check max attempts
    if otp_record['attempts'] >= OTP_MAX_ATTEMPTS:
        conn.execute("UPDATE email_otps SET used = 1 WHERE id = ?", (otp_record['id'],))
        conn.commit()
        conn.close()
        return jsonify({'success': False, 'message': 'Too many attempts. Please request a new OTP.'}), 400

    # 2. Check expiry
    expires_at_dt = datetime.strptime(otp_record['expires_at'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expires_at_dt:
        conn.execute("UPDATE email_otps SET used = 1 WHERE id = ?", (otp_record['id'],))
        conn.commit()
        conn.close()
        return jsonify({'success': False, 'message': 'This OTP has expired. Please request a new OTP.'}), 400

    # 3. Check hash
    if hash_otp(otp_input) != otp_record['otp_hash']:
        new_attempts = otp_record['attempts'] + 1
        is_used = 1 if new_attempts >= OTP_MAX_ATTEMPTS else 0
        conn.execute("UPDATE email_otps SET attempts = ?, used = ? WHERE id = ?", (new_attempts, is_used, otp_record['id']))
        conn.commit()
        conn.close()
        if new_attempts >= OTP_MAX_ATTEMPTS:
            return jsonify({'success': False, 'message': 'Too many attempts. Please request a new OTP.'}), 400
        return jsonify({'success': False, 'message': 'Incorrect OTP. Please try again.'}), 400

    # Mark OTP as used immediately (Single-use enforcement Req #3)
    conn.execute("UPDATE email_otps SET used = 1 WHERE id = ?", (otp_record['id'],))
    conn.commit()

    # Retrieve or auto-provision citizen account
    user = conn.execute("SELECT * FROM users WHERE email = ? OR username = ?", (email, email)).fetchone()

    if not user:
        if target_role == 'citizen':
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM households")
            hh_count = cur.fetchone()[0] + 1
            hh_code = f"H{hh_count:03d}"
            name = email.split('@')[0].replace('.', ' ').replace('_', ' ').title()

            cur.execute("""
                INSERT INTO households (household_code, name, phone, street_segment, is_society)
                VALUES (?, ?, '9999999999', 'Navrangpura', 0)
            """, (hh_code, name))
            hh_id = cur.lastrowid

            cur.execute("""
                INSERT INTO users (username, password, name, role, email, is_verified, phone, locality, household_id)
                VALUES (?, 'otp_verified', ?, 'citizen', ?, 1, '9999999999', 'Navrangpura', ?)
            """, (email, name, email, hh_id))
            user_id = cur.lastrowid
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        else:
            conn.close()
            return jsonify({'success': False, 'message': f'No authorized {target_role.replace("_", " ").title()} account exists for this email.'}), 403

    conn.close()

    # Enforce Role Authorization (Req #7, #8)
    user_role = user['role']
    if user_role != target_role and not (user_role == 'society_manager' and target_role in ['society', 'society_manager']):
        return jsonify({'success': False, 'message': f'Access denied. Your account role is "{user_role.replace("_", " ").title()}", not "{target_role.replace("_", " ").title()}".'}), 403

    # Establish Secure Server-Side Session (Req #10)
    session.clear()
    session['user_id'] = user['id']
    session['username'] = user['username'] or user['email']
    session['name'] = user['name']
    session['role'] = user['role']
    session['household_id'] = user['household_id']
    session['society_id'] = user['society_id']
    session['van_id'] = user['van_id']
    session['user'] = {
        'id': user['id'],
        'username': user['username'] or user['email'],
        'name': user['name'],
        'role': user['role'],
        'household_id': user['household_id'],
        'society_id': user['society_id'],
        'van_id': user['van_id']
    }

    # Determine redirect destination based on server-side role
    if user_role == 'admin':
        redirect_url = url_for('admin_dashboard')
    elif user_role == 'driver':
        redirect_url = url_for('driver_portal')
    elif user_role == 'society_manager':
        redirect_url = url_for('society_dashboard')
    else:
        redirect_url = url_for('citizen_booking')

    flash(f"🎉 Email verified successfully! Welcome back, {user['name']}.", "success")
    return jsonify({'success': True, 'message': 'Email verified successfully.', 'redirect_url': redirect_url})

@app.route('/login/<role>', methods=['GET', 'POST'])
def login_page(role):
    if role not in ['citizen', 'society_manager', 'society', 'driver', 'admin']:
        role = 'citizen'
    if role == 'society':
        role = 'society_manager'

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()

        conn = get_db()
        user = conn.execute("""
            SELECT * FROM users 
            WHERE (LOWER(username) = ? OR LOWER(email) = ? OR phone = ?) 
              AND (password = ? OR password = 'otp_verified') 
              AND (role = ? OR (role = 'society_manager' AND ? = 'society'))
        """, (username, username, username, password, role, role)).fetchone()
        conn.close()

        if user:
            if user['is_verified'] == 0:
                session['pending_verification_email'] = user['email']
                session['pending_role'] = user['role']
                flash("Please verify your email before logging in.", "warning")
                return redirect(url_for('verify_email_page'))

            session['user_id'] = user['id']
            session['username'] = user['username']
            session['name'] = user['name']
            session['role'] = user['role']
            session['household_id'] = user['household_id']
            session['society_id'] = user['society_id']
            session['van_id'] = user['van_id']
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'name': user['name'],
                'role': user['role'],
                'household_id': user['household_id'],
                'society_id': user['society_id'],
                'van_id': user['van_id']
            }
            flash(f"Welcome back, {user['name']}!", "success")
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'driver':
                return redirect(url_for('driver_portal'))
            elif user['role'] == 'society_manager':
                return redirect(url_for('society_dashboard'))
            else:
                return redirect(url_for('citizen_booking'))
        else:
            flash("Invalid username/phone or password for this role.", "danger")

    return render_template('login.html', role=role)

@app.route('/register', methods=['GET', 'POST'])
def register():
    reg_type = request.args.get('type', 'citizen')
    if request.method == 'POST':
        reg_type = request.form.get('reg_type', 'citizen')
        password = request.form.get('password', '').strip()
        raw_phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip().lower()

        if not raw_phone or not password:
            flash("Mobile number and password are required.", "danger")
            return render_template('register.html', reg_type=reg_type)

        phone = validate_indian_phone(raw_phone)
        if not phone:
            flash("Please enter a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9 (e.g. 9825012345).", "danger")
            return render_template('register.html', reg_type=reg_type)

        if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            flash("Please enter a valid email address.", "danger")
            return render_template('register.html', reg_type=reg_type)

        conn = get_db()
        existing = conn.execute("SELECT id FROM users WHERE username = ? OR phone = ? OR (email IS NOT NULL AND email = ?)", (phone, phone, email)).fetchone()
        if existing:
            conn.close()
            flash("An account with this mobile number or email already exists. Please log in.", "warning")
            return redirect(url_for('login_page', role='society_manager' if reg_type in ['society', 'society_manager'] else 'citizen'))

        cur = conn.cursor()
        if reg_type in ['society', 'society_manager']:
            society_name = request.form.get('society_name', '').strip()
            manager_name = request.form.get('manager_name', '').strip()
            address = request.form.get('address', '').strip()
            collection_point = request.form.get('collection_point', '').strip() or 'Main Gate Security Post'

            if not society_name or not manager_name or not address:
                conn.close()
                flash("Please fill in all society registration details.", "danger")
                return render_template('register.html', reg_type='society')

            cur.execute("SELECT COUNT(*) FROM societies")
            soc_count = cur.fetchone()[0] + 1
            soc_code = f"SOC-{soc_count:03d}"

            cur.execute("""
                INSERT INTO societies (society_code, name, manager_name, phone, address, collection_point, ward)
                VALUES (?, ?, ?, ?, ?, ?, 'Navrangpura')
            """, (soc_code, society_name, manager_name, phone, address, collection_point))
            soc_id = cur.lastrowid

            cur.execute("""
                INSERT INTO households (household_code, name, phone, street_segment, is_society, society_id)
                VALUES (?, ?, ?, ?, 1, ?)
            """, (soc_code, society_name, phone, address, soc_id))
            hh_id = cur.lastrowid
            user_email = email or f"society{soc_id}@nagarloop.in"
            cur.execute("""
                INSERT INTO users (username, password, name, role, phone, email, is_verified, locality, household_id, society_id)
                VALUES (?, ?, ?, 'society_manager', ?, ?, 0, ?, ?, ?)
            """, (phone, password, manager_name, phone, user_email, address, hh_id, soc_id))
            user_id = cur.lastrowid
            conn.commit()

            # Generate OTP & Dispatch Email
            otp_code = generate_secure_otp()
            otp_hashed = hash_otp(otp_code)
            expires_at = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')

            cur.execute("""
                INSERT INTO email_otps (email, otp_hash, expires_at, attempts, used)
                VALUES (?, ?, ?, 0, 0)
            """, (user_email, otp_hashed, expires_at))
            conn.commit()
            conn.close()

            send_otp_email(user_email, otp_code)

            session['pending_verification_email'] = user_email
            session['pending_role'] = 'society_manager'
            flash(f"🎉 Account created! We sent a 6-digit OTP code to {user_email}. Please verify your email.", "info")
            return redirect(url_for('verify_email_page'))

        else:
            name = request.form.get('name', '').strip()
            address = request.form.get('address', '').strip() or 'Navrangpura'

            if not name:
                conn.close()
                flash("Please enter your full name.", "danger")
                return render_template('register.html', reg_type='citizen')

            cur.execute("SELECT COUNT(*) FROM households")
            hh_count = cur.fetchone()[0] + 1
            hh_code = f"H{hh_count:03d}"

            cur.execute("""
                INSERT INTO households (household_code, name, phone, street_segment, is_society)
                VALUES (?, ?, ?, ?, 0)
            """, (hh_code, name, phone, address))
            hh_id = cur.lastrowid

            user_email = email or f"citizen{hh_id}@nagarloop.in"
            cur.execute("""
                INSERT INTO users (username, password, name, role, phone, email, is_verified, locality, household_id)
                VALUES (?, ?, ?, 'citizen', ?, ?, 0, ?, ?)
            """, (phone, password, name, phone, user_email, address, hh_id))
            user_id = cur.lastrowid
            conn.commit()

            # Generate OTP & Dispatch Email
            otp_code = generate_secure_otp()
            otp_hashed = hash_otp(otp_code)
            expires_at = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')

            cur.execute("""
                INSERT INTO email_otps (email, otp_hash, expires_at, attempts, used)
                VALUES (?, ?, ?, 0, 0)
            """, (user_email, otp_hashed, expires_at))
            conn.commit()
            conn.close()

            send_otp_email(user_email, otp_code)

            session['pending_verification_email'] = user_email
            session['pending_role'] = 'citizen'
            flash(f"🎉 Account created! We sent a 6-digit OTP code to {user_email}. Please verify your email.", "info")
            return redirect(url_for('verify_email_page'))

    return render_template('register.html', reg_type=reg_type)

@app.route('/verify-email', methods=['GET', 'POST'])
def verify_email_page():
    """Dedicated Email OTP Verification Page (Req #8, #9)"""
    email = session.get('pending_verification_email')
    target_role = session.get('pending_role', 'citizen')

    if not email:
        flash("No pending email verification found. Please register or log in.", "warning")
        return redirect(url_for('register'))

    # Mask recipient email for privacy in UI
    parts = email.split('@')
    masked_email = f"{parts[0][:2]}****@{parts[1]}" if len(parts[0]) > 2 else f"*@{parts[1]}"

    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        if not otp_input or len(otp_input) != 6:
            return render_template('verify_email.html', masked_email=masked_email, error_msg="Please enter a valid 6-digit OTP code.")

        conn = get_db()
        otp_record = conn.execute("""
            SELECT * FROM email_otps 
            WHERE email = ? AND used = 0
            ORDER BY id DESC LIMIT 1
        """, (email,)).fetchone()

        if not otp_record:
            conn.close()
            return render_template('verify_email.html', masked_email=masked_email, error_msg="Incorrect OTP. Please try again.")

        # Check attempt limits
        if otp_record['attempts'] >= OTP_MAX_ATTEMPTS:
            conn.execute("UPDATE email_otps SET used = 1 WHERE id = ?", (otp_record['id'],))
            conn.commit()
            conn.close()
            return render_template('verify_email.html', masked_email=masked_email, error_msg="Too many failed attempts. Please click Resend Code.")

        # Check expiry
        expires_at_dt = datetime.strptime(otp_record['expires_at'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() > expires_at_dt:
            conn.execute("UPDATE email_otps SET used = 1 WHERE id = ?", (otp_record['id'],))
            conn.commit()
            conn.close()
            return render_template('verify_email.html', masked_email=masked_email, error_msg="This OTP has expired. Please click Resend Code.")

        # Check Hash
        if hash_otp(otp_input) != otp_record['otp_hash']:
            conn.execute("UPDATE email_otps SET attempts = attempts + 1 WHERE id = ?", (otp_record['id'],))
            conn.commit()
            conn.close()
            return render_template('verify_email.html', masked_email=masked_email, error_msg="Incorrect OTP. Please try again.")

        # SUCCESS: Mark user verified & OTP used
        conn.execute("UPDATE users SET is_verified = 1 WHERE email = ? OR username = ?", (email, email))
        conn.execute("UPDATE email_otps SET used = 1 WHERE id = ?", (otp_record['id'],))
        conn.commit()

        # Fetch verified user record to establish authenticated session directly
        user = conn.execute("SELECT * FROM users WHERE email = ? OR username = ?", (email, email)).fetchone()
        conn.close()

        session.pop('pending_verification_email', None)
        session.pop('pending_role', None)

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['name'] = user['name']
            session['role'] = user['role']
            session['household_id'] = user['household_id']
            session['society_id'] = user['society_id']
            session['van_id'] = user['van_id']
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'name': user['name'],
                'role': user['role'],
                'household_id': user['household_id'],
                'society_id': user['society_id'],
                'van_id': user['van_id']
            }

            flash(f"🎉 Email verified! Welcome to NagarLoop, {user['name']}.", "success")
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'driver':
                return redirect(url_for('driver_portal'))
            elif user['role'] == 'society_manager':
                return redirect(url_for('society_dashboard'))
            else:
                return redirect(url_for('citizen_booking'))

        flash("🎉 Email verified successfully! Please log in to your account.", "success")
        return redirect(url_for('login_page', role=target_role))

    return render_template('verify_email.html', masked_email=masked_email)

@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    """Resend OTP handler with rate limiting (Req #6, #19)"""
    email = session.get('pending_verification_email')
    if not email:
        flash("No pending verification found.", "warning")
        return redirect(url_for('register'))

    conn = get_db()
    recent_otp = conn.execute("""
        SELECT created_at FROM email_otps 
        WHERE email = ? AND datetime(created_at) > datetime('now', '-' || ? || ' seconds')
        ORDER BY id DESC LIMIT 1
    """, (email, OTP_RESEND_COOLDOWN_SECONDS)).fetchone()

    if recent_otp:
        conn.close()
        flash(f"Please wait {OTP_RESEND_COOLDOWN_SECONDS} seconds before requesting another code.", "warning")
        return redirect(url_for('verify_email_page'))

    # Invalidate old OTPs for this email
    conn.execute("UPDATE email_otps SET used = 1 WHERE email = ? AND used = 0", (email,))

    otp_code = generate_secure_otp()
    otp_hashed = hash_otp(otp_code)
    expires_at = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')

    conn.execute("""
        INSERT INTO email_otps (email, otp_hash, expires_at, attempts, used)
        VALUES (?, ?, ?, 0, 0)
    """, (email, otp_hashed, expires_at))
    conn.commit()
    conn.close()

    send_otp_email(email, otp_code)
    flash("A new 6-digit verification code has been sent to your email.", "success")
    return redirect(url_for('verify_email_page'))

@app.route('/change-email', methods=['POST'])
def change_email():
    """Safe email change handler (Req #10)"""
    session.pop('pending_verification_email', None)
    session.pop('pending_role', None)
    flash("You can now enter a different email address to register.", "info")
    return redirect(url_for('register'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for('home'))

# ----------------------------------------------------
# CITIZEN & SOCIETY BOOKING FLOWS
# ----------------------------------------------------

@app.route('/book')
@login_required(roles=['citizen', 'admin'])
def citizen_booking():
    """Citizen Doorstep Booking Portal (Requires Citizen/Admin Login)"""
    user = session.get('user')
    hh_id = session.get('household_id') or (user.get('household_id') if user else 1) or 1
    repeat_id = request.args.get('repeat_id')

    conn = get_db()
    household = conn.execute("SELECT * FROM households WHERE id = ?", (hh_id,)).fetchone()
    if not household:
        household = conn.execute("SELECT * FROM households WHERE id = 1").fetchone()

    total_points = conn.execute("""
        SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE household_id = ?
    """, (household['id'],)).fetchone()[0]

    # Pre-fill repeat pickup data if requested
    repeat_pickup = None
    if repeat_id:
        repeat_pickup = conn.execute("SELECT * FROM pickups WHERE id = ?", (repeat_id,)).fetchone()

    pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        WHERE p.household_id = ?
        ORDER BY p.id DESC
    """, (household['id'],)).fetchall()

    citizen_streams = conn.execute("""
        SELECT ps.stream_type, COALESCE(SUM(ps.estimated_kg), 0) as total_kg
        FROM pickup_streams ps
        JOIN pickups p ON ps.pickup_id = p.id
        WHERE p.household_id = ?
        GROUP BY ps.stream_type
    """, (household['id'],)).fetchall()

    streams_dict = {row['stream_type']: round(row['total_kg'], 1) for row in citizen_streams}
    wet_kg = streams_dict.get('wet', 0.0)
    dry_kg = streams_dict.get('dry', 0.0)
    ewaste_kg = streams_dict.get('e_waste', 0.0)
    residual_kg = streams_dict.get('residual', 0.0)
    total_diverted = round(wet_kg + dry_kg + ewaste_kg + residual_kg, 1)
    co2_saved = calculate_co2_impact(wet_kg, dry_kg, ewaste_kg, residual_kg)

    pickup_list = []
    for p in pickups:
        p_dict = dict(p)
        streams = conn.execute("""
            SELECT ps.*, f.name as facility_name, f.facility_type
            FROM pickup_streams ps
            LEFT JOIN facilities f ON ps.facility_id = f.id
            WHERE ps.pickup_id = ?
        """, (p['id'],)).fetchall()
        p_dict['streams'] = [dict(s) for s in streams]
        pickup_list.append(p_dict)

    conn.close()

    return render_template('citizen_report.html',
                           household=household,
                           total_points=total_points,
                           total_diverted=total_diverted,
                           wet_kg=wet_kg,
                           dry_kg=dry_kg,
                           ewaste_kg=ewaste_kg,
                           residual_kg=residual_kg,
                           co2_saved=co2_saved,
                           pickups=pickup_list,
                           repeat_pickup=repeat_pickup)

@app.route('/book-pickup', methods=['POST'])
@login_required(roles=['citizen', 'society_manager', 'admin'])
def book_pickup():
    user = session.get('user')
    user_role = session.get('role') or (user.get('role') if user else 'citizen')
    is_society = 1 if (request.form.get('society_id') or request.form.get('is_society') == '1') else 0

    if is_society:
        if user_role not in ['society_manager', 'admin']:
            flash("Access denied: Only Society Managers can submit bulk society bookings.", "danger")
            return redirect(url_for('home'))
        society_id = session.get('society_id') if user_role == 'society_manager' else (request.form.get('society_id') or session.get('society_id') or 1)
        household_id = None
    else:
        if user_role not in ['citizen', 'admin']:
            flash("Access denied: Only Citizens can book household pickups.", "danger")
            return redirect(url_for('home'))
        household_id = session.get('household_id') if user_role == 'citizen' else (request.form.get('household_id') or session.get('household_id') or 1)
        society_id = None

    lat = float(request.form.get('lat', '23.0375') or 23.0375)
    lng = float(request.form.get('lng', '72.5520') or 72.5520)

    # Segregated streams & Estimated KG
    has_wet = 'stream_wet' in request.form or request.form.get('stream_wet') in ['on', '1', 'true']
    has_dry = 'stream_dry' in request.form or request.form.get('stream_dry') in ['on', '1', 'true']
    has_ewaste = 'stream_ewaste' in request.form or request.form.get('stream_ewaste') in ['on', '1', 'true']
    has_residual = 'stream_residual' in request.form or request.form.get('stream_residual') in ['on', '1', 'true']

    try:
        wet_kg = float(request.form.get('stream_wet_kg', '4.0') or 4.0) if has_wet else 0.0
        dry_kg = float(request.form.get('stream_dry_kg', '3.0') or 3.0) if has_dry else 0.0
        ewaste_kg = float(request.form.get('stream_ewaste_kg', '1.0') or 1.0) if has_ewaste else 0.0
        residual_kg = float(request.form.get('stream_residual_kg', '1.5') or 1.5) if has_residual else 0.0
    except ValueError:
        flash("Invalid estimated quantity. Please enter positive numbers.", "danger")
        return redirect(url_for('citizen_booking'))

    # Validation: Positive quantities
    if wet_kg < 0 or dry_kg < 0 or ewaste_kg < 0 or residual_kg < 0:
        flash("Estimated quantities cannot be negative.", "danger")
        return redirect(url_for('citizen_booking'))

    stream_kg_dict = {}
    if has_wet and wet_kg > 0: stream_kg_dict['wet'] = wet_kg
    if has_dry and dry_kg > 0: stream_kg_dict['dry'] = dry_kg
    if has_ewaste and ewaste_kg > 0: stream_kg_dict['e_waste'] = ewaste_kg
    if has_residual and residual_kg > 0: stream_kg_dict['residual'] = residual_kg

    if not stream_kg_dict:
        flash("Please select at least one segregated stream and enter an estimated quantity.", "warning")
        return redirect(url_for('citizen_booking'))

    total_kg = round(sum(stream_kg_dict.values()), 1)
    bin_score = random.randint(75, 95)
    green_points = calculate_green_points(stream_kg_dict, bin_score=bin_score, is_society=bool(is_society))

    photo_path = "/static/images/bins/sample_bin_1.svg"
    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename:
            filename = f"bin_{int(time.time())}_{os.urandom(4).hex()}_{file.filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            photo_path = f"/static/uploads/{filename}"

    conn = get_db()
    cur = conn.cursor()

    # Address determination & persistence
    address = request.form.get('address', '').strip()
    if not address:
        if is_society and society_id:
            s_row = conn.execute("SELECT address, collection_point FROM societies WHERE id = ?", (society_id,)).fetchone()
            address = f"{s_row['collection_point']}, {s_row['address']}" if s_row else "Gujarat, India"
        elif household_id:
            h_row = conn.execute("SELECT street_segment FROM households WHERE id = ?", (household_id,)).fetchone()
            address = f"{h_row['street_segment']}, Gujarat, India" if h_row else "Gujarat, India"
        else:
            address = "Gujarat, India"

    cur.execute("SELECT lat, lng FROM pickups LIMIT 40")
    existing_coords = cur.fetchall()
    pickup_zone = 1
    if len(existing_coords) >= 5:
        coords_arr = np.array([[r['lat'], r['lng']] for r in existing_coords])
        kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
        kmeans.fit(coords_arr)
        pickup_zone = int(kmeans.predict(np.array([[lat, lng]]))[0]) + 1

    ai_image_check = request.form.get('ai_image_check', 'passed').strip()
    try:
        ai_confidence = float(request.form.get('ai_confidence', '0.85') or 0.85)
    except ValueError:
        ai_confidence = 0.85

    # Backend Security Enforcement: Hard block if AI validation explicitly failed, warned, not submitted, or confidence < 0.30
    if ai_image_check in ['failed', 'warning', 'skipped', 'not_submitted'] or ai_confidence < 0.30:
        flash("⚠️ Booking blocked: A valid waste photo must be verified before booking. Please upload/take a clear photo of waste.", "danger")
        return redirect(url_for('society_dashboard') if is_society else url_for('citizen_booking'))

    cur.execute("""
        INSERT INTO pickups (
            household_id, society_id, is_society, address, lat, lng,
            bin_score, photo_path, status, pickup_zone, total_kg, earned_points,
            ai_image_check, ai_confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
    """, (household_id if not is_society else None, society_id if is_society else None, is_society, address, lat, lng, bin_score, photo_path, pickup_zone, total_kg, green_points, ai_image_check, ai_confidence))
    pickup_id = cur.lastrowid
    p_code = format_pickup_code(pickup_id)
    cur.execute("UPDATE pickups SET pickup_code = ? WHERE id = ?", (p_code, pickup_id))

    # Insert streams
    for stream_type, kg in stream_kg_dict.items():
        facility_id = 1 if stream_type == 'wet' else (2 if stream_type == 'dry' else (3 if stream_type == 'e_waste' else 4))
        cur.execute("""
            INSERT INTO pickup_streams (pickup_id, stream_type, estimated_kg, facility_id, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (pickup_id, stream_type, kg, facility_id))

    # Green points ledger
    if green_points > 0:
        cur.execute("""
            INSERT INTO points_ledger (household_id, society_id, pickup_id, points, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (household_id if not is_society else None, society_id if is_society else None, pickup_id, green_points, f"Segregated 4-Stream Collection {p_code} ({total_kg} kg, Score: {bin_score}/100)"))

    # Simulated notification
    hh = None
    if household_id:
        cur.execute("SELECT phone FROM households WHERE id = ?", (household_id,))
        hh = cur.fetchone()
    phone = hh['phone'] if hh else '9876543210'
    log_sms(phone, f"Your NagarLoop pickup {p_code} is confirmed. +{green_points} Green Points reserved.", "booking_confirmed", pickup_id, db_conn=conn)

    conn.commit()
    conn.close()

    flash(f"🎉 Pickup #{p_code} booked successfully! Estimated: {total_kg} kg | +{green_points} Green Points! 🌿", "success")
    if is_society:
        return redirect(url_for('society_dashboard'))
    return redirect(url_for('citizen_booking'))

# ----------------------------------------------------
# PUBLIC WASTE REPORT (NO LOGIN REQUIRED)
# ----------------------------------------------------

@app.route('/report-public', methods=['GET', 'POST'])
def report_public():
    """Public Waste Report (Roadside / Event / Dumping) — No Login Required"""
    if request.method == 'POST':
        address = request.form.get('address', '').strip() or 'Navrangpura Roadside'
        lat = float(request.form.get('lat', '23.0375') or 23.0375)
        lng = float(request.form.get('lng', '72.5520') or 72.5520)
        waste_type = request.form.get('waste_type', 'dry')
        estimated_kg = float(request.form.get('estimated_kg', '12.0') or 12.0)
        description = request.form.get('description', '').strip()
        reporter_name = request.form.get('reporter_name', '').strip() or 'Anonymous Citizen'
        raw_rep_phone = request.form.get('reporter_phone', '').strip()
        reporter_phone = validate_indian_phone(raw_rep_phone) if raw_rep_phone else 'N/A'

        photo_path = "/static/images/bins/sample_bin_1.svg"
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename:
                filename = f"public_{int(time.time())}_{os.urandom(4).hex()}_{file.filename}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(save_path)
                photo_path = f"/static/uploads/{filename}"

        conn = get_db()
        cur = conn.cursor()

        ai_image_check = request.form.get('ai_image_check', 'passed').strip()
        try:
            ai_confidence = float(request.form.get('ai_confidence', '0.85') or 0.85)
        except ValueError:
            ai_confidence = 0.85

        if ai_image_check in ['failed', 'warning', 'skipped', 'not_submitted'] or ai_confidence < 0.30:
            flash("⚠️ Public report blocked: A valid waste photo must be verified before submitting. Please attach or take a clear photo of waste.", "danger")
            return redirect(url_for('report_public'))

        cur.execute("""
            INSERT INTO pickups (
                is_public, reporter_name, reporter_phone, public_description,
                address, lat, lng, bin_score, photo_path, status, total_kg, earned_points,
                ai_image_check, ai_confidence
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, 70, ?, 'pending', ?, 0, ?, ?)
        """, (reporter_name, reporter_phone, description, address, lat, lng, photo_path, estimated_kg, ai_image_check, ai_confidence))
        pickup_id = cur.lastrowid
        p_code = format_pickup_code(pickup_id)
        cur.execute("UPDATE pickups SET pickup_code = ? WHERE id = ?", (p_code, pickup_id))

        stream_code = 'wet' if waste_type in ['wet', 'organic'] else ('dry' if waste_type in ['dry', 'plastic'] else ('e_waste' if waste_type == 'ewaste' else 'residual'))
        facility_id = 1 if stream_code == 'wet' else (2 if stream_code == 'dry' else (3 if stream_code == 'e_waste' else 4))

        cur.execute("""
            INSERT INTO pickup_streams (pickup_id, stream_type, estimated_kg, facility_id, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (pickup_id, stream_code, estimated_kg, facility_id))

        if reporter_phone and reporter_phone != 'N/A':
            log_sms(reporter_phone, f"NagarLoop: Public waste report {p_code} received. Municipal operations will verify and dispatch.", "public_report_received", pickup_id, db_conn=conn)

        conn.commit()
        conn.close()

        flash(f"🎉 Public waste report #{p_code} submitted successfully! Municipal team has been notified for verification.", "success")
        return redirect(url_for('home'))

    return render_template('public_report.html')

# ----------------------------------------------------
# SOCIETY SYSTEM & DASHBOARD
# ----------------------------------------------------

@app.route('/society/dashboard')
@login_required(roles=['society_manager', 'admin'])
def society_dashboard():
    """Society Manager Operations & Green Points Portal (Phase 3 Privacy Protected)"""
    user = session.get('user')
    user_role = session.get('role') or (user.get('role') if user else 'citizen')

    if user_role == 'society_manager':
        soc_id = session.get('society_id') or (user.get('society_id') if user else 1) or 1
    else: # admin
        requested_soc = request.args.get('society_id')
        soc_id = int(requested_soc) if requested_soc else (session.get('society_id') or 1)

    conn = get_db()
    society = conn.execute("SELECT * FROM societies WHERE id = ?", (soc_id,)).fetchone()
    if not society:
        society = conn.execute("SELECT * FROM societies WHERE id = 1").fetchone()

    total_points = conn.execute("""
        SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE society_id = ?
    """, (society['id'],)).fetchone()[0]

    pickups = conn.execute("""
        SELECT p.*, s.name as society_name, s.collection_point, s.address, v.van_code, v.driver_name
        FROM pickups p
        JOIN societies s ON p.society_id = s.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.society_id = ?
        ORDER BY p.id DESC
    """, (society['id'],)).fetchall()

    streams = conn.execute("""
        SELECT ps.stream_type, COALESCE(SUM(ps.estimated_kg), 0) as total_kg
        FROM pickup_streams ps
        JOIN pickups p ON ps.pickup_id = p.id
        WHERE p.society_id = ?
        GROUP BY ps.stream_type
    """, (society['id'],)).fetchall()

    streams_dict = {row['stream_type']: round(row['total_kg'], 1) for row in streams}
    wet_kg = streams_dict.get('wet', 0.0)
    dry_kg = streams_dict.get('dry', 0.0)
    ewaste_kg = streams_dict.get('e_waste', 0.0)
    residual_kg = streams_dict.get('residual', 0.0)
    total_diverted = round(wet_kg + dry_kg + ewaste_kg + residual_kg, 1)
    co2_saved = calculate_co2_impact(wet_kg, dry_kg, ewaste_kg, residual_kg)

    pickup_list = []
    for p in pickups:
        p_dict = dict(p)
        p_streams = conn.execute("""
            SELECT ps.*, f.name as facility_name
            FROM pickup_streams ps
            LEFT JOIN facilities f ON ps.facility_id = f.id
            WHERE ps.pickup_id = ?
        """, (p['id'],)).fetchall()
        p_dict['streams'] = [dict(s) for s in p_streams]
        pickup_list.append(p_dict)

    conn.close()

    return render_template('society_dashboard.html',
                           society=society,
                           total_points=total_points,
                           total_diverted=total_diverted,
                           wet_kg=wet_kg,
                           dry_kg=dry_kg,
                           ewaste_kg=ewaste_kg,
                           residual_kg=residual_kg,
                           co2_saved=co2_saved,
                           pickups=pickup_list)

@app.route('/society/book')
@login_required(roles=['society_manager', 'admin'])
def society_booking():
    """Bulk Society Waste Collection Booking"""
    user = session.get('user')
    user_role = session.get('role') or (user.get('role') if user else 'citizen')

    if user_role == 'society_manager':
        soc_id = session.get('society_id') or (user.get('society_id') if user else 1) or 1
    else: # admin
        requested_soc = request.args.get('society_id')
        soc_id = int(requested_soc) if requested_soc else (session.get('society_id') or 1)

    conn = get_db()
    society = conn.execute("SELECT * FROM societies WHERE id = ?", (soc_id,)).fetchone()
    if not society:
        society = conn.execute("SELECT * FROM societies WHERE id = 1").fetchone()
    conn.close()

    return render_template('society_booking.html', society=society)

# ----------------------------------------------------
# CITIZEN MY PICKUPS & IMPACT
# ----------------------------------------------------

@app.route('/my-reports', endpoint='my_reports')
@app.route('/my-pickups', endpoint='citizen_my_reports')
@login_required(roles=['citizen', 'admin'])
def citizen_my_reports():
    user = session.get('user')
    hh_id = session.get('household_id') or (user.get('household_id') if user else 1) or 1

    conn = get_db()
    household = conn.execute("SELECT * FROM households WHERE id = ?", (hh_id,)).fetchone()
    if not household:
        household = conn.execute("SELECT * FROM households WHERE id = 1").fetchone()

    total_points = conn.execute("""
        SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE household_id = ?
    """, (household['id'],)).fetchone()[0]

    pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment, v.van_code, v.driver_name
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.household_id = ?
        ORDER BY p.id DESC
    """, (household['id'],)).fetchall()

    pickup_list = []
    for p in pickups:
        p_dict = dict(p)
        streams = conn.execute("""
            SELECT ps.*, f.name as facility_name, f.facility_type
            FROM pickup_streams ps
            LEFT JOIN facilities f ON ps.facility_id = f.id
            WHERE ps.pickup_id = ?
        """, (p['id'],)).fetchall()
        p_dict['streams'] = [dict(s) for s in streams]
        pickup_list.append(p_dict)

    conn.close()

    return render_template('citizen_my_reports.html',
                           household=household,
                           total_points=total_points,
                           pickups=pickup_list)

@app.route('/impact')
@login_required(roles=['citizen', 'admin'])
def citizen_impact():
    user = session.get('user')
    hh_id = session.get('household_id') or (user.get('household_id') if user else 1) or 1

    conn = get_db()
    household = conn.execute("SELECT * FROM households WHERE id = ?", (hh_id,)).fetchone()
    if not household:
        household = conn.execute("SELECT * FROM households WHERE id = 1").fetchone()

    total_points = conn.execute("SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE household_id = ?", (household['id'],)).fetchone()[0]

    citizen_streams = conn.execute("""
        SELECT ps.stream_type, COALESCE(SUM(ps.estimated_kg), 0) as total_kg
        FROM pickup_streams ps
        JOIN pickups p ON ps.pickup_id = p.id
        WHERE p.household_id = ?
        GROUP BY ps.stream_type
    """, (household['id'],)).fetchall()

    streams_dict = {row['stream_type']: round(row['total_kg'], 1) for row in citizen_streams}
    wet_kg = streams_dict.get('wet', 0.0)
    dry_kg = streams_dict.get('dry', 0.0)
    ewaste_kg = streams_dict.get('e_waste', 0.0)
    residual_kg = streams_dict.get('residual', 0.0)
    total_diverted = round(wet_kg + dry_kg + ewaste_kg + residual_kg, 1)
    co2_saved = calculate_co2_impact(wet_kg, dry_kg, ewaste_kg, residual_kg)

    recent_pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        WHERE p.household_id = ?
        ORDER BY p.id DESC LIMIT 5
    """, (household['id'],)).fetchall()

    pickup_list = []
    for p in recent_pickups:
        p_dict = dict(p)
        streams = conn.execute("""
            SELECT ps.*, f.name as facility_name, f.facility_type
            FROM pickup_streams ps
            LEFT JOIN facilities f ON ps.facility_id = f.id
            WHERE ps.pickup_id = ?
        """, (p['id'],)).fetchall()
        p_dict['streams'] = [dict(s) for s in streams]
        pickup_list.append(p_dict)

    conn.close()
    return render_template('citizen_impact.html',
                           household=household,
                           total_points=total_points,
                           total_diverted=total_diverted,
                           wet_kg=wet_kg,
                           dry_kg=dry_kg,
                           ewaste_kg=ewaste_kg,
                           residual_kg=residual_kg,
                           co2_saved=co2_saved,
                           pickups=pickup_list)

# ----------------------------------------------------
# DRIVER PORTAL & SHIFT OPERATIONS (PHASE 3)
# ----------------------------------------------------

@app.route('/driver')
@login_required(roles=['driver', 'admin'])
def driver_portal():
    user = session.get('user')
    van_id = session.get('van_id') or (user.get('van_id') if user else 1) or 1

    conn = get_db()
    van = conn.execute("SELECT * FROM vans WHERE id = ?", (van_id,)).fetchone()
    if not van:
        van = conn.execute("SELECT * FROM vans LIMIT 1").fetchone()
        van_id = van['id'] if van else 1

    # Shift status for today
    shift = conn.execute("""
        SELECT * FROM driver_shifts 
        WHERE van_id = ? AND shift_date = date('now')
        ORDER BY id DESC LIMIT 1
    """, (van_id,)).fetchone()

    stops = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment, h.phone
        FROM pickups p
        LEFT JOIN households h ON p.household_id = h.id
        WHERE (p.assigned_van_id = ? OR (p.assigned_van_id IS NULL AND p.pickup_zone <= 2))
        ORDER BY p.id ASC
    """, (van_id,)).fetchall()

    stops_list = []
    for s in stops:
        s_dict = dict(s)
        st_rows = conn.execute("SELECT stream_type, estimated_kg FROM pickup_streams WHERE pickup_id = ?", (s['id'],)).fetchall()
        s_dict['streams_list'] = [dict(r) for r in st_rows]
        s_dict['streams_str'] = ", ".join([f"{r['stream_type'].upper()} ({r['estimated_kg']}kg)" for r in st_rows])
        stops_list.append(s_dict)

    total_stops = len(stops_list)
    completed_stops = sum(1 for s in stops_list if s['status'] in ('collected', 'delivered'))
    reported_stops = sum(1 for s in stops_list if s['status'] == 'collection_reported')
    problem_stops = sum(1 for s in stops_list if s['status'] == 'failed')
    pending_stops = sum(1 for s in stops_list if s['status'] == 'pending')
    remaining_stops = total_stops - completed_stops

    next_stop = next((s for s in stops_list if s['status'] == 'pending'), None)
    progress_pct = round((completed_stops / total_stops * 100), 1) if total_stops > 0 else 0.0

    conn.close()

    return render_template('driver_portal.html',
                           van=van,
                           shift=shift,
                           stops=stops_list,
                           total_stops=total_stops,
                           completed_stops=completed_stops,
                           reported_stops=reported_stops,
                           problem_stops=problem_stops,
                           pending_stops=pending_stops,
                           remaining_stops=remaining_stops,
                           next_stop=next_stop,
                           progress_pct=progress_pct)

@app.route('/driver/history')
@login_required(roles=['driver', 'admin'])
def driver_history():
    user = session.get('user')
    van_id = session.get('van_id') or (user.get('van_id') if user else 1) or 1

    conn = get_db()
    van = conn.execute("SELECT * FROM vans WHERE id = ?", (van_id,)).fetchone()
    if not van:
        van = conn.execute("SELECT * FROM vans LIMIT 1").fetchone()

    stops = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment
        FROM pickups p
        LEFT JOIN households h ON p.household_id = h.id
        WHERE (p.assigned_van_id = ? OR p.assigned_van_id IS NULL) AND p.status IN ('collected', 'delivered')
        ORDER BY p.id DESC
    """, (van_id,)).fetchall()

    stops_list = []
    total_kg = 0.0
    for s in stops:
        s_dict = dict(s)
        streams = conn.execute("SELECT stream_type, estimated_kg FROM pickup_streams WHERE pickup_id = ?", (s['id'],)).fetchall()
        s_dict['streams'] = [dict(st) for st in streams]
        total_kg += (s['total_kg'] or sum(st['estimated_kg'] for st in streams))
        stops_list.append(s_dict)

    conn.close()

    return render_template('driver_history.html', van=van, stops=stops_list, total_kg=round(total_kg, 1))

@app.route('/api/driver/start-shift', methods=['POST'])
@login_required(roles=['driver', 'admin'])
def api_driver_start_shift():
    user = session.get('user')
    van_id = session.get('van_id') or (user.get('van_id') if user else 1) or 1

    conn = get_db()
    cursor = conn.cursor()

    existing = cursor.execute("""
        SELECT * FROM driver_shifts WHERE van_id = ? AND shift_date = date('now')
    """, (van_id,)).fetchone()

    if existing:
        cursor.execute("""
            UPDATE driver_shifts 
            SET status = 'active', start_time = COALESCE(start_time, datetime('now'))
            WHERE id = ?
        """, (existing['id'],))
        shift_id = existing['id']
    else:
        cursor.execute("""
            INSERT INTO driver_shifts (driver_id, van_id, shift_date, start_time, status)
            VALUES (?, ?, date('now'), datetime('now'), 'active')
        """, (session.get('user_id'), van_id))
        shift_id = cursor.lastrowid

    cursor.execute("UPDATE vans SET status = 'active' WHERE id = ?", (van_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Shift started! Drive safely.', 'shift_id': shift_id})

@app.route('/api/driver/end-shift', methods=['POST'])
@login_required(roles=['driver', 'admin'])
def api_driver_end_shift():
    user = session.get('user')
    van_id = session.get('van_id') or (user.get('van_id') if user else 1) or 1

    conn = get_db()
    cursor = conn.cursor()

    # Calculate real shift metrics from database
    stops = cursor.execute("""
        SELECT p.id, p.status, COALESCE(p.total_kg, 0) as kg
        FROM pickups p
        WHERE p.assigned_van_id = ?
    """, (van_id,)).fetchall()

    total_stops = len(stops)
    collected_count = sum(1 for s in stops if s['status'] in ('collected', 'delivered'))
    reported_count = sum(1 for s in stops if s['status'] == 'collection_reported')
    problem_count = sum(1 for s in stops if s['status'] == 'failed')
    delivered_count = sum(1 for s in stops if s['status'] == 'delivered')

    stream_sum = cursor.execute("""
        SELECT COALESCE(SUM(ps.estimated_kg), 0)
        FROM pickup_streams ps
        JOIN pickups p ON ps.pickup_id = p.id
        WHERE p.assigned_van_id = ? AND p.status IN ('collected', 'delivered', 'collection_reported')
    """, (van_id,)).fetchone()[0]

    latest_route = cursor.execute("""
        SELECT * FROM routes WHERE van_id = ? ORDER BY id DESC LIMIT 1
    """, (van_id,)).fetchone()

    route_dist = latest_route['opt_dist_km'] if latest_route else 8.4
    saved_pct = latest_route['saved_pct'] if latest_route else 35.0

    existing = cursor.execute("""
        SELECT * FROM driver_shifts WHERE van_id = ? AND shift_date = date('now')
    """, (van_id,)).fetchone()

    if existing:
        cursor.execute("""
            UPDATE driver_shifts
            SET status = 'completed', end_time = datetime('now'),
                total_stops = ?, collected_count = ?, reported_count = ?,
                problem_count = ?, delivered_count = ?, waste_kg = ?,
                route_dist_km = ?, saved_pct = ?
            WHERE id = ?
        """, (total_stops, collected_count, reported_count, problem_count, delivered_count, round(stream_sum, 1), route_dist, saved_pct, existing['id']))
    else:
        cursor.execute("""
            INSERT INTO driver_shifts (driver_id, van_id, shift_date, start_time, end_time, status,
                                      total_stops, collected_count, reported_count, problem_count, delivered_count, waste_kg, route_dist_km, saved_pct)
            VALUES (?, ?, date('now'), datetime('now', '-4 hours'), datetime('now'), 'completed',
                    ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session.get('user_id'), van_id, total_stops, collected_count, reported_count, problem_count, delivered_count, round(stream_sum, 1), route_dist, saved_pct))

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': 'Shift completed! Summary generated.',
        'summary': {
            'total_stops': total_stops,
            'collected_count': collected_count,
            'reported_count': reported_count,
            'problem_count': problem_count,
            'delivered_count': delivered_count,
            'waste_kg': round(stream_sum, 1),
            'route_dist_km': route_dist,
            'saved_pct': saved_pct
        }
    })

@app.route('/api/driver/notify-nearby/<int:pickup_id>', methods=['POST'])
@login_required(roles=['driver', 'admin'])
def api_driver_notify_nearby(pickup_id):
    conn = get_db()
    cursor = conn.cursor()

    pickup = cursor.execute("""
        SELECT p.*, h.phone, v.van_code 
        FROM pickups p 
        LEFT JOIN households h ON p.household_id = h.id 
        LEFT JOIN vans v ON p.assigned_van_id = v.id 
        WHERE p.id = ?
    """, (pickup_id,)).fetchone()

    if not pickup:
        conn.close()
        return jsonify({'success': False, 'message': 'Pickup not found'}), 404

    phone = pickup['phone'] or '9876543210'
    van_code = pickup['van_code'] or 'SL-VAN-01'
    p_code = pickup['pickup_code'] or format_pickup_code(pickup_id)

    sms_id = log_sms(phone, f"Your NagarLoop collection van {van_code} is nearby for pickup {p_code}.", "truck_nearby", pickup_id, db_conn=conn)
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Citizen notified via simulated SMS: Truck nearby for {p_code}.', 'sms_id': sms_id})

@app.route('/api/driver/report-problem/<int:pickup_id>', methods=['POST'])
@login_required(roles=['driver', 'admin'])
def api_driver_report_problem(pickup_id):
    """Driver reports collection issue (Gate locked, waste unavailable, etc.)"""
    data = request.json or request.form
    reason = data.get('reason', 'Gate locked').strip()
    notes = data.get('notes', '').strip()

    conn = get_db()
    cursor = conn.cursor()

    pickup = cursor.execute("SELECT * FROM pickups WHERE id = ?", (pickup_id,)).fetchone()
    if not pickup:
        conn.close()
        return jsonify({'success': False, 'message': 'Pickup not found'}), 404

    cursor.execute("""
        UPDATE pickups 
        SET status = 'failed', problem_reason = ?, problem_notes = ?
        WHERE id = ?
    """, (reason, notes, pickup_id))

    cursor.execute("""
        INSERT INTO audit_logs (pickup_id, previous_status, new_status, action, actor_type, notes)
        VALUES (?, ?, 'failed', 'driver_report_problem', 'driver', ?)
    """, (pickup_id, pickup['status'], f"Problem: {reason}. {notes}"))

    hh = cursor.execute("SELECT * FROM households WHERE id = ?", (pickup['household_id'],)).fetchone() if pickup['household_id'] else None
    if hh and hh['phone']:
        p_code = pickup['pickup_code'] or format_pickup_code(pickup_id)
        log_sms(hh['phone'], f"Your NagarLoop pickup {p_code} could not be completed ({reason}) and needs rescheduling.", "problem_reported", pickup_id, db_conn=conn)

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Issue reported: {reason}. Ticket sent to Operations Command.'})

# ----------------------------------------------------
# ADMIN SOCIETY MANAGEMENT (PHASE 3)
# ----------------------------------------------------

@app.route('/admin/societies')
@login_required(roles=['admin'])
def admin_societies():
    conn = get_db()
    societies = conn.execute("SELECT * FROM societies ORDER BY id ASC").fetchall()

    soc_list = []
    for s in societies:
        s_dict = dict(s)
        pts = conn.execute("SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE society_id = ?", (s['id'],)).fetchone()[0]
        kg = conn.execute("""
            SELECT COALESCE(SUM(ps.estimated_kg), 0)
            FROM pickup_streams ps
            JOIN pickups p ON ps.pickup_id = p.id
            WHERE p.society_id = ?
        """, (s['id'],)).fetchone()[0]
        total_p = conn.execute("SELECT COUNT(*) FROM pickups WHERE society_id = ?", (s['id'],)).fetchone()[0]
        pending_p = conn.execute("SELECT COUNT(*) FROM pickups WHERE society_id = ? AND status = 'pending'", (s['id'],)).fetchone()[0]
        completed_p = conn.execute("SELECT COUNT(*) FROM pickups WHERE society_id = ? AND status IN ('collected', 'delivered')", (s['id'],)).fetchone()[0]

        s_dict['points'] = pts
        s_dict['total_kg'] = round(kg, 1)
        s_dict['co2e_saved'] = round(kg * 1.42, 1)
        s_dict['total_pickups'] = total_p
        s_dict['pending_pickups'] = pending_p
        s_dict['completed_pickups'] = completed_p
        soc_list.append(s_dict)

    conn.close()
    return render_template('admin_societies.html', societies=soc_list)

@app.route('/admin/societies/<int:society_id>')
@login_required(roles=['admin'])
def admin_society_detail(society_id):
    conn = get_db()
    society = conn.execute("SELECT * FROM societies WHERE id = ?", (society_id,)).fetchone()
    if not society:
        conn.close()
        flash("Housing society not found.", "warning")
        return redirect(url_for('admin_societies'))

    points = conn.execute("SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE society_id = ?", (society_id,)).fetchone()[0]

    # 4-Stream Breakdown
    streams = conn.execute("""
        SELECT ps.stream_type, COALESCE(SUM(ps.estimated_kg), 0) as total_kg
        FROM pickup_streams ps
        JOIN pickups p ON ps.pickup_id = p.id
        WHERE p.society_id = ?
        GROUP BY ps.stream_type
    """, (society_id,)).fetchall()
    streams_dict = {r['stream_type']: round(r['total_kg'], 1) for r in streams}
    wet_kg = streams_dict.get('wet', 0.0)
    dry_kg = streams_dict.get('dry', 0.0)
    ewaste_kg = streams_dict.get('e_waste', 0.0)
    residual_kg = streams_dict.get('residual', 0.0)
    total_diverted = round(wet_kg + dry_kg + ewaste_kg + residual_kg, 1)
    co2e_saved = calculate_co2_impact(wet_kg, dry_kg, ewaste_kg, residual_kg)

    # Pickups history
    pickups = conn.execute("""
        SELECT p.*, v.van_code, v.driver_name
        FROM pickups p
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.society_id = ?
        ORDER BY p.id DESC
    """, (society_id,)).fetchall()

    pickup_list = []
    for p in pickups:
        p_dict = dict(p)
        p_streams = conn.execute("""
            SELECT ps.*, f.name as facility_name, f.facility_type
            FROM pickup_streams ps
            LEFT JOIN facilities f ON ps.facility_id = f.id
            WHERE ps.pickup_id = ?
        """, (p['id'],)).fetchall()
        p_dict['streams'] = [dict(s) for s in p_streams]
        pickup_list.append(p_dict)

    # Problem/dispute history
    issues = conn.execute("""
        SELECT * FROM pickups WHERE society_id = ? AND (status IN ('disputed', 'failed') OR problem_reason IS NOT NULL)
    """, (society_id,)).fetchall()

    conn.close()

    return render_template('admin_society_detail.html',
                           society=society,
                           points=points,
                           total_diverted=total_diverted,
                           wet_kg=wet_kg,
                           dry_kg=dry_kg,
                           ewaste_kg=ewaste_kg,
                           residual_kg=residual_kg,
                           co2e_saved=co2e_saved,
                           pickups=pickup_list,
                           issues=issues)

# ----------------------------------------------------
# ADMIN COMMAND CENTER & OPERATIONS
# ----------------------------------------------------

@app.route('/admin')
@login_required(roles=['admin'])
def admin_dashboard():
    conn = get_db()

    total_pickups = conn.execute("SELECT COUNT(*) FROM pickups").fetchone()[0]
    pending_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'pending'").fetchone()[0]
    reported_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'collection_reported'").fetchone()[0]
    collected_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'collected'").fetchone()[0]
    delivered_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'delivered'").fetchone()[0]
    disputed_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'disputed'").fetchone()[0]
    failed_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'failed'").fetchone()[0]
    active_vans = conn.execute("SELECT COUNT(*) FROM vans WHERE status = 'active'").fetchone()[0]

    total_kg_diverted = conn.execute("SELECT COALESCE(SUM(estimated_kg), 0) FROM pickup_streams").fetchone()[0]
    total_green_points = conn.execute("SELECT COALESCE(SUM(points), 0) FROM points_ledger").fetchone()[0]

    # Operational Performance Rates (P4.4)
    success_rate = round(((collected_pickups + delivered_pickups) / max(1, total_pickups)) * 100, 1)
    failed_rate = round((failed_pickups / max(1, total_pickups)) * 100, 1)
    dispute_rate = round((disputed_pickups / max(1, total_pickups)) * 100, 1)
    delivery_rate = round((delivered_pickups / max(1, (collected_pickups + delivered_pickups))) * 100, 1)

    # Destination Facilities Capacity & Utilization Metrics
    facilities = conn.execute("SELECT * FROM facilities ORDER BY id ASC").fetchall()
    facility_list = []
    alerts = []

    for f in facilities:
        f_dict = dict(f)
        cap = f['capacity_kg'] or 1000.0
        load = f['current_load_kg'] or 0.0
        pct = round((load / cap) * 100, 1)
        status = 'AT CAPACITY' if pct >= 100 else ('NEAR CAPACITY' if pct >= 80 else 'NORMAL')
        f_dict['utilization_pct'] = pct
        f_dict['capacity_status'] = status
        facility_list.append(f_dict)
        if pct >= 80:
            alerts.append({
                'type': 'danger' if pct >= 100 else 'warning',
                'title': f"Facility {status.title()}: {f['name']}",
                'message': f"{f['name']} ({f['facility_type']}) load is {load:.1f} kg / {cap:.1f} kg ({pct}% utilization). Reroute upcoming batches if necessary.",
                'icon': 'fa-solid fa-triangle-exclamation'
            })

    # Operational Alerts (P4.7, P4.8)
    if disputed_pickups > 0:
        alerts.append({
            'type': 'danger',
            'title': 'Disputed Collection Alert',
            'message': f"{disputed_pickups} doorstep collection dispute(s) require supervisor investigation.",
            'icon': 'fa-solid fa-circle-exclamation'
        })

    if failed_pickups > 0:
        alerts.append({
            'type': 'warning',
            'title': 'Unresolved Problem Stops',
            'message': f"{failed_pickups} pickup(s) encountered exceptions (gate locked, unavailable) and need rescheduling.",
            'icon': 'fa-solid fa-clock-rotate-left'
        })

    # Hotspot / Zone Analysis (P4.8)
    zone_counts = conn.execute("""
        SELECT pickup_zone, COUNT(*) as p_count 
        FROM pickups 
        WHERE status IN ('pending', 'failed')
        GROUP BY pickup_zone 
        ORDER BY p_count DESC 
        LIMIT 1
    """).fetchone()
    if zone_counts and zone_counts['p_count'] >= 4:
        alerts.append({
            'type': 'info',
            'title': f"Zone Attention Signal — Zone {zone_counts['pickup_zone']}",
            'message': f"Zone {zone_counts['pickup_zone']} has {zone_counts['p_count']} pending/unresolved collection requests. Consider fleet reassignment.",
            'icon': 'fa-solid fa-map-location-dot'
        })

    # Needs Attention Queue (Disputes, Failed Stops, Unverified Public Reports)
    needs_attention = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment, h.phone, v.van_code
        FROM pickups p
        LEFT JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.status IN ('disputed', 'failed', 'collection_reported') OR (p.is_public = 1 AND p.status = 'pending')
        ORDER BY p.id DESC
    """).fetchall()

    vans = conn.execute("SELECT * FROM vans ORDER BY id ASC").fetchall()

    # Circular Flow Breakdown by Stream (P4.2)
    stream_flow = conn.execute("""
        SELECT stream_type, COUNT(id) as pickup_count, COALESCE(SUM(estimated_kg), 0) as total_kg
        FROM pickup_streams
        GROUP BY stream_type
    """).fetchall()
    stream_summary = {r['stream_type']: {'count': r['pickup_count'], 'kg': round(r['total_kg'], 1)} for r in stream_flow}
    wet_kg = stream_summary.get('wet', {}).get('kg', 0.0)
    dry_kg = stream_summary.get('dry', {}).get('kg', 0.0)
    ewaste_kg = stream_summary.get('e_waste', {}).get('kg', 0.0)
    residual_kg = stream_summary.get('residual', {}).get('kg', 0.0)
    total_co2e = calculate_co2_impact(wet_kg, dry_kg, ewaste_kg, residual_kg)

    # Waste Trend Chart Dataset (P4.3)
    chart_streams = {
        'labels': ['Wet / Compost', 'Dry / MRF', 'E-Waste / Recycler', 'Residual / RDF'],
        'data': [wet_kg, dry_kg, ewaste_kg, residual_kg],
        'colors': ['#2E7D32', '#0288D1', '#F57F17', '#D32F2F']
    }

    # Housing Societies Summary Performance (P4.5)
    societies = conn.execute("""
        SELECT s.*, 
               COALESCE((SELECT SUM(points) FROM points_ledger WHERE society_id = s.id), 0) as green_points,
               COALESCE((SELECT SUM(ps.estimated_kg) FROM pickup_streams ps JOIN pickups p ON ps.pickup_id = p.id WHERE p.society_id = s.id), 0) as total_kg,
               COALESCE((SELECT COUNT(*) FROM pickups WHERE society_id = s.id), 0) as pickup_count
        FROM societies s
        ORDER BY total_kg DESC
    """).fetchall()
    society_list = []
    for s in societies:
        s_dict = dict(s)
        s_dict['co2e_saved'] = round(s_dict['total_kg'] * 0.85, 1)
        society_list.append(s_dict)

    # Leaderboard
    leaderboard = conn.execute("""
        SELECT h.household_code, h.name, h.street_segment, SUM(pl.points) as total_points,
               COUNT(DISTINCT pl.pickup_id) as total_pickups
        FROM households h
        JOIN points_ledger pl ON h.id = pl.household_id
        GROUP BY h.id
        ORDER BY total_points DESC
        LIMIT 10
    """).fetchall()

    # Notification & SMS Simulation Log
    sms_logs = conn.execute("""
        SELECT s.*, p.pickup_code 
        FROM sms_logs s 
        LEFT JOIN pickups p ON s.pickup_id = p.id 
        ORDER BY s.id DESC 
        LIMIT 25
    """).fetchall()

    conn.close()

    return render_template('admin_dashboard.html',
                           total=total_pickups,
                           pending=pending_pickups,
                           reported=reported_pickups,
                           collected=collected_pickups,
                           delivered=delivered_pickups,
                           disputed=disputed_pickups,
                           failed=failed_pickups,
                           active_vans=active_vans,
                           success_rate=success_rate,
                           failed_rate=failed_rate,
                           dispute_rate=dispute_rate,
                           delivery_rate=delivery_rate,
                           total_kg_diverted=round(total_kg_diverted, 1),
                           total_green_points=total_green_points,
                           total_co2e=total_co2e,
                           facilities=facility_list,
                           alerts=alerts,
                           needs_attention=needs_attention,
                           vans=vans,
                           leaderboard=leaderboard,
                           stream_summary=stream_summary,
                           chart_streams=chart_streams,
                           societies=society_list,
                           sms_logs=sms_logs)

@app.route('/admin/reports')
@login_required(roles=['admin'])
def admin_reports():
    """Municipal Operational Summary Report with Printable Layout (Phase 4 Spec)"""
    conn = get_db()
    
    total_pickups = conn.execute("SELECT COUNT(*) FROM pickups").fetchone()[0]
    pending_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'pending'").fetchone()[0]
    collected_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'collected'").fetchone()[0]
    delivered_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'delivered'").fetchone()[0]
    disputed_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'disputed'").fetchone()[0]
    failed_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'failed'").fetchone()[0]
    
    stream_flow = conn.execute("""
        SELECT stream_type, COUNT(id) as pickup_count, COALESCE(SUM(estimated_kg), 0) as total_kg
        FROM pickup_streams
        GROUP BY stream_type
    """).fetchall()
    stream_dict = {r['stream_type']: round(r['total_kg'], 1) for r in stream_flow}
    wet_kg = stream_dict.get('wet', 0.0)
    dry_kg = stream_dict.get('dry', 0.0)
    ewaste_kg = stream_dict.get('e_waste', 0.0)
    residual_kg = stream_dict.get('residual', 0.0)
    total_kg = round(wet_kg + dry_kg + ewaste_kg + residual_kg, 1)
    co2e_estimate = calculate_co2_impact(wet_kg, dry_kg, ewaste_kg, residual_kg)
    
    total_points = conn.execute("SELECT COALESCE(SUM(points), 0) FROM points_ledger").fetchone()[0]
    facilities = conn.execute("SELECT * FROM facilities ORDER BY id ASC").fetchall()
    
    issues = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment, v.van_code
        FROM pickups p
        LEFT JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.status IN ('disputed', 'failed')
        ORDER BY p.id DESC
    """).fetchall()
    
    conn.close()
    
    success_rate = round(((collected_pickups + delivered_pickups) / max(1, total_pickups)) * 100, 1)
    
    return render_template('admin_reports.html',
                           total=total_pickups,
                           pending=pending_pickups,
                           collected=collected_pickups,
                           delivered=delivered_pickups,
                           disputed=disputed_pickups,
                           failed=failed_pickups,
                           success_rate=success_rate,
                           wet_kg=wet_kg,
                           dry_kg=dry_kg,
                           ewaste_kg=ewaste_kg,
                           residual_kg=residual_kg,
                           total_kg=total_kg,
                           co2e_estimate=co2e_estimate,
                           total_points=total_points,
                           facilities=facilities,
                           issues=issues,
                           generated_at=time.strftime('%d %B %Y, %I:%M %p'))

@app.route('/admin/export-csv')
@login_required(roles=['admin'])
def admin_export_csv():
    """Export operational pickups dataset as CSV download (Phase 4 Spec)"""
    conn = get_db()
    pickups = conn.execute("""
        SELECT p.id, p.pickup_code, p.is_public, p.is_society, p.status, p.pickup_zone, p.total_kg,
               p.earned_points, p.problem_reason, p.created_at, p.rescheduled_date,
               h.household_code, h.name as citizen_name, h.street_segment, h.phone,
               s.name as society_name, s.society_code,
               v.van_code, v.driver_name
        FROM pickups p
        LEFT JOIN households h ON p.household_id = h.id
        LEFT JOIN societies s ON p.society_id = s.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        ORDER BY p.id ASC
    """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Pickup_ID', 'Reference_Code', 'Type', 'Entity_Name', 'Code', 'Street_Address',
        'Phone', 'Zone', 'Assigned_Van', 'Driver', 'Status', 'Total_KG', 'Green_Points',
        'Issue_Reason', 'Rescheduled_Date', 'Created_At'
    ])

    for p in pickups:
        p_type = 'Public Report' if p['is_public'] else ('Housing Society' if p['is_society'] else 'Individual Household')
        name = p['society_name'] if p['is_society'] else (p['citizen_name'] or 'Public Reporter')
        code = p['society_code'] if p['is_society'] else (p['household_code'] or 'PUBLIC')
        writer.writerow([
            p['id'],
            p['pickup_code'] or format_pickup_code(p['id']),
            p_type,
            name,
            code,
            p['street_segment'] or 'Navrangpura',
            p['phone'] or 'N/A',
            f"Zone {p['pickup_zone']}",
            p['van_code'] or 'Unassigned',
            p['driver_name'] or 'Unassigned',
            p['status'],
            p['total_kg'] or 0.0,
            p['earned_points'] or 0,
            p['problem_reason'] or '',
            p['rescheduled_date'] or '',
            p['created_at'] or ''
        ])

    conn.close()
    mem_file = io.BytesIO()
    mem_file.write(output.getvalue().encode('utf-8'))
    mem_file.seek(0)
    return send_file(mem_file, mimetype='text/csv', as_attachment=True, download_name='nagarloop_operations_report.csv')

@app.route('/api/admin/reschedule/<int:pickup_id>', methods=['POST'])
@login_required(roles=['admin'])
def api_admin_reschedule(pickup_id):
    """Admin reschedules a failed or problem pickup"""
    data = request.json or request.form
    new_date = data.get('date', 'Tomorrow Morning').strip()
    new_window = data.get('window', '07:30 AM - 09:30 AM').strip()
    van_id = data.get('van_id')

    conn = get_db()
    cursor = conn.cursor()

    pickup = cursor.execute("SELECT * FROM pickups WHERE id = ?", (pickup_id,)).fetchone()
    if not pickup:
        conn.close()
        return jsonify({'success': False, 'message': 'Pickup not found'}), 404

    cursor.execute("""
        UPDATE pickups 
        SET status = 'pending', rescheduled_date = ?, rescheduled_window = ?, assigned_van_id = COALESCE(?, assigned_van_id)
        WHERE id = ?
    """, (new_date, new_window, van_id, pickup_id))

    cursor.execute("""
        INSERT INTO audit_logs (pickup_id, previous_status, new_status, action, actor_type, notes)
        VALUES (?, ?, 'pending', 'admin_reschedule', 'admin', ?)
    """, (pickup_id, pickup['status'], f"Rescheduled for {new_date} ({new_window})"))

    hh = cursor.execute("SELECT * FROM households WHERE id = ?", (pickup['household_id'],)).fetchone() if pickup['household_id'] else None
    if hh and hh['phone']:
        p_code = pickup['pickup_code'] or format_pickup_code(pickup_id)
        log_sms(hh['phone'], f"NagarLoop: Your pickup {p_code} has been rescheduled for {new_date} ({new_window}).", "pickup_rescheduled", pickup_id, db_conn=conn)

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Pickup rescheduled for {new_date} ({new_window}).'})

@app.route('/api/admin/verify-public/<int:pickup_id>', methods=['POST'])
@login_required(roles=['admin'])
def api_admin_verify_public(pickup_id):
    """Admin verifies public waste report and assigns eligible Green Points"""
    conn = get_db()
    cursor = conn.cursor()

    pickup = cursor.execute("SELECT * FROM pickups WHERE id = ? AND is_public = 1", (pickup_id,)).fetchone()
    if not pickup:
        conn.close()
        return jsonify({'success': False, 'message': 'Public report not found'}), 404

    total_kg = pickup['total_kg'] or 10.0
    pts = calculate_green_points({'wet': total_kg}, is_public=True)

    cursor.execute("""
        UPDATE pickups SET earned_points = ? WHERE id = ?
    """, (pts, pickup_id))

    cursor.execute("""
        INSERT INTO audit_logs (pickup_id, previous_status, new_status, action, actor_type, notes)
        VALUES (?, 'pending', 'pending', 'admin_verify_public', 'admin', ?)
    """, (pickup_id, f"Public report verified. {pts} points approved for collection."))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Public report verified. +{pts} points allocated upon collection.'})

# ----------------------------------------------------
# LEADERBOARD & MANIFEST
# ----------------------------------------------------

@app.route('/leaderboard')
def public_leaderboard():
    """Upgraded Green Champions Leaderboard with Period & Entity Filters"""
    period = request.args.get('period', 'all_time')
    category = request.args.get('category', 'all')

    conn = get_db()
    date_filter = ""
    if period == 'this_week':
        date_filter = "WHERE pl.created_at >= datetime('now', '-7 days')"
    elif period == 'this_month':
        date_filter = "WHERE pl.created_at >= datetime('now', '-30 days')"

    if category == 'societies':
        rows = conn.execute(f"""
            SELECT s.name as entity_name, s.society_code as code, s.address as locality,
                   COALESCE(SUM(pl.points), 0) as total_points,
                   COUNT(DISTINCT pl.pickup_id) as total_pickups,
                   1 as is_society
            FROM societies s
            LEFT JOIN points_ledger pl ON s.id = pl.society_id {date_filter.replace('WHERE', 'AND') if date_filter else ''}
            GROUP BY s.id
            ORDER BY total_points DESC
        """).fetchall()
    else:
        rows = conn.execute(f"""
            SELECT h.name as entity_name, h.household_code as code, h.street_segment as locality,
                   COALESCE(SUM(pl.points), 0) as total_points,
                   COUNT(DISTINCT pl.pickup_id) as total_pickups,
                   h.is_society
            FROM households h
            LEFT JOIN points_ledger pl ON h.id = pl.household_id {date_filter.replace('WHERE', 'AND') if date_filter else ''}
            GROUP BY h.id
            ORDER BY total_points DESC
            LIMIT 25
        """).fetchall()

    leaderboard = [dict(r) for r in rows]
    conn.close()

    return render_template('leaderboard.html', leaderboard=leaderboard, period=period, category=category)

@app.route('/manifest/<int:pickup_id>')
def manifest_page(pickup_id):
    conn = get_db()
    pickup = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.phone, h.street_segment,
               v.van_code, v.driver_name
        FROM pickups p
        LEFT JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.id = ?
    """, (pickup_id,)).fetchone()

    if not pickup:
        conn.close()
        return "Manifest Not Found", 404

    streams = conn.execute("""
        SELECT ps.*, f.name as facility_name, f.facility_type, f.stream_type
        FROM pickup_streams ps
        LEFT JOIN facilities f ON ps.facility_id = f.id
        WHERE ps.pickup_id = ?
    """, (pickup_id,)).fetchall()

    ledger = conn.execute("SELECT * FROM points_ledger WHERE pickup_id = ?", (pickup_id,)).fetchone()
    audit_trail = conn.execute("SELECT * FROM audit_logs WHERE pickup_id = ? ORDER BY id DESC", (pickup_id,)).fetchall()
    conn.close()

    qr_data_uri = generate_qr_base64(pickup_id, request.host_url)
    total_kg = pickup['total_kg'] or sum([s['estimated_kg'] for s in streams])
    points_earned = pickup['earned_points'] or (ledger['points'] if ledger else 20)

    return render_template('manifest_view.html',
                           pickup=pickup,
                           streams=streams,
                           total_kg=round(total_kg, 1),
                           points_earned=points_earned,
                           qr_data_uri=qr_data_uri,
                           audit_trail=audit_trail)

@app.route('/qr/<int:pickup_id>')
def qr_image(pickup_id):
    manifest_url = f"{request.host_url.rstrip('/')}/manifest/{pickup_id}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(manifest_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# ----------------------------------------------------
# DISPATCH & ROUTE OPTIMIZATION
# ----------------------------------------------------

@app.route('/admin/dispatch')
@login_required(roles=['admin'])
def admin_dispatch():
    stream_filter = request.args.get('stream', 'all')
    van_filter = request.args.get('van', '1')

    conn = get_db()
    vans = conn.execute("SELECT * FROM vans ORDER BY id ASC").fetchall()
    selected_van = conn.execute("SELECT * FROM vans WHERE id = ?", (van_filter,)).fetchone() or vans[0]

    query = """
        SELECT p.*, h.household_code, h.name as citizen_name, h.phone, h.street_segment, v.van_code
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE (p.assigned_van_id = ? OR (p.assigned_van_id IS NULL AND p.pickup_zone <= 2))
    """
    params = [selected_van['id']]
    if stream_filter != 'all':
        query += " AND EXISTS (SELECT 1 FROM pickup_streams ps WHERE ps.pickup_id = p.id AND ps.stream_type = ?)"
        params.append(stream_filter)

    query += " ORDER BY p.id ASC LIMIT 10"
    raw_stops = conn.execute(query, tuple(params)).fetchall()

    facility = conn.execute("SELECT * FROM facilities LIMIT 1").fetchone()
    fac_pos = (facility['lat'], facility['lng']) if facility else None
    van_pos = (selected_van['lat'], selected_van['lng'])

    stops_data = []
    for s in raw_stops:
        st_rows = conn.execute("SELECT stream_type, estimated_kg, status FROM pickup_streams WHERE pickup_id = ?", (s['id'],)).fetchall()
        streams_str = ", ".join([f"{r['stream_type'].upper()} ({r['estimated_kg']}kg)" for r in st_rows])
        stops_data.append({
            'id': s['id'], 'lat': s['lat'], 'lng': s['lng'],
            'household_code': s['household_code'], 'name': s['citizen_name'],
            'phone': s['phone'], 'street': s['street_segment'],
            'bin_score': s['bin_score'], 'zone': s['pickup_zone'],
            'status': s['status'], 'streams': streams_str,
            'streams_list': [dict(r) for r in st_rows]
        })

    naive_dist, opt_dist, saved_pct, ordered_stops = calculate_route_metrics(van_pos, stops_data, fac_pos)

    total_stops = len(ordered_stops)
    collected_stops = sum(1 for s in ordered_stops if s['status'] in ['collected', 'delivered'])
    delivered_stops = sum(1 for s in ordered_stops if s['status'] == 'delivered')
    progress_pct = round((collected_stops / total_stops * 100), 1) if total_stops > 0 else 0.0
    next_stop = next((s for s in ordered_stops if s['status'] == 'pending'), None)
    is_route_complete = (collected_stops == total_stops and total_stops > 0)

    disputed_pickups = conn.execute("""
        SELECT p.id, p.household_id, p.status, p.bin_score, h.household_code, h.name as citizen_name,
               h.phone, h.street_segment, v.van_code, v.driver_name
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.status = 'disputed'
        ORDER BY p.id DESC
    """).fetchall()

    conn.close()

    return render_template('admin_dispatch.html',
                           selected_van=selected_van,
                           vans=vans,
                           stops=ordered_stops,
                           total_stops=total_stops,
                           collected_stops=collected_stops,
                           delivered_stops=delivered_stops,
                           progress_pct=progress_pct,
                           next_stop=next_stop,
                           is_route_complete=is_route_complete,
                           disputed_pickups=disputed_pickups,
                           naive_dist=naive_dist,
                           opt_dist=opt_dist,
                           saved_pct=saved_pct,
                           facility=facility,
                           stream_filter=stream_filter)

@app.route('/admin/route/<int:van_id>')
@login_required(roles=['admin'])
def admin_route_optimization(van_id):
    stream_filter = request.args.get('stream', 'all')
    zone_filter = request.args.get('zone', 'all')

    conn = get_db()
    van = conn.execute("SELECT * FROM vans WHERE id = ?", (van_id,)).fetchone()
    if not van:
        conn.close()
        return "Van not found", 404

    query = """
        SELECT DISTINCT p.id, p.lat, p.lng, p.bin_score, p.status, p.pickup_zone,
                        h.household_code, h.name as citizen_name, h.street_segment
        FROM pickups p
        LEFT JOIN households h ON p.household_id = h.id
    """
    params = []
    where_clauses = []
    
    if stream_filter != 'all':
        query += " JOIN pickup_streams ps ON p.id = ps.pickup_id "
        where_clauses.append("ps.stream_type = ?")
        params.append(stream_filter)

    if zone_filter != 'all':
        where_clauses.append("p.pickup_zone = ?")
        params.append(int(zone_filter))

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY p.id ASC LIMIT 12"
    raw_stops = conn.execute(query, tuple(params)).fetchall()

    stops_data = []
    for s in raw_stops:
        st_rows = conn.execute("SELECT stream_type, estimated_kg FROM pickup_streams WHERE pickup_id = ?", (s['id'],)).fetchall()
        streams_str = ", ".join([f"{r['stream_type'].upper()} ({r['estimated_kg']}kg)" for r in st_rows])
        stops_data.append({
            'id': s['id'], 'lat': s['lat'], 'lng': s['lng'],
            'household_code': s['household_code'] or 'SOC-001', 'name': s['citizen_name'] or 'Citizen',
            'street': s['street_segment'] or 'Navrangpura', 'bin_score': s['bin_score'],
            'zone': s['pickup_zone'], 'streams': streams_str
        })

    all_vans = conn.execute("SELECT * FROM vans ORDER BY id ASC").fetchall()
    facility = None
    if stream_filter != 'all':
        facility = conn.execute("SELECT * FROM facilities WHERE stream_type = ?", (stream_filter,)).fetchone()
    if not facility:
        facility = conn.execute("SELECT * FROM facilities LIMIT 1").fetchone()
    conn.close()

    fac_pos = (facility['lat'], facility['lng']) if facility else None
    van_pos = (van['lat'], van['lng'])
    naive_dist, opt_dist, saved_pct, ordered_stops = calculate_route_metrics(van_pos, stops_data, fac_pos)

    if len(ordered_stops) == 0:
        explanation = "No pickups in this batch matching the selected stream and zone filters."
    elif len(ordered_stops) == 1:
        saved_pct = 0.0
        explanation = "Route optimization not required for a single stop."
    else:
        explanation = f"Recommended batch for {van['van_code']}: {len(ordered_stops)} stops optimized using Nearest-Neighbor heuristic, saving {saved_pct}% travel distance."

    return render_template('admin_route.html',
                           van=van,
                           all_vans=all_vans,
                           stops=ordered_stops,
                           naive_dist=naive_dist,
                           opt_dist=opt_dist,
                           saved_pct=saved_pct,
                           route_status='recommended',
                           stream_filter=stream_filter,
                           zone_filter=zone_filter,
                           explanation=explanation,
                           facility=facility)

@app.route('/api/route/recalculate', methods=['POST'])
@login_required(roles=['admin'])
def api_route_recalculate():
    data = request.json or {}
    van_id = data.get('van_id', 1)
    stream_type = data.get('stream_type', 'all')
    pickup_ids = data.get('pickup_ids', [])

    conn = get_db()
    van = conn.execute("SELECT * FROM vans WHERE id = ?", (van_id,)).fetchone()
    if not van:
        conn.close()
        return jsonify({'success': False, 'message': 'Van not found'}), 404

    facility = None
    if stream_type != 'all':
        facility = conn.execute("SELECT * FROM facilities WHERE stream_type = ?", (stream_type,)).fetchone()
    if not facility:
        facility = conn.execute("SELECT * FROM facilities LIMIT 1").fetchone()

    fac_pos = (facility['lat'], facility['lng']) if facility else None
    van_pos = (van['lat'], van['lng'])

    ordered_stops = []
    for pid in pickup_ids:
        p = conn.execute("SELECT id, lat, lng, bin_score, pickup_zone FROM pickups WHERE id = ?", (pid,)).fetchone()
        if p:
            ordered_stops.append(dict(p))

    conn.close()

    if not ordered_stops:
        return jsonify({
            'success': True,
            'naive_dist_km': 0.0,
            'custom_dist_km': 0.0,
            'saved_pct': 0.0,
            'explanation': 'No pickups in batch.'
        })

    # Calculate naive distance (in natural ID order)
    natural_order = sorted(ordered_stops, key=lambda x: x['id'])
    naive_dist = 0.0
    curr = van_pos
    for s in natural_order:
        naive_dist += haversine(curr[0], curr[1], s['lat'], s['lng'])
        curr = (s['lat'], s['lng'])
    if fac_pos:
        naive_dist += haversine(curr[0], curr[1], fac_pos[0], fac_pos[1])

    # Calculate customized distance (in current order of pickup_ids)
    custom_dist = 0.0
    curr = van_pos
    for s in ordered_stops:
        custom_dist += haversine(curr[0], curr[1], s['lat'], s['lng'])
        curr = (s['lat'], s['lng'])
    if fac_pos:
        custom_dist += haversine(curr[0], curr[1], fac_pos[0], fac_pos[1])

    saved_pct = 0.0
    if len(ordered_stops) > 1 and naive_dist > 0:
        saved_pct = round(max(0.0, ((naive_dist - custom_dist) / naive_dist) * 100), 1)

    return jsonify({
        'success': True,
        'naive_dist_km': round(naive_dist, 2),
        'custom_dist_km': round(custom_dist, 2),
        'saved_pct': saved_pct,
        'stop_count': len(ordered_stops)
    })

@app.route('/api/route/apply', methods=['POST'])
@login_required(roles=['admin'])
def api_route_apply():
    data = request.json or {}
    van_id = data.get('van_id')
    stream_type = data.get('stream_type', 'all')
    zone = data.get('zone', 'all')
    pickup_ids = data.get('pickup_ids', [])
    naive_dist = data.get('naive_dist', 0.0)
    opt_dist = data.get('opt_dist', 0.0)
    saved_pct = data.get('saved_pct', 0.0)

    if not van_id or not pickup_ids:
        return jsonify({'success': False, 'message': 'Missing van ID or stop sequence'}), 400

    conn = get_db()
    cursor = conn.cursor()

    van = cursor.execute("SELECT * FROM vans WHERE id = ?", (van_id,)).fetchone()
    if not van:
        conn.close()
        return jsonify({'success': False, 'message': 'Van not found'}), 404

    zone_val = int(zone) if zone != 'all' else 1
    cursor.execute("""
        INSERT INTO routes (van_id, stream_type, pickup_zone, status, naive_dist_km, opt_dist_km, saved_pct, stop_order_json, explanation, applied_at)
        VALUES (?, ?, ?, 'applied', ?, ?, ?, ?, ?, datetime('now'))
    """, (van_id, stream_type, zone_val, naive_dist, opt_dist, saved_pct, json.dumps(pickup_ids), f"Applied route batch with {len(pickup_ids)} stops for {van['van_code']}"))
    route_id = cursor.lastrowid

    # Assign van to these pickups
    for pid in pickup_ids:
        cursor.execute("UPDATE pickups SET assigned_van_id = ? WHERE id = ?", (van_id, pid))
        cursor.execute("""
            INSERT INTO audit_logs (pickup_id, previous_status, new_status, action, actor_type, notes)
            VALUES (?, 'pending', 'pending', 'route_assigned', 'admin', ?)
        """, (pid, f"Assigned to {van['van_code']} (Route Batch #{route_id})"))

    cursor.execute("UPDATE vans SET status = 'active' WHERE id = ?", (van_id,))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': f"Route batch #{route_id} applied! {len(pickup_ids)} stops assigned to {van['van_code']} ({van['driver_name']}).",
        'route_id': route_id
    })

# ----------------------------------------------------
# REST API ENDPOINTS
# ----------------------------------------------------

@app.route('/api/pickups')
def api_pickups():
    conn = get_db()
    pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment, v.van_code
        FROM pickups p
        LEFT JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        ORDER BY p.id ASC
    """).fetchall()

    result = []
    for p in pickups:
        p_dict = dict(p)
        p_dict['address'] = p['address'] or p['street_segment'] or 'Address not available'
        streams = conn.execute("""
            SELECT ps.stream_type, ps.estimated_kg, ps.status, f.name as facility_name, f.facility_type
            FROM pickup_streams ps
            LEFT JOIN facilities f ON ps.facility_id = f.id
            WHERE ps.pickup_id = ?
        """, (p['id'],)).fetchall()
        p_dict['streams'] = [dict(s) for s in streams]
        result.append(p_dict)
    conn.close()
    return jsonify({'pickups': result})

@app.route('/api/vans')
def api_vans():
    conn = get_db()
    vans = conn.execute("SELECT * FROM vans ORDER BY id ASC").fetchall()
    conn.close()
    return jsonify({'vans': [dict(v) for v in vans]})

@app.route('/api/facilities')
def api_facilities():
    conn = get_db()
    facilities = conn.execute("SELECT * FROM facilities ORDER BY id ASC").fetchall()
    conn.close()
    return jsonify({'facilities': [dict(f) for f in facilities]})

@app.route('/api/citizen/verify/<int:pickup_id>', methods=['POST'])
@login_required(roles=['citizen', 'admin'])
def api_citizen_verify(pickup_id):
    """Citizen confirms or disputes doorstep collection"""
    data = request.json or request.form
    action = data.get('action') # 'confirm' or 'dispute'

    conn = get_db()
    cursor = conn.cursor()

    current = cursor.execute("SELECT * FROM pickups WHERE id = ?", (pickup_id,)).fetchone()
    if not current:
        conn.close()
        return jsonify({'success': False, 'message': f'Pickup #{pickup_id} not found'}), 404

    curr_status = current['status']
    if curr_status != 'collection_reported':
        conn.close()
        return jsonify({'success': False, 'message': f'Only collection_reported pickups can be verified. Current: {curr_status}'}), 400

    if action == 'confirm':
        new_status = 'collected'
        action_name = 'citizen_confirm'
        notes = 'Citizen confirmed waste collection'
    elif action == 'dispute':
        new_status = 'disputed'
        action_name = 'citizen_dispute'
        notes = 'Citizen disputed: Waste was NOT collected'
    else:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid verification action'}), 400

    cursor.execute("UPDATE pickups SET status = ? WHERE id = ?", (new_status, pickup_id))
    cursor.execute("UPDATE pickup_streams SET status = ? WHERE pickup_id = ?", (new_status, pickup_id))
    cursor.execute("""
        INSERT INTO audit_logs (pickup_id, previous_status, new_status, action, actor_type, notes)
        VALUES (?, 'collection_reported', ?, ?, 'citizen', ?)
    """, (pickup_id, new_status, action_name, notes))

    conn.commit()
    conn.close()

    msg = "🎉 Thank you! Your waste collection is confirmed." if action == 'confirm' else "⚠ Dispute recorded. Municipal team notified."
    return jsonify({'success': True, 'message': msg, 'new_status': new_status})

@app.route('/api/status/<int:pickup_id>', methods=['POST'])
@login_required()
def api_update_status(pickup_id):
    user = session.get('user')
    user_role = session.get('role') or (user.get('role') if user else 'citizen')

    data = request.json or request.form
    action = data.get('action')
    new_status = data.get('status')

    if action == 'report_collection':
        if user_role not in ['driver', 'admin']:
            return jsonify({'success': False, 'message': 'Access denied: Only drivers can report collections.'}), 403
        new_status = 'collection_reported'
    elif action in ['citizen_confirm', 'citizen_dispute']:
        if user_role not in ['citizen', 'admin']:
            return jsonify({'success': False, 'message': 'Access denied: Only citizens can confirm collections.'}), 403
        new_status = 'collected' if action == 'citizen_confirm' else 'disputed'
    elif action in ['admin_confirm', 'admin_reopen', 'mark_delivered', 'reopen_delivered']:
        if user_role not in ['admin']:
            return jsonify({'success': False, 'message': 'Access denied: Only municipal administrators can perform this operational action.'}), 403
        if action == 'admin_confirm':
            new_status = 'collected'
        elif action == 'admin_reopen':
            new_status = 'pending'
        elif action == 'mark_delivered':
            new_status = 'delivered'
        elif action == 'reopen_delivered':
            new_status = 'collected'

    if not new_status or new_status not in ['pending', 'collection_reported', 'disputed', 'collected', 'delivered', 'failed']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400

    conn = get_db()
    cursor = conn.cursor()

    current = cursor.execute("SELECT * FROM pickups WHERE id = ?", (pickup_id,)).fetchone()
    if not current:
        conn.close()
        return jsonify({'success': False, 'message': 'Pickup not found'}), 404

    curr_status = current['status']
    actor_type = 'operator'
    delivered_timestamp = None

    if new_status == 'delivered':
        delivered_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute("UPDATE pickups SET status = ? WHERE id = ?", (new_status, pickup_id))
    cursor.execute("""
        UPDATE pickup_streams SET status = ?, delivered_at = ? WHERE pickup_id = ?
    """, (new_status, delivered_timestamp, pickup_id))

    cursor.execute("""
        INSERT INTO audit_logs (pickup_id, previous_status, new_status, action, actor_type, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (pickup_id, curr_status, new_status, action or 'status_update', actor_type, f"Updated to {new_status}"))

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'✓ Pickup #{pickup_id} updated to {new_status}',
        'pickup_id': pickup_id,
        'new_status': new_status
    })

# ----------------------------------------------------
# GUJARAT LOCATION & GEOCODING APIS
# ----------------------------------------------------

LOCATION_SEARCH_CACHE = {}
LOCATION_REVERSE_CACHE = {}

GUJARAT_LOCAL_GAZETTEER = [
    {"name": "Navrangpura", "city": "Ahmedabad", "lat": 23.0375, "lng": 72.5520, "display": "Navrangpura, Ahmedabad, Gujarat 380009"},
    {"name": "Commerce Six Roads", "city": "Ahmedabad", "lat": 23.0365, "lng": 72.5535, "display": "Commerce Six Roads, Navrangpura, Ahmedabad, Gujarat 380009"},
    {"name": "Vijay Cross Roads", "city": "Ahmedabad", "lat": 23.0392, "lng": 72.5480, "display": "Vijay Cross Roads, Navrangpura, Ahmedabad, Gujarat 380009"},
    {"name": "Bodakdev", "city": "Ahmedabad", "lat": 23.0372, "lng": 72.5120, "display": "Bodakdev, SG Highway, Ahmedabad, Gujarat 380054"},
    {"name": "Satellite", "city": "Ahmedabad", "lat": 23.0298, "lng": 72.5273, "display": "Satellite Road, Ahmedabad, Gujarat 380015"},
    {"name": "Vastrapur", "city": "Ahmedabad", "lat": 23.0350, "lng": 72.5293, "display": "Vastrapur Lake, Ahmedabad, Gujarat 380015"},
    {"name": "Prahlad Nagar", "city": "Ahmedabad", "lat": 23.0120, "lng": 72.5080, "display": "Prahlad Nagar, SG Highway, Ahmedabad, Gujarat 380015"},
    {"name": "Maninagar", "city": "Ahmedabad", "lat": 22.9978, "lng": 72.6033, "display": "Maninagar East, Ahmedabad, Gujarat 380008"},
    {"name": "Paldi", "city": "Ahmedabad", "lat": 23.0125, "lng": 72.5625, "display": "Paldi Cross Roads, Ahmedabad, Gujarat 380007"},
    {"name": "Ashram Road", "city": "Ahmedabad", "lat": 23.0300, "lng": 72.5700, "display": "Ashram Road, Usmanpura, Ahmedabad, Gujarat 380014"},
    {"name": "Bopal", "city": "Ahmedabad", "lat": 23.0345, "lng": 72.4645, "display": "South Bopal, Ahmedabad, Gujarat 380058"},
    {"name": "Gota", "city": "Ahmedabad", "lat": 23.0980, "lng": 72.5350, "display": "Gota Cross Roads, SG Highway, Ahmedabad, Gujarat 382481"},
    {"name": "Chandkheda", "city": "Ahmedabad", "lat": 23.1100, "lng": 72.5850, "display": "Chandkheda, Ahmedabad, Gujarat 382424"},
    {"name": "Infocity", "city": "Gandhinagar", "lat": 23.1920, "lng": 72.6280, "display": "Infocity, Gandhinagar, Gujarat 382007"},
    {"name": "Sector 21", "city": "Gandhinagar", "lat": 23.2320, "lng": 72.6500, "display": "Sector 21, Gandhinagar, Gujarat 382021"},
    {"name": "GIFT City", "city": "Gandhinagar", "lat": 23.1610, "lng": 72.6840, "display": "GIFT City, Gandhinagar, Gujarat 382355"},
    {"name": "Sector 6", "city": "Gandhinagar", "lat": 23.2150, "lng": 72.6360, "display": "Sector 6, Gandhinagar, Gujarat 382006"},
    {"name": "Athwa Lines", "city": "Surat", "lat": 21.1780, "lng": 72.8050, "display": "Athwa Lines, Surat, Gujarat 395007"},
    {"name": "Adajan", "city": "Surat", "lat": 21.1980, "lng": 72.7950, "display": "Adajan Hazira Road, Surat, Gujarat 395009"},
    {"name": "Vesu", "city": "Surat", "lat": 21.1450, "lng": 72.7750, "display": "VIP Road, Vesu, Surat, Gujarat 395007"},
    {"name": "Varachha", "city": "Surat", "lat": 21.2180, "lng": 72.8650, "display": "Varachha Main Road, Surat, Gujarat 395006"},
    {"name": "Althan", "city": "Surat", "lat": 21.1550, "lng": 72.8100, "display": "Althan Road, Surat, Gujarat 395017"},
    {"name": "Alkapuri", "city": "Vadodara", "lat": 22.3110, "lng": 73.1750, "display": "RC Dutt Road, Alkapuri, Vadodara, Gujarat 390007"},
    {"name": "Gotri", "city": "Vadodara", "lat": 22.3180, "lng": 73.1450, "display": "Gotri Road, Vadodara, Gujarat 390021"},
    {"name": "Fatehgunj", "city": "Vadodara", "lat": 22.3250, "lng": 73.1890, "display": "Fatehgunj Main Road, Vadodara, Gujarat 390002"},
    {"name": "Manjalpur", "city": "Vadodara", "lat": 22.2700, "lng": 73.1950, "display": "Manjalpur Naka, Vadodara, Gujarat 390011"},
    {"name": "Kalawad Road", "city": "Rajkot", "lat": 22.2850, "lng": 70.7680, "display": "Kalawad Road, Rajkot, Gujarat 360005"},
    {"name": "Race Course", "city": "Rajkot", "lat": 22.3020, "lng": 70.7950, "display": "Race Course Ring Road, Rajkot, Gujarat 360001"},
    {"name": "Yagnik Road", "city": "Rajkot", "lat": 22.2960, "lng": 70.7980, "display": "Dr. Yagnik Road, Rajkot, Gujarat 360001"},
    {"name": "University Road", "city": "Rajkot", "lat": 22.2920, "lng": 70.7550, "display": "University Road, Rajkot, Gujarat 360005"},
    {"name": "Waghawadi Road", "city": "Bhavnagar", "lat": 21.7550, "lng": 72.1450, "display": "Waghawadi Road, Bhavnagar, Gujarat 364002"},
    {"name": "Kaliyabid", "city": "Bhavnagar", "lat": 21.7450, "lng": 72.1380, "display": "Kaliyabid, Bhavnagar, Gujarat 364002"},
    {"name": "Digjam", "city": "Jamnagar", "lat": 22.4650, "lng": 70.0650, "display": "Aerodrome Road, Digjam, Jamnagar, Gujarat 361006"},
    {"name": "MG Road", "city": "Junagadh", "lat": 21.5200, "lng": 70.4600, "display": "MG Road, Junagadh, Gujarat 362001"},
    {"name": "Vallabh Vidyanagar", "city": "Anand", "lat": 22.5500, "lng": 72.9300, "display": "Mota Bazaar, Vallabh Vidyanagar, Anand, Gujarat 388120"}
]

@app.route('/api/location/search')
def api_location_search():
    q = request.args.get('q', '').strip()
    request_id = request.args.get('request_id', '')
    if len(q) < 3:
        return jsonify({'success': True, 'results': [], 'request_id': request_id})

    cache_key = q.lower()
    if cache_key in LOCATION_SEARCH_CACHE:
        return jsonify({'success': True, 'results': LOCATION_SEARCH_CACHE[cache_key], 'request_id': request_id})

    results = []
    # 1. Search Local Gazetteer First
    q_words = [w.lower() for w in q.split() if len(w) > 1]
    for item in GUJARAT_LOCAL_GAZETTEER:
        item_text = f"{item['name']} {item['city']} {item['display']}".lower()
        if all(w in item_text for w in q_words) or q.lower() in item_text:
            results.append({
                'title': item['name'],
                'subtitle': f"{item['city']}, Gujarat",
                'display_name': item['display'],
                'lat': item['lat'],
                'lng': item['lng'],
                'source': 'gazetteer'
            })

    # 2. If fewer than 4 results, query OpenStreetMap Nominatim with safe rate-limiting and user-agent
    if len(results) < 4:
        try:
            query_param = q if ('gujarat' in q.lower() or 'india' in q.lower()) else f"{q}, Gujarat, India"
            url = f"https://nominatim.openstreetmap.org/search?format=json&q={urllib.parse.quote(query_param)}&countrycodes=in&viewbox=68.1,24.7,74.5,20.1&limit=6&addressdetails=1"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'NagarLoop-CircularRecovery/2.0 (contact: info@nagarloop.org)',
                'Accept-Language': 'en'
            })
            with urllib.request.urlopen(req, timeout=3.5) as response:
                osm_data = json.loads(response.read().decode('utf-8'))
                for item in osm_data:
                    display = item.get('display_name', '')
                    parts = display.split(',')
                    title = parts[0].strip()
                    subtitle = ", ".join([p.strip() for p in parts[1:4]])
                    lat = float(item['lat'])
                    lng = float(item['lon'])

                    # Avoid duplicates
                    if not any(abs(r['lat'] - lat) < 0.002 and abs(r['lng'] - lng) < 0.002 for r in results):
                        results.append({
                            'title': title,
                            'subtitle': subtitle or 'Gujarat, India',
                            'display_name': display,
                            'lat': lat,
                            'lng': lng,
                            'source': 'nominatim'
                        })
        except Exception:
            # Fallback smoothly to gazetteer without throwing error
            pass

    # Cache results (max 500 items in memory)
    if len(LOCATION_SEARCH_CACHE) > 500:
        LOCATION_SEARCH_CACHE.clear()
    LOCATION_SEARCH_CACHE[cache_key] = results[:6]

    return jsonify({'success': True, 'results': results[:6], 'request_id': request_id})

@app.route('/api/location/reverse')
def api_location_reverse():
    lat = request.args.get('lat', '')
    lng = request.args.get('lng', '')
    try:
        lat_f = round(float(lat), 5)
        lng_f = round(float(lng), 5)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid coordinates'}), 400

    cache_key = f"{lat_f},{lng_f}"
    if cache_key in LOCATION_REVERSE_CACHE:
        return jsonify({'success': True, 'address': LOCATION_REVERSE_CACHE[cache_key]})

    readable_address = None
    # 1. Match closest local gazetteer within 150m
    closest = None
    min_dist = float('inf')
    for item in GUJARAT_LOCAL_GAZETTEER:
        d = math.hypot(item['lat'] - lat_f, item['lng'] - lng_f)
        if d < min_dist:
            min_dist = d
            closest = item

    if min_dist < 0.002 and closest: # within ~200 meters
        readable_address = closest['display']

    # 2. If not in immediate vicinity, query Nominatim reverse
    if not readable_address:
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat_f}&lon={lng_f}&zoom=18&addressdetails=1"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'NagarLoop-CircularRecovery/2.0 (contact: info@nagarloop.org)',
                'Accept-Language': 'en'
            })
            with urllib.request.urlopen(req, timeout=3.5) as response:
                osm_data = json.loads(response.read().decode('utf-8'))
                if osm_data and 'display_name' in osm_data:
                    addr_dict = osm_data.get('address', {})
                    parts = [
                        addr_dict.get('building') or addr_dict.get('amenity') or addr_dict.get('house_number') or '',
                        addr_dict.get('road') or addr_dict.get('suburb') or addr_dict.get('neighbourhood') or '',
                        addr_dict.get('city') or addr_dict.get('town') or addr_dict.get('village') or addr_dict.get('county') or '',
                        addr_dict.get('state') or 'Gujarat',
                        addr_dict.get('postcode') or ''
                    ]
                    parts = [p.strip() for p in parts if p.strip()]
                    readable_address = ", ".join(parts) if len(parts) >= 2 else osm_data['display_name']
        except Exception:
            pass

    if not readable_address:
        if closest:
            readable_address = f"Near {closest['name']}, {closest['city']}, Gujarat"
        else:
            readable_address = f"Location at {lat_f:.4f}, {lng_f:.4f}, Gujarat"

    if len(LOCATION_REVERSE_CACHE) > 500:
        LOCATION_REVERSE_CACHE.clear()
    LOCATION_REVERSE_CACHE[cache_key] = readable_address

    return jsonify({'success': True, 'address': readable_address})

@app.route('/api/demo/reset', methods=['POST'])
def api_demo_reset():
    try:
        seed_database()
        return jsonify({'success': True, 'message': 'Database re-seeded successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ----------------------------------------------------
# LEGAL & STATIC INFO PAGES
# ----------------------------------------------------

@app.route('/privacy')
def privacy_page():
    return render_template('legal.html', page_type='privacy', page_title='Privacy Policy')

@app.route('/rewards')
def rewards_page():
    return render_template('legal.html', page_type='rewards', page_title='Green Rewards & Points')

@app.route('/help')
def help_page():
    return render_template('legal.html', page_type='help', page_title='Help & Support')

# ----------------------------------------------------
# MAIN ENTRY POINT
# ----------------------------------------------------

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
