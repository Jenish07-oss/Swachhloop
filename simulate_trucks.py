"""
Simulated truck movement for demo purposes.
Run this script in a separate terminal OR via Flask background thread to see
trucks animate on the admin map.
"""
import time
import random
import math
from database import get_db

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def move_trucks():
    """Move each truck slightly toward a random nearby report every 5 sec."""
    conn = get_db()
    cursor = conn.cursor()
    
    vehicles = cursor.execute("SELECT * FROM vehicles").fetchall()
    
    for v in vehicles:
        # Find nearest pending report
        reports = cursor.execute(
            "SELECT * FROM waste_reports WHERE status IN ('Reported', 'Assigned', 'In Progress') ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        
        if not reports:
            continue
        
        # Move vehicle toward that report (small step per tick)
        step_lat = (reports['lat'] - v['lat']) * 0.05
        step_lon = (reports['lon'] - v['lon']) * 0.05
        
        new_lat = round(v['lat'] + step_lat, 5)
        new_lon = round(v['lon'] + step_lon, 5)
        
        # If arrived within 0.0005 degrees (~50m), update status
        if haversine(new_lat, new_lon, reports['lat'], reports['lon']) < 0.05:
            cursor.execute("UPDATE waste_reports SET status = 'In Progress' WHERE id = ? AND status = 'Assigned'", (reports['id'],))
            cursor.execute("UPDATE vehicles SET status = 'On Route' WHERE id = ?", (v['id'],))
        
        # Add random jitter for realistic movement
        new_lat += random.uniform(-0.0005, 0.0005)
        new_lon += random.uniform(-0.0005, 0.0005)
        
        cursor.execute("UPDATE vehicles SET lat = ?, lon = ? WHERE id = ?", (new_lat, new_lon, v['id']))
    
    conn.commit()
    conn.close()
    print(f"[{time.strftime('%H:%M:%S')}] Trucks moved...")

if __name__ == '__main__':
    print("Starting truck simulation. Press Ctrl+C to stop.")
    while True:
        move_trucks()
        time.sleep(5)