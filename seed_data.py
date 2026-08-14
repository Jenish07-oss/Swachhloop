import random
import math
import numpy as np
from sklearn.cluster import KMeans
from database import get_db, init_db

def calculate_green_points(bin_score):
    """
    SwachhLoop 4R Transparent Green Points Formula:
    Base Points = 20
    Score Bonus = floor(bin_score / 10)
    Green Points = 20 + floor(bin_score / 10)
    """
    return 20 + math.floor(bin_score / 10)

def seed():
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    # Clear existing tables cleanly
    cursor.execute("DELETE FROM points_ledger")
    cursor.execute("DELETE FROM pickup_streams")
    cursor.execute("DELETE FROM pickups")
    cursor.execute("DELETE FROM facilities")
    cursor.execute("DELETE FROM vans")
    cursor.execute("DELETE FROM households")

    # Reset SQLite autoincrement sequences
    cursor.execute("DELETE FROM sqlite_sequence")

    # ----------------------------------------------------
    # 1. SEED 4 DESTINATION FACILITIES (Circular Economy)
    # ----------------------------------------------------
    facilities_data = [
        (
            1,
            "GreenCycle Compost & Bio-CNG Plant",
            "Bio-CNG & Composting",
            "wet",
            23.0650,
            72.5750,
            "AMC & GPCB Approved Wet Processing Hub #W-204",
            12000.0
        ),
        (
            2,
            "Ahmedabad Central MRF Facility",
            "Material Recovery Facility (MRF)",
            "dry",
            23.0180,
            72.5350,
            "Automated Optical Sorter & Baler Unit #D-109",
            15000.0
        ),
        (
            3,
            "E-Clean Gujarat Recyclers",
            "CPCB-Registered E-Waste Facility",
            "e_waste",
            23.0850,
            72.5100,
            "CPCB Auth #GJ-EW-2024-884 (Govt Approved)",
            5000.0
        ),
        (
            4,
            "Ultratech RDF Kiln Co-Processing Hub",
            "RDF Cement Kiln Co-Processing",
            "residual",
            22.9800,
            72.6300,
            "Zero-Landfill High-Calorific Energy Recovery #R-042",
            20000.0
        )
    ]
    cursor.executemany("""
        INSERT INTO facilities (id, name, facility_type, stream_type, lat, lng, registration_note, capacity_kg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, facilities_data)

    # ----------------------------------------------------
    # 2. SEED 3 VANS
    # ----------------------------------------------------
    vans_data = [
        (1, "SL-VAN-01", "Vikram Rathod", 23.0385, 72.5480, "idle", 500.0),
        (2, "SL-VAN-02", "Sanjay Patel", 23.0315, 72.5590, "en_route", 500.0),
        (3, "SL-VAN-03", "Anil Chauhan", 23.0445, 72.5410, "idle", 500.0)
    ]
    cursor.executemany("""
        INSERT INTO vans (id, van_code, driver_name, lat, lng, status, capacity_kg)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, vans_data)

    # ----------------------------------------------------
    # 3. SEED 40 HOUSEHOLDS (Single Ward: Navrangpura / University, Ahmedabad)
    # ----------------------------------------------------
    names = [
        "Jenish Patel", "Ramesh Kumar", "Priya Sharma", "Aarav Shah", "Diya Mehta",
        "Kavita Desai", "Bhavin Trivedi", "Hiren Joshi", "Meera Vora", "Chetan Solanki",
        "Pooja Parikh", "Rajesh Dave", "Ananya Bhatt", "Dharmesh Soni", "Neha Panchal",
        "Manish Raval", "Geeta Shukla", "Sunil Makwana", "Tanvi Modi", "Jignesh Limbachiya",
        "Kinjal Gandhi", "Parth Bhavsar", "Ritu Kothari", "Alpesh Patel", "Swati Vyas",
        "Nikhil Pandya", "Deepa Thakkar", "Krunal Chauhan", "Sneha Sanghavi", "Pranav Dani",
        "Shalini Zala", "Gaurav Barot", "Vaishali Nayak", "Harshil Merchant", "Payal Rathod",
        "Devang Shah", "Urvi Acharya", "Yash Vaghela", "Bhakti Patel", "Vipul Mistry"
    ]

    street_segments = [
        "C.G. Road Sector 1", "C.G. Road Sector 2", "C.G. Road Cross Lane",
        "University Campus Road North", "University Campus Road South", "Commerce Six Roads",
        "Gulbai Tekra Main Marg", "Gulbai Tekra Lane 4", "Mithakhali 2nd Avenue",
        "Mithakhali 6th Cross", "Law Garden Perimeter", "Navrangpura Bus Stand Road",
        "Swastik Cross Road", "St. Xavier's Corner", "L.D. Engineering Marg",
        "Panchwati Circle East", "Panchwati Circle West", "Samartheshwar Temple Road",
        "Vijay Cross Roads Block A", "Vijay Cross Roads Block B"
    ]

    households_data = []
    for i in range(1, 41):
        code = f"H{i:03d}"
        name = names[i - 1]
        phone = f"98765{40000 + i}"
        street = street_segments[(i - 1) % len(street_segments)]
        households_data.append((i, code, name, phone, street))

    cursor.executemany("""
        INSERT INTO households (id, household_code, name, phone, street_segment)
        VALUES (?, ?, ?, ?, ?)
    """, households_data)

    # ----------------------------------------------------
    # 4. SEED 40 PICKUPS (Concentrated in 1 Ward, Realistic Jitter)
    # ----------------------------------------------------
    # Seed reproducible random generator
    random.seed(42)
    np.random.seed(42)

    # Ward center (Navrangpura, Ahmedabad: 23.0375, 72.5520)
    # We create 5 neighborhood sub-clusters inside this single ward to mirror real city density
    sub_centers = [
        (23.0390, 72.5510), # C.G. Road / Swastik
        (23.0425, 72.5440), # Commerce Six Roads / University
        (23.0330, 72.5580), # Mithakhali / Law Garden
        (23.0350, 72.5480), # Gulbai Tekra / Panchwati
        (23.0450, 72.5530)  # Navrangpura North / St. Xavier's
    ]

    sample_photos = [
        "https://images.unsplash.com/photo-1530587191325-3db32d826c18?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1611284446314-60a58ac0deb9?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1605600659873-d808a13e4d2a?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1558583082-409143c794ca?auto=format&fit=crop&w=600&q=80"
    ]

    # Realistic Bin Score Distribution:
    # Poor: 0-30, Needs improvement: 31-55, Good: 56-75, Very good: 76-90, Excellent: 91-100
    bin_scores = [
        22, 28,                          # Poor (2)
        35, 42, 48, 52, 54,              # Needs improvement (5)
        58, 62, 65, 68, 70, 72, 74, 75,  # Good (8)
        78, 80, 82, 84, 85, 86, 88, 89, 90, 83, 85, 87, # Very Good (12)
        92, 94, 95, 96, 98, 99, 93, 95, 97, 100, 92, 94, 96 # Excellent (13)
    ]
    random.shuffle(bin_scores)

    statuses = (
        ["pending"] * 18 +
        ["collected"] * 12 +
        ["delivered"] * 10
    )
    random.shuffle(statuses)

    raw_pickups = []
    coords_for_kmeans = []

    for i in range(1, 41):
        center_lat, center_lng = sub_centers[(i - 1) % len(sub_centers)]
        # Micro-jitter within ~300-600m
        lat = round(center_lat + random.uniform(-0.0035, 0.0035), 5)
        lng = round(center_lng + random.uniform(-0.0035, 0.0035), 5)
        coords_for_kmeans.append([lat, lng])

        score = bin_scores[i - 1]
        status = statuses[i - 1]
        photo = sample_photos[(i - 1) % len(sample_photos)]

        # Assigned van logic
        if status in ['collected', 'delivered']:
            assigned_van = (i % 3) + 1
        elif status == 'pending' and i % 2 == 0:
            assigned_van = (i % 3) + 1
        else:
            assigned_van = None

        raw_pickups.append({
            'id': i,
            'household_id': i,
            'lat': lat,
            'lng': lng,
            'bin_score': score,
            'photo_path': photo,
            'status': status,
            'assigned_van_id': assigned_van
        })

    # ----------------------------------------------------
    # 5. KMEANS PICKUP ZONES (K=5 on exact 40 coordinates)
    # ----------------------------------------------------
    kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
    kmeans.fit(np.array(coords_for_kmeans))
    cluster_labels = kmeans.labels_ # 0 to 4

    pickups_data = []
    for i, p in enumerate(raw_pickups):
        zone_number = int(cluster_labels[i]) + 1 # 1 to 5
        pickups_data.append((
            p['id'],
            p['household_id'],
            p['lat'],
            p['lng'],
            p['bin_score'],
            p['photo_path'],
            p['status'],
            p['assigned_van_id'],
            zone_number
        ))

    cursor.executemany("""
        INSERT INTO pickups (id, household_id, lat, lng, bin_score, photo_path, status, assigned_van_id, pickup_zone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, pickups_data)

    # ----------------------------------------------------
    # 6. SEED PICKUP STREAMS (4R Segregated Collection)
    # ----------------------------------------------------
    # Each pickup gets 1 to 4 streams
    # Facility mapping:
    # wet -> facility_id 1
    # dry -> facility_id 2
    # e_waste -> facility_id 3
    # residual -> facility_id 4
    facility_map = {
        'wet': 1,
        'dry': 2,
        'e_waste': 3,
        'residual': 4
    }

    streams_data = []
    stream_id = 1

    for p in raw_pickups:
        p_id = p['id']
        p_status = p['status']

        # Determine which streams are included in this pickup
        # Wet & Dry are almost always present; E-Waste & Residual appear periodically
        included_streams = ['wet', 'dry']
        if p_id % 3 == 0:
            included_streams.append('e_waste')
        if p_id % 2 == 0:
            included_streams.append('residual')

        for st in included_streams:
            if st == 'wet':
                kg = round(random.uniform(2.0, 7.5), 1)
            elif st == 'dry':
                kg = round(random.uniform(1.5, 6.0), 1)
            elif st == 'e_waste':
                kg = round(random.uniform(0.5, 3.5), 1)
            else: # residual
                kg = round(random.uniform(1.0, 4.0), 1)

            st_status = p_status
            delivered_at = '2026-08-14 14:00:00' if p_status == 'delivered' else None

            streams_data.append((
                stream_id,
                p_id,
                st,
                kg,
                facility_map[st],
                st_status,
                delivered_at
            ))
            stream_id += 1

    cursor.executemany("""
        INSERT INTO pickup_streams (id, pickup_id, stream_type, estimated_kg, facility_id, status, delivered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, streams_data)

    # ----------------------------------------------------
    # 7. SEED POINTS LEDGER (Green Points Formula)
    # ----------------------------------------------------
    ledger_data = []
    ledger_id = 1

    for p in raw_pickups:
        hh_id = p['household_id']
        p_id = p['id']
        score = p['bin_score']
        points = calculate_green_points(score)
        reason = f"Segregated 4R Pickup #{p_id} (Bin Score: {score}/100)"

        ledger_data.append((
            ledger_id,
            hh_id,
            p_id,
            points,
            reason
        ))
        ledger_id += 1

    cursor.executemany("""
        INSERT INTO points_ledger (id, household_id, pickup_id, points, reason)
        VALUES (?, ?, ?, ?, ?)
    """, ledger_data)

    conn.commit()
    conn.close()

    print(f"Successfully seeded SwachhLoop 4R Database:")
    print(f"- 4 Destination Facilities (Wet, Dry, E-Waste, Residual)")
    print(f"- 3 Collection Vans")
    print(f"- 40 Households (Single Ward: Navrangpura, Ahmedabad)")
    print(f"- 40 Pickups clustered into 5 KMeans Zones")
    print(f"- {len(streams_data)} Segregated Stream records (UNIQUE per stream type)")
    print(f"- 40 Green Points Ledger records")

if __name__ == '__main__':
    seed()
