import os
import math
import time
import io
import json
import base64
import threading
import random
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from database import get_db, init_db
from seed_data import seed as seed_database
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
# ROUTE CALCULATION & RECOMMENDATION ENGINE
# ----------------------------------------------------

def calculate_route_metrics(van_pos, stops, facility_pos=None):
    """
    Computes Naive Route, Nearest-Neighbor Optimized Route, and Distance Saved %
    Optionally includes terminating destination facility for zero-mixing completion.
    """
    if not stops:
        return 0.0, 0.0, 0.0, []

    if len(stops) == 1:
        s = dict(stops[0])
        s['sequence'] = 1
        dist = haversine(van_pos[0], van_pos[1], s['lat'], s['lng'])
        if facility_pos:
            dist += haversine(s['lat'], s['lng'], facility_pos[0], facility_pos[1])
        return round(dist, 2), round(dist, 2), 0.0, [s]

    all_points = [van_pos] + [(s['lat'], s['lng']) for s in stops]
    if facility_pos:
        all_points.append(facility_pos)

    # 1. Naive distance (original sequential order)
    naive_dist = 0.0
    for i in range(len(all_points) - 1):
        naive_dist += haversine(all_points[i][0], all_points[i][1], all_points[i+1][0], all_points[i+1][1])

    # 2. Nearest-Neighbor Heuristic (Greedy optimization starting at van)
    num_stops = len(stops)
    unvisited = list(range(1, num_stops + 1))
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

    if facility_pos:
        optimized_order.append(len(all_points) - 1)

    # 3. Optimized distance calculation
    opt_dist = 0.0
    for i in range(len(optimized_order) - 1):
        p1 = all_points[optimized_order[i]]
        p2 = all_points[optimized_order[i+1]]
        opt_dist += haversine(p1[0], p1[1], p2[0], p2[1])

    saved_pct = round(((naive_dist - opt_dist) / naive_dist * 100), 1) if naive_dist > 0 else 0.0

    ordered_stops = []
    for seq_num, idx in enumerate(optimized_order[1:num_stops + 1], 1):
        s_info = dict(stops[idx - 1])
        s_info['sequence'] = seq_num
        ordered_stops.append(s_info)

    return round(naive_dist, 2), round(opt_dist, 2), saved_pct, ordered_stops

def generate_route_recommendations(conn):
    """
    Automatically groups uncollected pickups by stream and zone, selects nearest available van,
    and returns rich recommendation objects.
    """
    vans = conn.execute("SELECT * FROM vans ORDER BY id ASC").fetchall()
    facilities = {f['stream_type']: f for f in conn.execute("SELECT * FROM facilities").fetchall()}
    
    recommendations = []
    stream_types = ['wet', 'dry', 'e_waste', 'residual']
    
    for stream in stream_types:
        for zone in range(1, 6):
            stops = conn.execute("""
                SELECT DISTINCT p.id, p.lat, p.lng, p.bin_score, p.status, p.pickup_zone,
                                h.household_code, h.name as citizen_name, h.street_segment,
                                ps.estimated_kg, ps.stream_type
                FROM pickups p
                JOIN households h ON p.household_id = h.id
                JOIN pickup_streams ps ON p.id = ps.pickup_id
                WHERE ps.stream_type = ? AND p.pickup_zone = ? AND (p.status = 'pending' OR p.status = 'collection_reported' OR p.status = 'collected')
                ORDER BY p.id ASC LIMIT 10
            """, (stream, zone)).fetchall()
            
            if not stops:
                continue

            avg_lat = sum(s['lat'] for s in stops) / len(stops)
            avg_lng = sum(s['lng'] for s in stops) / len(stops)

            best_van = min(
                vans,
                key=lambda v: haversine(v['lat'], v['lng'], avg_lat, avg_lng)
            )

            fac = facilities.get(stream)
            fac_pos = (fac['lat'], fac['lng']) if fac else None
            van_pos = (best_van['lat'], best_van['lng'])

            stops_list = [dict(s) for s in stops]
            naive_dist, opt_dist, saved_pct, ordered_stops = calculate_route_metrics(van_pos, stops_list, fac_pos)

            stream_display_names = {
                'wet': 'Wet / Organic',
                'dry': 'Dry Recyclables',
                'e_waste': 'E-Waste',
                'residual': 'Residual Combustibles'
            }
            s_name = stream_display_names.get(stream, stream.upper())
            explanation = f"Recommended because {len(stops)} {s_name} pickups are concentrated in Zone {zone} and {best_van['van_code']} is the nearest available van."

            recommendations.append({
                'van_id': best_van['id'],
                'van_code': best_van['van_code'],
                'driver_name': best_van['driver_name'],
                'stream_type': stream,
                'stream_name': s_name,
                'pickup_zone': zone,
                'stop_count': len(stops),
                'stops': ordered_stops,
                'naive_dist_km': naive_dist,
                'opt_dist_km': opt_dist,
                'saved_pct': saved_pct,
                'facility_name': fac['name'] if fac else 'Designated Facility',
                'explanation': explanation
            })

    return recommendations

# ----------------------------------------------------
# CITIZEN ROUTES
# ----------------------------------------------------

@app.route('/')
def citizen_home():
    conn = get_db()
    
    household = conn.execute("SELECT * FROM households WHERE id = 1").fetchone()
    if not household:
        conn.close()
        return "Database not initialized. Please run seed_data.py first.", 500

    total_points = conn.execute("""
        SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE household_id = 1
    """).fetchone()[0]

    pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        WHERE p.household_id = 1
        ORDER BY p.id DESC
    """).fetchall()

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

@app.route('/impact')
def citizen_impact():
    conn = get_db()
    household = conn.execute("SELECT * FROM households WHERE id = 1").fetchone()
    total_points = conn.execute("SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE household_id = 1").fetchone()[0]

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

    recent_pickups = conn.execute("""
        SELECT p.*, h.household_code, h.name as citizen_name, h.street_segment
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        WHERE p.household_id = 1
        ORDER BY p.id DESC LIMIT 5
    """).fetchall()

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

@app.route('/book-pickup', methods=['POST'])
@app.route('/report', methods=['POST'])
def book_pickup():
    household_id = int(request.form.get('household_id', 1))
    
    try:
        lat = float(request.form.get('lat', 23.0375))
        lng = float(request.form.get('lon', request.form.get('lng', 72.5520)))
    except (ValueError, TypeError):
        lat = 23.0375
        lng = 72.5520

    stream_wet = request.form.get('stream_wet') in ['on', 'true', '1']
    stream_dry = request.form.get('stream_dry') in ['on', 'true', '1']
    stream_ewaste = request.form.get('stream_ewaste') in ['on', 'true', '1']
    stream_residual = request.form.get('stream_residual') in ['on', 'true', '1']

    if not (stream_wet or stream_dry or stream_ewaste or stream_residual):
        stream_wet = True
        stream_dry = True

    photo_file = request.files.get('photo')
    photo_path = "https://images.unsplash.com/photo-1530587191325-3db32d826c18?auto=format&fit=crop&w=600&q=80"
    
    if photo_file and photo_file.filename != '':
        filename = f"bin_{int(time.time())}_{os.urandom(4).hex()}_{photo_file.filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        photo_file.save(filepath)
        photo_path = url_for('static', filename=f"uploads/{filename}")

    selected_count = sum([stream_wet, stream_dry, stream_ewaste, stream_residual])
    base_score = 72 + (selected_count * 5)
    bin_score = min(98, max(55, base_score + random.randint(1, 8)))

    green_points = calculate_green_points(bin_score)

    conn = get_db()
    cursor = conn.cursor()

    existing_coords = conn.execute("SELECT lat, lng FROM pickups LIMIT 40").fetchall()
    pickup_zone = 1
    if len(existing_coords) >= 5:
        coords_arr = np.array([[r['lat'], r['lng']] for r in existing_coords])
        kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
        kmeans.fit(coords_arr)
        pickup_zone = int(kmeans.predict(np.array([[lat, lng]]))[0]) + 1

    cursor.execute("""
        INSERT INTO pickups (household_id, lat, lng, bin_score, photo_path, status, pickup_zone)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """, (household_id, lat, lng, bin_score, photo_path, pickup_zone))
    pickup_id = cursor.lastrowid

    streams_to_insert = []
    if stream_wet:
        est_wet = round(random.uniform(3.0, 5.0), 1)
        streams_to_insert.append((pickup_id, 'wet', est_wet, 1, 'pending'))
    if stream_dry:
        est_dry = round(random.uniform(2.0, 4.0), 1)
        streams_to_insert.append((pickup_id, 'dry', est_dry, 2, 'pending'))
    if stream_ewaste:
        est_ewaste = round(random.uniform(0.8, 2.5), 1)
        streams_to_insert.append((pickup_id, 'e_waste', est_ewaste, 3, 'pending'))
    if stream_residual:
        est_residual = round(random.uniform(1.2, 3.0), 1)
        streams_to_insert.append((pickup_id, 'residual', est_residual, 4, 'pending'))

    cursor.executemany("""
        INSERT INTO pickup_streams (pickup_id, stream_type, estimated_kg, facility_id, status)
        VALUES (?, ?, ?, ?, ?)
    """, streams_to_insert)

    reason = f"4R Segregated Pickup #{pickup_id} (Bin Score: {bin_score}/100)"
    cursor.execute("""
        INSERT INTO points_ledger (household_id, pickup_id, points, reason)
        VALUES (?, ?, ?, ?)
    """, (household_id, pickup_id, green_points, reason))

    conn.commit()
    conn.close()

    flash(f"🎉 4R Pickup #{pickup_id} booked successfully! Bin Score: {bin_score}/100 | +{green_points} Green Points earned! 🌿", "success")
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

    audit_trail = conn.execute("""
        SELECT * FROM audit_logs WHERE pickup_id = ? ORDER BY id DESC
    """, (pickup_id,)).fetchall()

    conn.close()

    qr_data_uri = generate_qr_base64(pickup_id, request.host_url)
    total_kg = sum([s['estimated_kg'] for s in streams])
    points_earned = ledger['points'] if ledger else calculate_green_points(pickup['bin_score'])

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
# ADMIN COMMAND CENTER (EXECUTIVE OVERVIEW)
# ----------------------------------------------------

@app.route('/admin')
def admin_dashboard():
    conn = get_db()

    total_pickups = conn.execute("SELECT COUNT(*) FROM pickups").fetchone()[0]
    pending_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status IN ('pending', 'collection_reported', 'disputed')").fetchone()[0]
    collected_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'collected'").fetchone()[0]
    delivered_pickups = conn.execute("SELECT COUNT(*) FROM pickups WHERE status = 'delivered'").fetchone()[0]
    active_vans = conn.execute("SELECT COUNT(*) FROM vans").fetchone()[0]
    
    total_kg_diverted = conn.execute("SELECT COALESCE(SUM(estimated_kg), 0) FROM pickup_streams").fetchone()[0]
    total_green_points = conn.execute("SELECT COALESCE(SUM(points), 0) FROM points_ledger").fetchone()[0]

    demand_rows = conn.execute("""
        SELECT f.id, f.name, f.facility_type, f.stream_type, f.registration_note, f.capacity_kg,
               COALESCE(SUM(ps.estimated_kg), 0) as total_demand_kg,
               COUNT(ps.id) as stream_count
        FROM facilities f
        LEFT JOIN pickup_streams ps ON f.id = ps.facility_id
        GROUP BY f.id
        ORDER BY f.id ASC
    """).fetchall()

    demand_list = []
    for d in demand_rows:
        d_dict = dict(d)
        cap = d['capacity_kg'] if d['capacity_kg'] else 10000.0
        d_dict['usage_pct'] = round((d['total_demand_kg'] / cap) * 100, 1)
        demand_list.append(d_dict)

    vans = conn.execute("SELECT * FROM vans ORDER BY id ASC").fetchall()

    leaderboard = conn.execute("""
        SELECT h.household_code, h.name, h.street_segment, SUM(pl.points) as total_points,
               COUNT(DISTINCT pl.pickup_id) as total_pickups
        FROM households h
        JOIN points_ledger pl ON h.id = pl.household_id
        GROUP BY h.id
        ORDER BY total_points DESC
        LIMIT 10
    """).fetchall()

    active_households_count = conn.execute("""
        SELECT COUNT(DISTINCT household_id) FROM points_ledger
    """).fetchone()[0]

    top_household = leaderboard[0] if leaderboard else None

    # Van Batches Summary
    van_ops_summary = []
    for v in vans:
        assigned_count = conn.execute("SELECT COUNT(*) FROM pickups WHERE assigned_van_id = ?", (v['id'],)).fetchone()[0]
        collected_cnt = conn.execute("SELECT COUNT(*) FROM pickups WHERE assigned_van_id = ? AND status IN ('collected', 'delivered')", (v['id'],)).fetchone()[0]
        van_ops_summary.append({
            'van_id': v['id'],
            'van_code': v['van_code'],
            'driver_name': v['driver_name'],
            'status': v['status'],
            'assigned_count': assigned_count,
            'collected_count': collected_cnt,
            'progress_pct': round((collected_cnt / assigned_count * 100), 1) if assigned_count > 0 else 0.0
        })

    # Recent Activity Events
    recent_events = conn.execute("""
        SELECT al.id, al.pickup_id, al.action, al.previous_status, al.new_status, al.notes,
               al.actor_type, al.created_at, h.household_code, h.name as citizen_name,
               h.street_segment, v.van_code
        FROM audit_logs al
        JOIN pickups p ON al.pickup_id = p.id
        JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        ORDER BY al.id DESC LIMIT 8
    """).fetchall()

    stream_counts = conn.execute("""
        SELECT stream_type, COUNT(*) as count, SUM(estimated_kg) as total_kg
        FROM pickup_streams GROUP BY stream_type
    """).fetchall()
    stream_counts_dict = {r['stream_type']: {'count': r['count'], 'kg': round(r['total_kg'], 1)} for r in stream_counts}

    recommended_routes = generate_route_recommendations(conn)

    conn.close()

    return render_template('admin_dashboard.html',
                           total=total_pickups,
                           pending=pending_pickups,
                           collected=collected_pickups,
                           delivered=delivered_pickups,
                           active_vans=active_vans,
                           total_kg_diverted=round(total_kg_diverted, 1),
                           total_green_points=total_green_points,
                           demand=demand_list,
                           vans=vans,
                           leaderboard=leaderboard,
                           active_households_count=active_households_count,
                           top_household=top_household,
                           van_ops_summary=van_ops_summary,
                           recent_events=recent_events,
                           stream_counts=stream_counts_dict,
                           recommended_routes=recommended_routes[:4])

# ----------------------------------------------------
# DEDICATED DISPATCH CENTER (OPERATIONAL MANAGEMENT)
# ----------------------------------------------------

@app.route('/admin/dispatch')
def admin_dispatch():
    van_id = int(request.args.get('van_id', 1))
    stream_filter = request.args.get('stream', 'all')
    
    conn = get_db()
    vans = conn.execute("SELECT * FROM vans ORDER BY id ASC").fetchall()
    selected_van = conn.execute("SELECT * FROM vans WHERE id = ?", (van_id,)).fetchone() or vans[0]

    # Fetch stops assigned to this van or pending in this van's area
    query = """
        SELECT DISTINCT p.id, p.lat, p.lng, p.bin_score, p.status, p.pickup_zone,
                        h.household_code, h.name as citizen_name, h.phone, h.street_segment,
                        v.van_code, v.driver_name
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
        st_rows = conn.execute("""
            SELECT stream_type, estimated_kg, status FROM pickup_streams WHERE pickup_id = ?
        """, (s['id'],)).fetchall()
        streams_str = ", ".join([f"{r['stream_type'].upper()} ({r['estimated_kg']}kg)" for r in st_rows])
        streams_list = [dict(r) for r in st_rows]
        stops_data.append({
            'id': s['id'],
            'lat': s['lat'],
            'lng': s['lng'],
            'household_code': s['household_code'],
            'name': s['citizen_name'],
            'phone': s['phone'],
            'street': s['street_segment'],
            'bin_score': s['bin_score'],
            'zone': s['pickup_zone'],
            'status': s['status'],
            'streams': streams_str,
            'streams_list': streams_list
        })

    naive_dist, opt_dist, saved_pct, ordered_stops = calculate_route_metrics(van_pos, stops_data, fac_pos)

    # Route progress: ONLY 'collected' and 'delivered' count towards completion!
    total_stops = len(ordered_stops)
    collected_stops = sum(1 for s in ordered_stops if s['status'] in ['collected', 'delivered'])
    delivered_stops = sum(1 for s in ordered_stops if s['status'] == 'delivered')
    progress_pct = round((collected_stops / total_stops * 100), 1) if total_stops > 0 else 0.0

    # Next stop: first pending stop (or first collection_reported / disputed needing action)
    next_stop = next((s for s in ordered_stops if s['status'] == 'pending'), None)
    is_route_complete = (collected_stops == total_stops and total_stops > 0)

    # Collection Issues & Disputes Queue
    disputed_pickups = conn.execute("""
        SELECT p.id, p.household_id, p.status, p.bin_score, h.household_code, h.name as citizen_name,
               h.phone, h.street_segment, v.van_code, v.driver_name
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        LEFT JOIN vans v ON p.assigned_van_id = v.id
        WHERE p.status = 'disputed'
        ORDER BY p.id DESC
    """).fetchall()

    disputed_list = []
    for dp in disputed_pickups:
        dp_dict = dict(dp)
        dp_dict['name'] = dp['citizen_name']
        st_rows = conn.execute("SELECT stream_type, estimated_kg FROM pickup_streams WHERE pickup_id = ?", (dp['id'],)).fetchall()
        dp_dict['streams'] = ", ".join([f"{r['stream_type'].upper()}" for r in st_rows])
        disputed_list.append(dp_dict)

    # Active operational routes overview for the dispatch header
    all_routes_overview = []
    for v in vans:
        v_stops = conn.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status IN ('collected', 'delivered') THEN 1 ELSE 0 END) as collected FROM pickups WHERE assigned_van_id = ?", (v['id'],)).fetchone()
        t_cnt = v_stops['total'] or 0
        c_cnt = v_stops['collected'] or 0
        all_routes_overview.append({
            'van_id': v['id'],
            'van_code': v['van_code'],
            'driver_name': v['driver_name'],
            'status': v['status'],
            'total': t_cnt,
            'collected': c_cnt,
            'pct': round((c_cnt / t_cnt * 100), 1) if t_cnt > 0 else 0.0
        })

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
                           disputed_pickups=disputed_list,
                           naive_dist=naive_dist,
                           opt_dist=opt_dist,
                           saved_pct=saved_pct,
                           facility=facility,
                           stream_filter=stream_filter,
                           all_routes_overview=all_routes_overview)

# ----------------------------------------------------
# ROUTE OPTIMIZATION SCREEN
# ----------------------------------------------------

@app.route('/admin/route/<int:van_id>')
def admin_route_optimization(van_id):
    stream_filter = request.args.get('stream', 'wet')
    zone_filter = request.args.get('zone', 'all')
    
    conn = get_db()
    van = conn.execute("SELECT * FROM vans WHERE id = ?", (van_id,)).fetchone()
    
    if not van:
        conn.close()
        return "Van not found", 404

    saved_route = conn.execute("""
        SELECT * FROM routes WHERE van_id = ? AND stream_type = ? AND status = 'applied'
        ORDER BY id DESC LIMIT 1
    """, (van_id, stream_filter)).fetchone()

    query = """
        SELECT DISTINCT p.id, p.lat, p.lng, p.bin_score, p.status, p.pickup_zone,
                        h.household_code, h.name as citizen_name, h.street_segment
        FROM pickups p
        JOIN households h ON p.household_id = h.id
        JOIN pickup_streams ps ON p.id = ps.pickup_id
        WHERE ps.stream_type = ?
    """
    params = [stream_filter]

    if zone_filter != 'all':
        query += " AND p.pickup_zone = ?"
        params.append(int(zone_filter))

    query += " ORDER BY p.id ASC LIMIT 12"
    raw_stops = conn.execute(query, tuple(params)).fetchall()

    if not raw_stops:
        raw_stops = conn.execute("""
            SELECT p.id, p.lat, p.lng, p.bin_score, p.status, p.pickup_zone,
                   h.household_code, h.name as citizen_name, h.street_segment
            FROM pickups p
            JOIN households h ON p.household_id = h.id
            WHERE p.status IN ('pending', 'collection_reported', 'disputed')
            ORDER BY p.id ASC LIMIT 8
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

    all_vans = conn.execute("SELECT * FROM vans ORDER BY id ASC").fetchall()
    facility = conn.execute("SELECT * FROM facilities WHERE stream_type = ?", (stream_filter,)).fetchone()
    if not facility:
        facility = conn.execute("SELECT * FROM facilities LIMIT 1").fetchone()
    
    conn.close()

    fac_pos = (facility['lat'], facility['lng']) if facility else None
    van_pos = (van['lat'], van['lng'])

    if saved_route and saved_route['stop_order_json']:
        try:
            saved_ids = json.loads(saved_route['stop_order_json'])
            id_map = {s['id']: s for s in stops_data}
            ordered_stops = []
            for seq_num, pid in enumerate(saved_ids, 1):
                if pid in id_map:
                    s_info = dict(id_map[pid])
                    s_info['sequence'] = seq_num
                    ordered_stops.append(s_info)
            naive_dist = saved_route['naive_dist_km']
            opt_dist = saved_route['opt_dist_km']
            saved_pct = saved_route['saved_pct']
            route_status = 'applied'
        except Exception:
            naive_dist, opt_dist, saved_pct, ordered_stops = calculate_route_metrics(van_pos, stops_data, fac_pos)
            route_status = 'recommended'
    else:
        naive_dist, opt_dist, saved_pct, ordered_stops = calculate_route_metrics(van_pos, stops_data, fac_pos)
        route_status = 'recommended'

    stream_display_names = {
        'wet': 'Wet / Organic',
        'dry': 'Dry Recyclables',
        'e_waste': 'E-Waste',
        'residual': 'Residual Combustibles'
    }
    s_name = stream_display_names.get(stream_filter, stream_filter.upper())
    zone_label = f"Zone {zone_filter}" if zone_filter != 'all' else "Ahmedabad Ward"
    explanation = f"Recommended batch for {van['van_code']}: {len(ordered_stops)} {s_name} stops in {zone_label} optimized using Nearest-Neighbor heuristic, saving {saved_pct}% travel distance."

    return render_template('admin_route.html',
                           van=van,
                           all_vans=all_vans,
                           stops=ordered_stops,
                           naive_dist=naive_dist,
                           opt_dist=opt_dist,
                           saved_pct=saved_pct,
                           route_status=route_status,
                           stream_filter=stream_filter,
                           zone_filter=zone_filter,
                           explanation=explanation,
                           facility=facility)

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
    colors = ['#15803d', '#0284c7', '#d97706', '#ea580c', '#db2777']
    for i, center in enumerate(centers):
        count = int(np.sum(labels == i))
        zones.append({
            'zone_id': i + 1,
            'lat': float(center[0]),
            'lng': float(center[1]),
            'pickup_count': count,
            'color': colors[i % len(colors)]
        })

    return jsonify({'zones': zones})

@app.route('/api/demand')
def api_demand():
    conn = get_db()
    demand = conn.execute("""
        SELECT f.stream_type, f.name as facility_name, f.facility_type, f.capacity_kg,
               COALESCE(SUM(ps.estimated_kg), 0) as total_kg
        FROM facilities f
        LEFT JOIN pickup_streams ps ON f.id = ps.facility_id
        GROUP BY f.id
    """).fetchall()
    conn.close()
    return jsonify({
        r['stream_type']: {
            'facility': r['facility_name'],
            'kg': round(r['total_kg'], 1),
            'capacity_kg': r['capacity_kg']
        } for r in demand
    })

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

# ----------------------------------------------------
# CITIZEN COLLECTION VERIFICATION API
# ----------------------------------------------------

@app.route('/api/citizen/verify/<int:pickup_id>', methods=['POST'])
def api_citizen_verify(pickup_id):
    """
    Citizen responds to 'Was your waste collected?'
    Action 'confirm' -> status becomes 'collected'
    Action 'dispute' -> status becomes 'disputed'
    """
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
        return jsonify({'success': False, 'message': f'Pickup #{pickup_id} is in {curr_status} status. Only collection_reported pickups can be verified.'}), 400

    if action == 'confirm':
        new_status = 'collected'
        action_name = 'citizen_confirm'
        notes = 'Citizen confirmed waste was collected'
    elif action == 'dispute':
        new_status = 'disputed'
        action_name = 'citizen_dispute'
        notes = 'Citizen disputed: Waste was not collected'
    else:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid citizen verification action'}), 400

    cursor.execute("UPDATE pickups SET status = ? WHERE id = ?", (new_status, pickup_id))
    cursor.execute("UPDATE pickup_streams SET status = ? WHERE pickup_id = ?", (new_status, pickup_id))
    cursor.execute("""
        INSERT INTO audit_logs (pickup_id, previous_status, new_status, action, actor_type, notes)
        VALUES (?, 'collection_reported', ?, ?, 'citizen', ?)
    """, (pickup_id, new_status, action_name, notes))

    conn.commit()
    conn.close()

    msg = "🎉 Thank you! Your waste collection has been confirmed." if action == 'confirm' else "⚠ Dispute recorded. Municipal team has been notified for investigation."
    return jsonify({'success': True, 'message': msg, 'new_status': new_status})

# ----------------------------------------------------
# OPERATOR & ADMIN STATUS LIFECYCLE API
# ----------------------------------------------------

@app.route('/api/status/<int:pickup_id>', methods=['POST'])
def api_update_status(pickup_id):
    """
    Strict State Machine & Verification Enforcement:
    1. report_collection: PENDING -> COLLECTION_REPORTED (Operator)
    2. citizen_confirm: COLLECTION_REPORTED -> COLLECTED (Citizen)
    3. citizen_dispute: COLLECTION_REPORTED -> DISPUTED (Citizen)
    4. admin_confirm: DISPUTED -> COLLECTED (Admin Review)
    5. admin_reopen: DISPUTED -> PENDING (Admin Review)
    6. reopen_pickup: (COLLECTION_REPORTED | COLLECTED) -> PENDING (Accidental fix)
    7. mark_delivered: COLLECTED -> DELIVERED (Facility delivery)
    8. reopen_delivered: DELIVERED -> COLLECTED (Facility recovery)
    """
    data = request.json or request.form
    action = data.get('action')
    new_status = data.get('status')

    # Direct mapping
    if action == 'report_collection':
        new_status = 'collection_reported'
    elif action == 'citizen_confirm':
        new_status = 'collected'
    elif action == 'citizen_dispute':
        new_status = 'disputed'
    elif action == 'admin_confirm':
        new_status = 'collected'
    elif action == 'admin_reopen':
        new_status = 'pending'
    elif action == 'reopen_pickup':
        new_status = 'pending'
    elif action == 'mark_delivered':
        new_status = 'delivered'
    elif action == 'reopen_delivered':
        new_status = 'collected'

    if not new_status or new_status not in ['pending', 'collection_reported', 'disputed', 'collected', 'delivered']:
        return jsonify({'success': False, 'message': 'Invalid target status'}), 400

    conn = get_db()
    cursor = conn.cursor()

    current = cursor.execute("SELECT * FROM pickups WHERE id = ?", (pickup_id,)).fetchone()
    if not current:
        conn.close()
        return jsonify({'success': False, 'message': f'Pickup #{pickup_id} not found'}), 404

    curr_status = current['status']
    actor_type = 'operator'
    delivered_timestamp = None

    # Server-Side State Machine Transitions
    if new_status == 'collection_reported':
        if curr_status != 'pending':
            conn.close()
            return jsonify({'success': False, 'message': f'Pickup #{pickup_id} is already in {curr_status} status. Cannot report collection.'}), 400
        action_name = 'report_collection'
        actor_type = 'operator'
        notes = 'Operator reported waste collection (Awaiting Citizen Confirmation)'

    elif action == 'citizen_confirm':
        if curr_status != 'collection_reported':
            conn.close()
            return jsonify({'success': False, 'message': f'Pickup must be in collection_reported state. Current: {curr_status}'}), 400
        action_name = 'citizen_confirm'
        actor_type = 'citizen'
        notes = 'Citizen confirmed waste collection'

    elif action == 'citizen_dispute':
        if curr_status != 'collection_reported':
            conn.close()
            return jsonify({'success': False, 'message': f'Pickup must be in collection_reported state. Current: {curr_status}'}), 400
        action_name = 'citizen_dispute'
        actor_type = 'citizen'
        notes = 'Citizen reported waste was NOT collected'

    elif action == 'admin_confirm':
        if curr_status != 'disputed':
            conn.close()
            return jsonify({'success': False, 'message': f'Pickup must be in disputed state for admin resolution. Current: {curr_status}'}), 400
        action_name = 'admin_confirm'
        actor_type = 'admin'
        notes = 'Admin verified collection after dispute investigation'

    elif action == 'admin_reopen':
        if curr_status != 'disputed':
            conn.close()
            return jsonify({'success': False, 'message': f'Pickup must be in disputed state for admin resolution. Current: {curr_status}'}), 400
        action_name = 'admin_reopen'
        actor_type = 'admin'
        notes = 'Admin returned pickup to pending for recollection'

    elif action == 'reopen_pickup':
        if curr_status not in ['collection_reported', 'collected']:
            conn.close()
            return jsonify({'success': False, 'message': f'Cannot reopen pickup from {curr_status} status.'}), 400
        action_name = 'reopen_pickup'
        actor_type = 'operator'
        notes = 'Operator reopened pickup to Pending (Accidental Collection Fix)'

    elif new_status == 'delivered':
        if curr_status != 'collected':
            conn.close()
            return jsonify({'success': False, 'message': f'Pickup must be in Collected state before marking Delivered. Current: {curr_status}'}), 400
        action_name = 'mark_delivered'
        actor_type = 'operator'
        notes = 'Delivered to Certified Circular Destination Facility'
        delivered_timestamp = '2026-08-14 14:00:00'

    elif action == 'reopen_delivered':
        if curr_status != 'delivered':
            conn.close()
            return jsonify({'success': False, 'message': f'Only delivered pickups can be reopened. Current: {curr_status}'}), 400
        action_name = 'reopen_delivered'
        actor_type = 'admin'
        notes = 'Admin reopened Delivery state back to Collected'
        new_status = 'collected'
    else:
        # Fallback for manual updates
        action_name = 'status_update'
        notes = f'Status updated to {new_status}'

    cursor.execute("UPDATE pickups SET status = ? WHERE id = ?", (new_status, pickup_id))
    cursor.execute("""
        UPDATE pickup_streams SET status = ?, delivered_at = ? WHERE pickup_id = ?
    """, (new_status, delivered_timestamp, pickup_id))

    cursor.execute("""
        INSERT INTO audit_logs (pickup_id, previous_status, new_status, action, actor_type, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (pickup_id, curr_status, new_status, action_name, actor_type, notes))

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'✓ Pickup #{pickup_id} status updated from {curr_status} to {new_status}',
        'pickup_id': pickup_id,
        'previous_status': curr_status,
        'new_status': new_status,
        'action': action_name
    })

@app.route('/api/route/deliver', methods=['POST'])
def api_deliver_route():
    """Mark all collected pickup streams in this batch as delivered to the circular facility."""
    data = request.json or request.form
    pickup_ids = data.get('pickup_ids', [])

    if not pickup_ids:
        return jsonify({'success': False, 'message': 'No pickup_ids provided'}), 400

    conn = get_db()
    cursor = conn.cursor()

    delivered_count = 0
    for pid in pickup_ids:
        current = cursor.execute("SELECT status FROM pickups WHERE id = ?", (pid,)).fetchone()
        if current and current['status'] == 'collected':
            cursor.execute("UPDATE pickups SET status = 'delivered' WHERE id = ?", (pid,))
            cursor.execute("UPDATE pickup_streams SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP WHERE pickup_id = ?", (pid,))
            cursor.execute("""
                INSERT INTO audit_logs (pickup_id, previous_status, new_status, action, actor_type, notes)
                VALUES (?, 'collected', 'delivered', 'mark_delivered', 'operator', 'Delivered to Circular Facility Batch')
            """, (pid,))
            delivered_count += 1

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'🎉 {delivered_count} pickups verified & delivered to Circular Facility!'})

@app.route('/api/route/recalculate', methods=['POST'])
def api_recalculate_route():
    data = request.json or request.form
    van_id = int(data.get('van_id', 1))
    pickup_ids = data.get('pickup_ids', [])
    stream_type = data.get('stream_type', 'wet')

    if not pickup_ids:
        return jsonify({'success': False, 'message': 'No pickup stops provided'}), 400

    conn = get_db()
    van = conn.execute("SELECT * FROM vans WHERE id = ?", (van_id,)).fetchone()
    facility = conn.execute("SELECT * FROM facilities WHERE stream_type = ?", (stream_type,)).fetchone()

    placeholders = ','.join(['?'] * len(pickup_ids))
    stops_rows = conn.execute(f"SELECT id, lat, lng FROM pickups WHERE id IN ({placeholders})", tuple(pickup_ids)).fetchall()
    conn.close()

    stops_map = {s['id']: (s['lat'], s['lng']) for s in stops_rows}
    van_pos = (van['lat'], van['lng'])
    fac_pos = (facility['lat'], facility['lng']) if facility else None

    ordered_points = [van_pos] + [stops_map[pid] for pid in pickup_ids if pid in stops_map]
    if fac_pos:
        ordered_points.append(fac_pos)

    custom_dist = 0.0
    for i in range(len(ordered_points) - 1):
        custom_dist += haversine(ordered_points[i][0], ordered_points[i][1], ordered_points[i+1][0], ordered_points[i+1][1])

    sorted_ids = sorted(pickup_ids)
    naive_points = [van_pos] + [stops_map[pid] for pid in sorted_ids if pid in stops_map]
    if fac_pos:
        naive_points.append(fac_pos)

    naive_dist = 0.0
    for i in range(len(naive_points) - 1):
        naive_dist += haversine(naive_points[i][0], naive_points[i][1], naive_points[i+1][0], naive_points[i+1][1])

    saved_pct = round(((naive_dist - custom_dist) / naive_dist * 100), 1) if naive_dist > 0 else 0.0

    return jsonify({
        'success': True,
        'naive_dist_km': round(naive_dist, 2),
        'custom_dist_km': round(custom_dist, 2),
        'saved_pct': saved_pct
    })

@app.route('/api/route/apply', methods=['POST'])
def api_apply_route():
    data = request.json or request.form
    van_id = int(data.get('van_id', 1))
    pickup_ids = data.get('pickup_ids', [])
    stream_type = data.get('stream_type', 'wet')
    zone = int(data.get('zone', 1)) if data.get('zone') not in ['all', None, ''] else 1
    naive_dist = float(data.get('naive_dist', 0.0))
    opt_dist = float(data.get('opt_dist', 0.0))
    saved_pct = float(data.get('saved_pct', 0.0))

    if not van_id or not pickup_ids:
        return jsonify({'success': False, 'message': 'Missing van_id or pickup_ids'}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.executemany("UPDATE pickups SET assigned_van_id = ? WHERE id = ?", [(van_id, pid) for pid in pickup_ids])
    cursor.execute("UPDATE vans SET status = 'en_route' WHERE id = ?", (van_id,))

    stop_order_json = json.dumps(pickup_ids)
    cursor.execute("""
        INSERT INTO routes (van_id, stream_type, pickup_zone, status, naive_dist_km, opt_dist_km, saved_pct, stop_order_json, applied_at)
        VALUES (?, ?, ?, 'applied', ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (van_id, stream_type, zone, naive_dist, opt_dist, saved_pct, stop_order_json))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'✅ Route applied! Van #{van_id} assigned to {len(pickup_ids)} stops.'})

@app.route('/api/reset-demo', methods=['POST'])
def api_reset_demo():
    seed_database()
    return jsonify({'success': True, 'message': 'Demo database successfully reset to initial 40 seeded pickups.'})

# ----------------------------------------------------
# BACKGROUND VAN SIMULATION
# ----------------------------------------------------
from simulate_trucks import move_trucks

def start_simulation():
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
