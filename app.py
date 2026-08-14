import os
import math
import time
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from database import get_db, init_db
from sklearn.cluster import KMeans
import numpy as np

app = Flask(__name__)
app.secret_key = 'swachhloop-sih-2026-secret-key'

# Ensure uploads folder exists
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Haversine distance in km
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ----------------------------------------------------
# CITIZEN ROUTES
# ----------------------------------------------------

@app.route('/')
def citizen_home():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    conn.close()
    return render_template('citizen_report.html', user=user)

@app.route('/report', methods=['POST'])
def submit_report():
    user_id = 1 # Default citizen user for demo
    lat = float(request.form.get('lat', 23.0225))
    lon = float(request.form.get('lon', 72.5714))
    waste_type = request.form.get('waste_type', 'Mixed')
    description = request.form.get('description', '')
    
    # Handle photo upload
    image_file = request.files.get('photo')
    image_url = "https://images.unsplash.com/photo-1530587191325-3db32d826c18?auto=format&fit=crop&w=600&q=80"
    if image_file and image_file.filename != '':
        filename = f"report_{os.urandom(4).hex()}_{image_file.filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_file.save(filepath)
        image_url = f"/static/uploads/{filename}"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO waste_reports (user_id, lat, lon, waste_type, description, image_url, status)
        VALUES (?, ?, ?, ?, ?, ?, 'Reported')
    """, (user_id, lat, lon, waste_type, description, image_url))
    
    # Earn +10 Green Points
    cursor.execute("UPDATE users SET green_points = green_points + 10 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash("Report submitted successfully! You earned +10 Green Points 🌿", "success")
    return redirect(url_for('my_reports'))

@app.route('/my-reports')
def my_reports():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    reports = conn.execute("""
        SELECT * FROM waste_reports 
        WHERE user_id = 1 
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return render_template('citizen_my_reports.html', user=user, reports=reports)

# ----------------------------------------------------
# ADMIN ROUTES
# ----------------------------------------------------

@app.route('/admin')
def admin_dashboard():
    conn = get_db()
    total_reports = conn.execute("SELECT COUNT(*) FROM waste_reports").fetchone()[0]
    pending_reports = conn.execute("SELECT COUNT(*) FROM waste_reports WHERE status = 'Reported'").fetchone()[0]
    active_vehicles = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    resolved_today = conn.execute("SELECT COUNT(*) FROM waste_reports WHERE status = 'Resolved'").fetchone()[0]
    
    vehicles = conn.execute("SELECT * FROM vehicles").fetchall()
    reports = conn.execute("SELECT * FROM waste_reports ORDER BY id DESC").fetchall()
    conn.close()
    
    return render_template('admin_dashboard.html',
                           total=total_reports,
                           pending=pending_reports,
                           vehicles_count=active_vehicles,
                           resolved=resolved_today,
                           vehicles=vehicles,
                           reports=reports)

@app.route('/admin/route/<int:vehicle_id>')
def admin_route_optimization(vehicle_id):
    conn = get_db()
    vehicle = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    
    # Get all reports assigned to or pending for this vehicle
    assigned_reports = conn.execute("""
        SELECT wr.* FROM waste_reports wr
        JOIN assignments a ON wr.id = a.report_id
        WHERE a.vehicle_id = ? AND wr.status IN ('Assigned', 'In Progress')
    """, (vehicle_id,)).fetchall()
    
    if not assigned_reports:
        # Fallback: get top 6 nearest pending reports
        assigned_reports = conn.execute("SELECT * FROM waste_reports WHERE status = 'Reported' LIMIT 6").fetchall()

    stops = [(r['lat'], r['lon'], r['id'], r['waste_type'], r['description']) for r in assigned_reports]
    
    conn.close()

    if not stops:
        return render_template('admin_route.html', vehicle=vehicle, route=[], naive_dist=0, opt_dist=0, saved_pct=0)

    # Depot / Vehicle start position
    start_pos = (vehicle['lat'], vehicle['lon'])
    all_points = [start_pos] + [(s[0], s[1]) for s in stops]

    # Naive distance (in order of DB)
    naive_dist = 0
    for i in range(len(all_points) - 1):
        naive_dist += haversine(all_points[i][0], all_points[i][1], all_points[i+1][0], all_points[i+1][1])

    # Nearest Neighbor Algorithm
    unvisited = list(range(1, len(all_points)))
    current = 0
    optimized_order = [0]
    
    while unvisited:
        nearest = min(unvisited, key=lambda idx: haversine(all_points[current][0], all_points[current][1], all_points[idx][0], all_points[idx][1]))
        optimized_order.append(nearest)
        unvisited.remove(nearest)
        current = nearest

    # Optimized distance
    opt_dist = 0
    for i in range(len(optimized_order) - 1):
        p1 = all_points[optimized_order[i]]
        p2 = all_points[optimized_order[i+1]]
        opt_dist += haversine(p1[0], p1[1], p2[0], p2[1])

    saved_pct = round(((naive_dist - opt_dist) / naive_dist * 100), 1) if naive_dist > 0 else 0

    # Ordered route items
    ordered_stops = []
    for idx in optimized_order[1:]:
        stop_info = stops[idx - 1]
        ordered_stops.append({
            'id': stop_info[2],
            'lat': stop_info[0],
            'lon': stop_info[1],
            'type': stop_info[3],
            'desc': stop_info[4]
        })

    return render_template('admin_route.html',
                           vehicle=vehicle,
                           stops=ordered_stops,
                           naive_dist=round(naive_dist, 2),
                           opt_dist=round(opt_dist, 2),
                           saved_pct=saved_pct)

# ----------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------

@app.route('/api/reports')
def api_reports():
    conn = get_db()
    reports = conn.execute("SELECT * FROM waste_reports").fetchall()
    conn.close()
    return jsonify([dict(r) for r in reports])

@app.route('/api/vehicles')
def api_vehicles():
    conn = get_db()
    vehicles = conn.execute("SELECT * FROM vehicles").fetchall()
    conn.close()
    return jsonify([dict(v) for v in vehicles])

@app.route('/api/assign', methods=['POST'])
def api_assign():
    data = request.json
    report_id = data.get('report_id')
    vehicle_id = data.get('vehicle_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Update report status
    cursor.execute("UPDATE waste_reports SET status = 'Assigned' WHERE id = ?", (report_id,))
    
    # Insert assignment
    cursor.execute("INSERT INTO assignments (report_id, vehicle_id, status) VALUES (?, ?, 'Assigned')", (report_id, vehicle_id))
    
    # Set vehicle status to Busy
    cursor.execute("UPDATE vehicles SET status = 'On Route' WHERE id = ?", (vehicle_id,))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Vehicle assigned successfully'})

@app.route('/api/status/<int:report_id>', methods=['POST'])
def api_update_status(report_id):
    data = request.json or request.form
    new_status = data.get('status', 'Resolved')
    resolved_img = data.get('resolved_image_url', 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=600&q=80')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE waste_reports SET status = ?, resolved_image_url = ? WHERE id = ?", (new_status, resolved_img, report_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Status updated to {new_status}'})

@app.route('/api/hotspots')
def api_hotspots():
    conn = get_db()
    reports = conn.execute("SELECT lat, lon FROM waste_reports WHERE status != 'Resolved'").fetchall()
    conn.close()

    if len(reports) < 5:
        return jsonify({'hotspots': []})

    coords = np.array([[r['lat'], r['lon']] for r in reports])
    
    # KMeans with k=5 clusters
    kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
    kmeans.fit(coords)
    
    centers = kmeans.cluster_centers_
    labels = kmeans.labels_
    
    hotspots = []
    for i, center in enumerate(centers):
        count = int(np.sum(labels == i))
        hotspots.append({
            'lat': float(center[0]),
            'lon': float(center[1]),
            'intensity': count
        })

    return jsonify({'hotspots': hotspots})

@app.route('/api/charts')
def api_charts():
    conn = get_db()
    
    # Waste type distribution
    waste_types = conn.execute("SELECT waste_type, COUNT(*) as count FROM waste_reports GROUP BY waste_type").fetchall()
    
    # Status distribution
    statuses = conn.execute("SELECT status, COUNT(*) as count FROM waste_reports GROUP BY status").fetchall()
    
    conn.close()
    
    return jsonify({
        'waste_types': {r['waste_type']: r['count'] for r in waste_types},
        'statuses': {r['status']: r['count'] for r in statuses}
    })

# ----------------------------------------------------
# BACKGROUND TRUCK SIMULATION (auto-runs on app start)
# ----------------------------------------------------
from simulate_trucks import move_trucks

def start_simulation():
    """Run truck simulation in background thread (only in production, not reloader)."""
    while True:
        try:
            time.sleep(5)
            move_trucks()
        except Exception as e:
            print(f"Sim error: {e}")

if __name__ == '__main__':
    init_db()
    # Auto-start simulation in background
    sim_thread = threading.Thread(target=start_simulation, daemon=True)
    sim_thread.start()
    print("Truck simulation started in background...")
    # Use PORT from env (Render) or default 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
