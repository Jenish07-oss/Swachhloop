"""
Simulated van movement for demo purposes in SwachhLoop 4R.
Moves collection vans toward assigned pickups or destination facilities.
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
    """Move each van slightly toward assigned pending/collected pickups."""
    conn = get_db()
    cursor = conn.cursor()

    vans = cursor.execute("SELECT * FROM vans").fetchall()

    for v in vans:
        # Find an assigned pickup that is pending or collected
        pickup = cursor.execute("""
            SELECT * FROM pickups 
            WHERE assigned_van_id = ? AND status IN ('pending', 'collected')
            ORDER BY id ASC LIMIT 1
        """, (v['id'],)).fetchone()

        if not pickup:
            # If no assigned pickup, pick any unassigned pending pickup to simulate movement
            pickup = cursor.execute("""
                SELECT * FROM pickups 
                WHERE status = 'pending'
                ORDER BY RANDOM() LIMIT 1
            """).fetchone()

        if not pickup:
            continue

        # Move van toward that pickup
        step_lat = (pickup['lat'] - v['lat']) * 0.05
        step_lng = (pickup['lng'] - v['lng']) * 0.05

        new_lat = round(v['lat'] + step_lat, 5)
        new_lng = round(v['lng'] + step_lng, 5)

        # Arrived within ~50m
        dist = haversine(new_lat, new_lng, pickup['lat'], pickup['lng'])
        if dist < 0.05:
            if pickup['status'] == 'pending':
                cursor.execute("UPDATE pickups SET status = 'collected' WHERE id = ?", (pickup['id'],))
                cursor.execute("UPDATE pickup_streams SET status = 'collected' WHERE pickup_id = ?", (pickup['id'],))
                cursor.execute("UPDATE vans SET status = 'en_route' WHERE id = ?", (v['id'],))

        # Add tiny jitter for realistic movement
        new_lat += random.uniform(-0.0003, 0.0003)
        new_lng += random.uniform(-0.0003, 0.0003)

        cursor.execute("UPDATE vans SET lat = ?, lng = ? WHERE id = ?", (new_lat, new_lng, v['id']))

    conn.commit()
    conn.close()

if __name__ == '__main__':
    print("Starting SwachhLoop 4R van simulation. Press Ctrl+C to stop.")
    while True:
        try:
            move_trucks()
            time.sleep(5)
        except Exception as e:
            print(f"Sim error: {e}")
            time.sleep(5)