import os
import math
import time
import io
import base64
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from database import get_db, init_db
from sklearn.cluster import KMeans
import numpy as np
import qrcode

app = Flask(__name__)
app.secret_key = 'swachhloop-4r-sih-2026-secret-key'

# Ensure uploads folder exists
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ----------------------------------------------------
# 4R FORMULAS & CALCULATION HELPERS
# ----------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    """Calculate great circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_green_points(bin_score):
    """
    SwachhLoop 4R Transparent Green Points Formula (SIH 2026 Rule):
    Base Points = 20
    Score Bonus = floor(bin_score / 10)
    Green Points = 20 + floor(bin_score / 10)
    """
    score = max(0, min(100, int(bin_score)))
    return 20 + math.floor(score / 10)

def calculate_co2_impact(wet_kg, dry_kg, ewaste_kg, residual_kg):
    """
    Simplified SIH MVP CO2 Reduction Estimates (kg CO2e):
    - Wet (Landfill diversion -> Bio-CNG / Compost): 0.85 kg CO2e / kg
    - Dry (Mechanical recycling vs virgin production): 1.95 kg CO2e / kg
    - E-Waste (Circular metals & plastics recovery): 3.20 kg CO2e / kg
    - Residual (RDF replacing fossil coal in cement kiln): 0.60 kg CO2e / kg
    NOTE: Explicitly labelled as ESTIMATES for demo/hackathon transparency.
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
# CITIZEN ROUTES
# ----------------------------------------------------

@app.route('/')
def citizen_home():
    conn = get_db()
    
    # Primary demo citizen household: H001 (Jenish Patel)
    household = conn.execute("SELECT * FROM households WHERE id = 1").fetchone()
    if not household:
        conn.close()
        return "Database not initialized. Please run seed_data.py first.", 500

    # Citizen points ledger
    total_points = conn.execute("""
        SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE household_id = 1
    """).fetchone()[0]

    # Citizen pickups
    pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        WHERE p.household_id = 1
        ORDER BY p.id DESC
    """).fetchall()

    # Aggregate citizen streams & impact
    citizen_streams = conn.execute("""
        SELECT ps.stream_type, COALESCE(SUM(ps.estimated_kg), 0) as total_kg
        FROM pickup_streams ps
        JOIN pickups p ON ps.pickup_id = p.id
        WHERE p.household_id = 1
        GROUP BY ps.stream_type
    """).fetchall()

    streams_dict = {row['stream_type']: round(row['total_kg'], 1) for row in citizen_streams}
    wet_kg = streams_dict.get('wet', 0.0)
    dry_kg = streams_dict.get('dry', 0.0)
    ewaste_kg = streams_dict.get('e_waste', 0.0)
    residual_kg = streams_dict.get('residual', 0.0)
    total_diverted = round(wet_kg + dry_kg + ewaste_kg + residual_kg, 1)
    co2_saved = calculate_co2_impact(wet_kg, dry_kg, ewaste_kg, residual_kg)

    # Attach streams to pickups for UI display
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
                           pickups=pickup_list)

@app.route('/book-pickup', methods=['POST'])
@app.route('/report', methods=['POST'])
def book_pickup():
    household_id = int(request.form.get('household_id', 1))
    lat = float(request.form.get('lat', 23.0375))
    lng = float(request.form.get('lon', request.form.get('lng', 72.5520)))
    
    # Waste stream selections
    stream_wet = request.form.get('stream_wet') == 'on'
    stream_dry = request.form.get('stream_dry') == 'on'
    stream_ewaste = request.form.get('stream_ewaste') == 'on'
    stream_residual = request.form.get('stream_residual') == 'on'

    # If no checkbox checked, default to wet + dry
    if not (stream_wet or stream_dry or stream_ewaste or stream_residual):
        stream_wet = True
        stream_dry = True

    # Bin Check Photo Upload Stub
    photo_file = request.files.get('photo')
    photo_path = "https://images.unsplash.com/photo-1530587191325-3db32d826c18?auto=format&fit=crop&w=600&q=80"
    
    if photo_file and photo_file.filename != '':
        filename = f"bin_{int(time.time())}_{os.urandom(4).hex()}_{photo_file.filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        photo_file.save(filepath)
        photo_path = url_for('static', filename=f"uploads/{filename}")

    # Simulated AI Bin Quality Score (stub: 75-95 based on segregation completeness)
    selected_count = sum([stream_wet, stream_dry, stream_ewaste, stream_residual])
    base_score = 70 + (selected_count * 6)
    bin_score = min(98, max(50, base_score + int(time.time() % 7)))

    green_points = calculate_green_points(bin_score)

    conn = get_db()
    cursor = conn.cursor()

    # Assign KMeans Pickup Zone based on nearest active cluster
    existing_coords = conn.execute("SELECT lat, lng, pickup_zone FROM pickups LIMIT 40").fetchall()
    pickup_zone = 1
    if len(existing_coords) >= 5:
        coords_arr = np.array([[r['lat'], r['lng']] for r in existing_coords])
        kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
        kmeans.fit(coords_arr)
        pickup_zone = int(kmeans.predict(np.array([[lat, lng]]))[0]) + 1

    # Insert pickup
    cursor.execute("""
        INSERT INTO pickups (household_id, lat, lng, bin_score, photo_path, status, pickup_zone)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """, (household_id, lat, lng, bin_score, photo_path, pickup_zone))
    pickup_id = cursor.lastrowid

    # Facility mappings:
    # 1: wet -> Bio-CNG / Compost
    # 2: dry -> MRF
    # 3: e_waste -> Recycler
    # 4: residual -> RDF Kiln
    streams_to_insert = []
    if stream_wet:
        streams_to_insert.append((pickup_id, 'wet', float(request.form.get('kg_wet', 3.5)), 1, 'pending'))
    if stream_dry:
        streams_to_insert.append((pickup_id, 'dry', float(request.form.get('kg_dry', 2.8)), 2, 'pending'))
    if stream_ewaste:
        streams_to_insert.append((pickup_id, 'e_waste', float(request.form.get('kg_ewaste', 1.2)), 3, 'pending'))
    if stream_residual:
        streams_to_insert.append((pickup_id, 'residual', float(request.form.get('kg_residual', 1.8)), 4, 'pending'))

    cursor.executemany("""
        INSERT INTO pickup_streams (pickup_id, stream_type, estimated_kg, facility_id, status)
        VALUES (?, ?, ?, ?, ?)
    """, streams_to_insert)

    # Insert Points Ledger entry
    reason = f"4R Segregated Pickup #{pickup_id} (Bin Score: {bin_score}/100)"
    cursor.execute("""
        INSERT INTO points_ledger (household_id, pickup_id, points, reason)
        VALUES (?, ?, ?, ?)
    """, (household_id, pickup_id, green_points, reason))

    conn.commit()
    conn.close()

    flash(f"🎉 4R Pickup #{pickup_id} booked! Bin Score: {bin_score}/100 | +{green_points} Green Points earned! 🌿", "success")
    return redirect(url_for('citizen_home'))

@app.route('/my-reports')
@app.route('/my-pickups')
def my_reports():
    conn = get_db()
    household = conn.execute("SELECT * FROM households WHERE id = 1").fetchone()
    
    total_points = conn.execute("""
        SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE household_id = 1
    """).fetchone()[0]

    pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment, v.van_code, v.driver_name
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.household_id = 1
        ORDER BY p.id DESC
    """).fetchall()

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

# ----------------------------------------------------
# QR MANIFEST & STATUS PAGE
# ----------------------------------------------------

@app.route('/manifest/<int:pickup_id>')
def manifest_page(pickup_id):
    """Public / Judge-verifiable digital QR manifest of a 4R pickup."""
    conn = get_db()
    pickup = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.phone, h.street_segment,
               v.van_code, v.driver_name
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.id = ?
    """, (pickup_id,)).fetchone()

    if not pickup:
        conn.close()
        return render_template('manifest_error.html', pickup_id=pickup_id), 404

    streams = conn.execute("""
        SELECT ps.*, f.name as facility_name, f.facility_type, f.registration_note
        FROM pickup_streams ps
        LEFT JOIN facilities f ON ps.facility_id = f.id
        WHERE ps.pickup_id = ?
    """, (pickup_id,)).fetchall()

    ledger = conn.execute("""
        SELECT * FROM points_ledger WHERE pickup_id = ?
    """, (pickup_id,)).fetchone()

    conn.close()

    # Generate live QR data URI
    qr_data_uri = generate_qr_base64(pickup_id, request.host_url)

    total_kg = sum([s['estimated_kg'] for s in streams])
    points_earned = ledger['points'] if ledger else calculate_green_points(pickup['bin_score'])

    return render_template('manifest_view.html',
                           pickup=pickup,
                           streams=streams,
                           total_kg=round(total_kg, 1),
                           points_earned=points_earned,
                           qr_data_uri=qr_data_uri)

@app.route('/qr/<int:pickup_id>')
def qr_image(pickup_id):
    """Direct PNG output of QR code."""
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
# ADMIN COMMAND CENTER
# ----------------------------------------------------

@app.route('/admin')
def admin_dashboard():
    conn = get_db()

    # KPI stats
    total_pickups = conn.execute("SELECT COUNT(*) FROM pickups").fetchone()[0]
    pending_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'pending'").fetchone()[0]
    collected_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'collected'").fetchone()[0]
    delivered_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'delivered'").fetchone()[0]
    active_vans = conn.execute("SELECT COUNT(*) FROM vans").fetchone()[0]
    
    total_kg_diverted = conn.execute("SELECT COALESCE(SUM(estimated_kg), 0) FROM pickup_streams").fetchone()[0]
    total_green_points = conn.execute("SELECT COALESCE(SUM(points), 0) FROM points_ledger").fetchone()[0]

    # Facility Demand Board
    demand_rows = conn.execute("""
        SELECT f.id, f.name, f.facility_type, f.stream_type, f.registration_note,
               COALESCE(SUM(ps.estimated_kg), 0) as total_demand_kg,
               COUNT(ps.id) as stream_count
        FROM facilities f
        LEFT JOIN pickup_streams ps ON f.id = ps.facility_id
        GROUP BY f.id
        ORDER BY f.id ASC
    """).fetchall()

    # Vans
    vans = conn.execute("SELECT * FROM vans ORDER BY id ASC").fetchall()

    # Pickups list with household and streams
    raw_pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment, v.van_code
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        ORDER BY p.id DESC
    """).fetchall()

    pickups_list = []
    for p in raw_pickups:
        p_dict = dict(p)
        st_rows = conn.execute("""
            SELECT ps.stream_type, ps.estimated_kg, ps.status, f.name as facility_name
            FROM pickup_streams ps
            LEFT JOIN facilities f ON ps.facility_id = f.id
            WHERE ps.pickup_id = ?
        """, (p['id'],)).fetchall()
        p_dict['streams'] = [dict(s) for s in st_rows]
        pickups_list.append(p_dict)

    # Ward Leaderboard Top Households
    leaderboard = conn.execute("""
        SELECT h.household_code, h.name, h.street_segment, SUM(pl.points) as total_points,
               COUNT(DISTINCT pl.pickup_id) as total_pickups
        FROM households h
        JOIN points_ledger pl ON h.id = pl.household_id
        GROUP BY h.id
        ORDER BY total_points DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return render_template('admin_dashboard.html',
                           total=total_pickups,
                           pending=pending_pickups,
                           collected=collected_pickups,
                           delivered=delivered_pickups,
                           active_vans=active_vans,
                           total_kg_diverted=round(total_kg_diverted, 1),
                           total_green_points=total_green_points,
                           demand=demand_rows,
                           vans=vans,
                           pickups=pickups_list,
                           leaderboard=leaderboard)

# ----------------------------------------------------
# ROUTE OPTIMIZATION (Nearest-Neighbor & Distance Saved %)
# ----------------------------------------------------

@app.route('/admin/route/<int:van_id>')
def admin_route_optimization(van_id):
    stream_filter = request.args.get('stream', 'all')
    
    conn = get_db()
    van = conn.execute("SELECT * FROM vans WHERE id = ?", (van_id,)).fetchone()
    
    if not van:
        conn.close()
        return "Van not found", 404

    # Fetch pickups assigned to or available for this van
    if stream_filter != 'all':
        query = """
            SELECT DISTINCT p.id, p.lat, p.lng, p.bin_score, p.status, p.pickup_zone,
                            h.household_code, h.name as citizen_name, h.street_segment
            FROM pickups p
            JOIN households h ON p.household_id = h.id
            JOIN pickup_streams ps ON p.id = ps.pickup_id
            WHERE (p.assigned_van_id = ? OR (p.assigned_van_id IS NULL AND p.status = 'pending'))
              AND ps.stream_type = ?
            ORDER BY p.id ASC
            LIMIT 12
        """
        raw_stops = conn.execute(query, (van_id, stream_filter)).fetchall()
    else:
        query = """
            SELECT p.id, p.lat, p.lng, p.bin_score, p.status, p.pickup_zone,
                   h.household_code, h.name as citizen_name, h.street_segment
            FROM pickups p
            JOIN households h ON p.household_id = h.id
            WHERE p.assigned_van_id = ? OR (p.assigned_van_id IS NULL AND p.status = 'pending')
            ORDER BY p.id ASC
            LIMIT 12
        """
        raw_stops = conn.execute(query, (van_id,)).fetchall()

    if not raw_stops:
        # Fallback to any pending pickups
        raw_stops = conn.execute("""
            SELECT p.id, p.lat, p.lng, p.bin_score, p.status, p.pickup_zone,
                   h.household_code, h.name as citizen_name, h.street_segment
            FROM pickups p
            JOIN households h ON p.household_id = h.id
            WHERE p.status = 'pending'
            ORDER BY p.id ASC
            LIMIT 8
        """).fetchall()

    stops_data = []
    for s in raw_stops:
        st_rows = conn.execute("""
            SELECT stream_type, estimated_kg, status FROM pickup_streams WHERE pickup_id = ?
        """, (s['id'],)).fetchall()
        streams_str = ", ".join([f"{r['stream_type'].upper()} ({r['estimated_kg']}kg)" for r in st_rows])
        stops_data.append({
            'id': s['id'],
            'lat': s['lat'],
            'lng': s['lng'],
            'household_code': s['household_code'],
            'name': s['citizen_name'],
            'street': s['street_segment'],
            'bin_score': s['bin_score'],
            'zone': s['pickup_zone'],
            'streams': streams_str
        })

    # Facilities for reference destination
    facilities = conn.execute("SELECT * FROM facilities").fetchall()
    conn.close()

    if not stops_data:
        return render_template('admin_route.html',
                               van=van,
                               stops=[],
                               naive_dist=0,
                               opt_dist=0,
                               saved_pct=0,
                               stream_filter=stream_filter,
                               facilities=facilities)

    # Depot / Van starting position
    start_pos = (van['lat'], van['lng'])
    all_points = [start_pos] + [(s['lat'], s['lng']) for s in stops_data]

    # 1. Naive distance (in sequential database order)
    naive_dist = 0.0
    for i in range(len(all_points) - 1):
        naive_dist += haversine(all_points[i][0], all_points[i][1], all_points[i+1][0], all_points[i+1][1])

    # 2. Nearest-Neighbor Heuristic (Greedy optimization)
    unvisited = list(range(1, len(all_points)))
    current = 0
    optimized_order = [0]

    while unvisited:
        nearest = min(
            unvisited,
            key=lambda idx: haversine(all_points[current][0], all_points[current][1], all_points[idx][0], all_points[idx][1])
        )
        optimized_order.append(nearest)
        unvisited.remove(nearest)
        current = nearest

    # 3. Optimized distance calculation
    opt_dist = 0.0
    for i in range(len(optimized_order) - 1):
        p1 = all_points[optimized_order[i]]
        p2 = all_points[optimized_order[i+1]]
        opt_dist += haversine(p1[0], p1[1], p2[0], p2[1])

    saved_pct = round(((naive_dist - opt_dist) / naive_dist * 100), 1) if naive_dist > 0 else 0.0

    # Ordered stops
    ordered_stops = []
    for order_num, idx in enumerate(optimized_order[1:], 1):
        stop_info = dict(stops_data[idx - 1])
        stop_info['sequence'] = order_num
        ordered_stops.append(stop_info)

    return render_template('admin_route.html',
                           van=van,
                           stops=ordered_stops,
                           naive_dist=round(naive_dist, 2),
                           opt_dist=round(opt_dist, 2),
                           saved_pct=saved_pct,
                           stream_filter=stream_filter,
                           facilities=facilities)

# ----------------------------------------------------
# REST API ENDPOINTS
# ----------------------------------------------------

@app.route('/api/pickups')
def api_pickups():
    conn = get_db()
    pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment, v.van_code
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        ORDER BY p.id ASC
    """).fetchall()

    result = []
    for p in pickups:
        p_dict = dict(p)
        streams = conn.execute("""
            SELECT ps.stream_type, ps.estimated_kg, ps.status, f.name as facility_name, f.facility_type
            FROM pickup_streams ps
            LEFT JOIN facilities f ON ps.facility_id = f.id
            WHERE ps.pickup_id = ?
        """, (p['id'],)).fetchall()
        p_dict['streams'] = [dict(s) for s in streams]
        result.append(p_dict)

    conn.close()
    return jsonify(result)

@app.route('/api/vans')
def api_vans():
    conn = get_db()
    vans = conn.execute("SELECT * FROM vans").fetchall()
    conn.close()
    return jsonify([dict(v) for v in vans])

@app.route('/api/facilities')
def api_facilities():
    conn = get_db()
    facilities = conn.execute("SELECT * FROM facilities").fetchall()
    conn.close()
    return jsonify([dict(f) for f in facilities])

@app.route('/api/zones')
@app.route('/api/hotspots')
def api_zones():
    """Returns KMeans pickup zones (K=5) computed from actual pickup coordinates."""
    conn = get_db()
    pickups = conn.execute("SELECT lat, lng, pickup_zone, status FROM pickups").fetchall()
    conn.close()

    if len(pickups) < 5:
        return jsonify({'zones': []})

    coords = np.array([[p['lat'], p['lng']] for p in pickups])
    kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
    kmeans.fit(coords)

    centers = kmeans.cluster_centers_
    labels = kmeans.labels_

    zones = []
    for i, center in enumerate(centers):
        count = int(np.sum(labels == i))
        zones.append({
            'zone_id': i + 1,
            'lat': float(center[0]),
            'lng': float(center[1]),
            'pickup_count': count,
            'color': ['#198754', '#0dcaf0', '#ffc107', '#fd7e14', '#d63384'][i % 5]
        })

    return jsonify({'zones': zones})

@app.route('/api/demand')
def api_demand():
    conn = get_db()
    demand = conn.execute("""
        SELECT f.stream_type, f.name as facility_name, f.facility_type,
               COALESCE(SUM(ps.estimated_kg), 0) as total_kg
        FROM facilities f
        LEFT JOIN pickup_streams ps ON f.id = ps.facility_id
        GROUP BY f.id
    """).fetchall()
    conn.close()
    return jsonify({r['stream_type']: {'facility': r['facility_name'], 'kg': round(r['total_kg'], 1)} for r in demand})

@app.route('/api/leaderboard')
def api_leaderboard():
    conn = get_db()
    rows = conn.execute("""
        SELECT h.household_code, h.name, SUM(pl.points) as points
        FROM households h
        JOIN points_ledger pl ON h.id = pl.household_id
        GROUP BY h.id
        ORDER BY points DESC
        LIMIT 10
    """).fetchall()
    conn.close()
    return jsonify({
        'labels': [f"{r['household_code']} ({r['name'].split()[0]})" for r in rows],
        'points': [r['points'] for r in rows]
    })

@app.route('/api/charts')
def api_charts():
    conn = get_db()
    
    # Stream-wise total kg
    streams = conn.execute("""
        SELECT stream_type, COALESCE(SUM(estimated_kg), 0) as total_kg
        FROM pickup_streams
        GROUP BY stream_type
    """).fetchall()

    # Status breakdown
    statuses = conn.execute("""
        SELECT status, COUNT(*) as count FROM pickups GROUP BY status
    """).fetchall()

    # Zone breakdown
    zones = conn.execute("""
        SELECT pickup_zone, COUNT(*) as count FROM pickups GROUP BY pickup_zone ORDER BY pickup_zone ASC
    """).fetchall()

    conn.close()

    return jsonify({
        'streams': {r['stream_type']: round(r['total_kg'], 1) for r in streams},
        'statuses': {r['status']: r['count'] for r in statuses},
        'zones': {f"Zone {r['pickup_zone']}": r['count'] for r in zones}
    })

@app.route('/api/impact')
def api_impact():
    conn = get_db()
    streams = conn.execute("""
        SELECT stream_type, COALESCE(SUM(estimated_kg), 0) as total_kg
        FROM pickup_streams
        GROUP BY stream_type
    """).fetchall()
    conn.close()

    s_dict = {r['stream_type']: r['total_kg'] for r in streams}
    wet = s_dict.get('wet', 0.0)
    dry = s_dict.get('dry', 0.0)
    ewaste = s_dict.get('e_waste', 0.0)
    residual = s_dict.get('residual', 0.0)

    total_diverted = round(wet + dry + ewaste + residual, 1)
    co2 = calculate_co2_impact(wet, dry, ewaste, residual)

    return jsonify({
        'total_kg_diverted': total_diverted,
        'estimated_co2_kg': co2,
        'breakdown': {
            'wet_kg': round(wet, 1),
            'dry_kg': round(dry, 1),
            'ewaste_kg': round(ewaste, 1),
            'residual_kg': round(residual, 1)
        }
    })

@app.route('/api/assign', methods=['POST'])
def api_assign():
    data = request.json or request.form
    pickup_id = data.get('pickup_id') or data.get('report_id')
    van_id = data.get('van_id') or data.get('vehicle_id')

    if not pickup_id or not van_id:
        return jsonify({'success': False, 'message': 'Missing pickup_id or van_id'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE pickups SET assigned_van_id = ?, status = 'pending' WHERE id = ?", (van_id, pickup_id))
    cursor.execute("UPDATE vans SET status = 'en_route' WHERE id = ?", (van_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Van #{van_id} assigned to Pickup #{pickup_id}'})

@app.route('/api/status/<int:pickup_id>', methods=['POST'])
def api_update_status(pickup_id):
    data = request.json or request.form
    new_status = data.get('status', 'collected')
    
    if new_status not in ['pending', 'collected', 'delivered']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    delivered_timestamp = '2026-08-14 14:00:00' if new_status == 'delivered' else None

    cursor.execute("UPDATE pickups SET status = ? WHERE id = ?", (new_status, pickup_id))
    cursor.execute("""
        UPDATE pickup_streams SET status = ?, delivered_at = ? WHERE pickup_id = ?
    """, (new_status, delivered_timestamp, pickup_id))
    
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Pickup #{pickup_id} status updated to {new_status}'})

# ----------------------------------------------------
# BACKGROUND VAN SIMULATION
# ----------------------------------------------------
from simulate_trucks import move_trucks

def start_simulation():
    """Run van simulation in background thread."""
    while True:
        try:
            time.sleep(6)
            move_trucks()
        except Exception as e:
            print(f"Simulation tick error: {e}")

if __name__ == '__main__':
    init_db()
    sim_thread = threading.Thread(target=start_simulation, daemon=True)
    sim_thread.start()
    print("SwachhLoop 4R Van simulation started in background...")
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
