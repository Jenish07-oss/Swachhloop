import random
import os
from database import get_db, init_db

def seed():
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    # Clear existing data
    cursor.execute("DELETE FROM assignments")
    cursor.execute("DELETE FROM waste_reports")
    cursor.execute("DELETE FROM vehicles")
    cursor.execute("DELETE FROM users")

    # Seed Default Citizen Users
    users = [
        ("Jenish Patel", "citizen", "9876543210", 50),
        ("Ramesh Kumar", "citizen", "9876543211", 30),
        ("Priya Sharma", "citizen", "9876543212", 20),
        ("Admin Control Center", "admin", "9000000000", 0)
    ]
    cursor.executemany("INSERT INTO users (name, role, phone, green_points) VALUES (?, ?, ?, ?)", users)

    # Seed Vehicles (Ahmedabad Depots)
    vehicles = [
        ("GJ-01-AA-1001", "Vikram Rathod", 23.0225, 72.5714, "Idle", "9988776651"),  # Riverfront
        ("GJ-01-AA-1002", "Sanjay Patel", 23.0500, 72.5300, "Idle", "9988776652"),   # SG Highway
        ("GJ-01-AA-1003", "Anil Chauhan", 22.9900, 72.6000, "Idle", "9988776653")   # Maninagar
    ]
    cursor.executemany("INSERT INTO vehicles (number, driver, lat, lon, status, phone) VALUES (?, ?, ?, ?, ?, ?)", vehicles)

    # Waste Types
    waste_types = ["Mixed", "Plastic", "Organic", "E-waste", "Construction"]
    statuses = ["Reported", "Assigned", "In Progress", "Resolved"]

    # Sample images
    sample_images = [
        "https://images.unsplash.com/photo-1530587191325-3db32d826c18?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1611284446314-60a58ac0deb9?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1605600659873-d808a13e4d2a?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1558583082-409143c794ca?auto=format&fit=crop&w=600&q=80"
    ]

    resolved_images = [
        "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1584467735871-8e85353a8413?auto=format&fit=crop&w=600&q=80"
    ]

    # Ahmedabad Wards / Hotspot Clusters Centers
    clusters = [
        (23.0225, 72.5714), # Riverfront / Ashram Road
        (23.0375, 72.5312), # Navrangpura / Vastrapur
        (22.9950, 72.5980), # Maninagar
        (23.0600, 72.5800), # Sabarmati
        (23.0100, 72.5200)  # Prahlad Nagar
    ]

    # Generate 50 waste reports around the 5 clusters
    random.seed(42) # Reproducible seed data
    reports = []
    
    for i in range(50):
        # Pick a cluster
        center_lat, center_lon = random.choice(clusters)
        # Add random jitter (approx 1-2 km radius)
        lat = center_lat + random.uniform(-0.012, 0.012)
        lon = center_lon + random.uniform(-0.012, 0.012)
        
        w_type = random.choice(waste_types)
        status = random.choices(statuses, weights=[0.35, 0.25, 0.15, 0.25])[0]
        user_id = random.randint(1, 3)
        img = random.choice(sample_images)
        res_img = random.choice(resolved_images) if status == "Resolved" else None
        
        desc = f"Garbage accumulation reported near Ward {random.randint(1, 15)}, {w_type} waste overflow."

        reports.append((user_id, round(lat, 5), round(lon, 5), w_type, desc, img, status, res_img))

    cursor.executemany("""
        INSERT INTO waste_reports (user_id, lat, lon, waste_type, description, image_url, status, resolved_image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, reports)

    # Assign some reports to vehicles
    cursor.execute("SELECT id FROM waste_reports WHERE status IN ('Assigned', 'In Progress')")
    active_reports = cursor.fetchall()
    
    for row in active_reports:
        rep_id = row['id']
        veh_id = random.randint(1, 3)
        cursor.execute("INSERT INTO assignments (report_id, vehicle_id, status) VALUES (?, ?, 'Assigned')", (rep_id, veh_id))

    conn.commit()
    conn.close()
    print("Database seeded with 50 reports and 3 vehicles successfully.")

if __name__ == '__main__':
    seed()
