import random
import math
import numpy as np
from sklearn.cluster import KMeans
from database import get_db, init_db
from brand import calculate_green_points, format_pickup_code

def seed():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS audit_logs")
    cursor.execute("DROP TABLE IF EXISTS routes")
    cursor.execute("DROP TABLE IF EXISTS points_ledger")
    cursor.execute("DROP TABLE IF EXISTS pickup_streams")
    cursor.execute("DROP TABLE IF EXISTS pickups")
    cursor.execute("DROP TABLE IF EXISTS facilities")
    cursor.execute("DROP TABLE IF EXISTS vans")
    cursor.execute("DROP TABLE IF EXISTS households")
    cursor.execute("DROP TABLE IF EXISTS societies")
    cursor.execute("DROP TABLE IF EXISTS sms_logs")
    cursor.execute("DROP TABLE IF EXISTS driver_shifts")
    conn.commit()
    conn.close()

    init_db()
    conn = get_db()
    cursor = conn.cursor()

    # ----------------------------------------------------
    # 1. SEED 4 SOCIETIES (Phase 2 First-Class Entity)
    # ----------------------------------------------------
    societies_data = [
        (1, 'SOC-001', 'Shivalik Heights', 'Rajesh Mehta', '9825012345', 'Commerce Six Roads, Navrangpura', 'Main Gate B Block Security Post', 'Navrangpura'),
        (2, 'SOC-002', 'Iscon Platinum', 'Sanjay Shah', '9825012346', 'Mithakhali 2nd Avenue, Navrangpura', 'Basement Wheelie Bin Bay', 'Navrangpura'),
        (3, 'SOC-003', 'Goyal Intercity', 'Amit Trivedi', '9825012347', 'L.D. Engineering Marg, Navrangpura', 'Society Clubhouse Gate', 'Navrangpura'),
        (4, 'SOC-004', 'Akshardham Residency', 'Pooja Barot', '9825012348', 'Swastik Cross Road, Navrangpura', 'Rear Service Gate', 'Navrangpura')
    ]
    cursor.executemany("""
        INSERT INTO societies (id, society_code, name, manager_name, phone, address, collection_point, ward)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, societies_data)

    # ----------------------------------------------------
    # 2. SEED 4 DESTINATION FACILITIES (Circular Economy)
    # ----------------------------------------------------
    facilities_data = [
        (1, "GreenCycle Compost & Bio-CNG Plant", "Bio-CNG & Composting", "wet", 23.0650, 72.5750, "Approved Wet Processing Hub #W-204", 500.0, 280.0),
        (2, "Ahmedabad Central MRF Facility", "Material Recovery Facility (MRF)", "dry", 23.0180, 72.5350, "Automated Optical Sorter & Baler Unit #D-109", 600.0, 420.0),
        (3, "E-Clean Gujarat Recyclers", "CPCB Certified E-Waste Dismantler", "e_waste", 23.0800, 72.5200, "Safe PCB & Battery Recycling Line #E-008", 150.0, 45.0),
        (4, "Ultratech RDF Kiln Co-Processing", "Cement Kiln Energy Recovery", "residual", 22.9850, 72.6050, "High-temp Co-processing Non-Recyclables #R-401", 300.0, 110.0)
    ]
    cursor.executemany("""
        INSERT INTO facilities (id, name, facility_type, stream_type, lat, lng, registration_note, capacity_kg, current_load_kg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, facilities_data)

    # ----------------------------------------------------
    # 3. SEED 3 COLLECTION VANS
    # ----------------------------------------------------
    vans_data = [
        (1, "SL-VAN-01", "Vikram Rathod", 23.0370, 72.5525, "active", 500.0, 320.0),
        (2, "SL-VAN-02", "Dharmesh Solanki", 23.0420, 72.5610, "active", 500.0, 210.0),
        (3, "SL-VAN-03", "Prakash Vaghela", 23.0310, 72.5440, "idle", 500.0, 0.0)
    ]
    cursor.executemany("""
        INSERT INTO vans (id, van_code, driver_name, lat, lng, status, capacity_kg, current_payload_kg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, vans_data)

    # ----------------------------------------------------
    # 4. SEED 40 HOUSEHOLDS (Navrangpura Ward)
    # ----------------------------------------------------
    citizen_names = [
        "Jenish Patel", "Aarav Shah", "Pooja Mehta", "Rohan Joshi", "Ananya Sharma",
        "Kavita Desai", "Hardik Patel", "Bhavna Trivedi", "Meera Vora", "Siddharth Dave",
        "Ritu Shah", "Rajesh Dave", "Kinjal Prajapati", "Jignesh Soni", "Neha Panchal",
        "Vikas Bhatt", "Swati Parikh", "Sunil Makwana", "Daksha Raval", "Chirag Barot",
        "Sheetal Gandhi", "Mahesh Solanki", "Kiran Pandya", "Alpesh Patel", "Geeta Shukla",
        "Dhaval Panchal", "Deepa Thakkar", "Nilesh Mistry", "Falguni Dave", "Pranav Dani",
        "Hina Raval", "Ketan Mehta", "Vaishali Nayak", "Hitesh Joshi", "Varsha Somani",
        "Devang Shah", "Tanvi Brahmbhatt", "Mukesh Thaker", "Bhakti Patel", "Jayesh Chawda"
    ]

    street_segments = [
        "C.G. Road Axis", "Commerce Six Roads", "Mithakhali 2nd Avenue", "Navrangpura Bus Stand Road",
        "L.D. Engineering Marg", "Samartheshwar Temple Road", "St. Xavier's High School Lane",
        "University Campus Road North", "Gulbai Tekra Main Marg", "Mithakhali 6th Cross",
        "Swastik Cross Road", "Panchwati Circle East", "Vijay Cross Roads Block A"
    ]

    households_data = []
    for i in range(1, 41):
        hh_code = f"H{i:03d}"
        name = citizen_names[i - 1]
        phone = f"9825{random.randint(100000, 999999)}"
        street = random.choice(street_segments)
        is_soc = 1 if i in [1, 2, 3, 4] else 0
        soc_id = i if is_soc else None
        households_data.append((i, hh_code, name, phone, street, is_soc, soc_id))

    cursor.executemany("""
        INSERT INTO households (id, household_code, name, phone, street_segment, is_society, society_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, households_data)

    # ----------------------------------------------------
    # 5. SEED 40 PICKUPS (Navrangpura Ward Clustered Geo)
    # ----------------------------------------------------
    np.random.seed(42)
    center_lat, center_lng = 23.0375, 72.5520
    lats = np.random.normal(center_lat, 0.009, 40)
    lngs = np.random.normal(center_lng, 0.009, 40)

    coordinates = np.column_stack((lats, lngs))
    kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
    pickup_zones = kmeans.fit_predict(coordinates) + 1

    statuses_pool = [
        'pending', 'pending', 'pending',
        'collection_reported', 'collection_reported',
        'collected', 'collected', 'delivered'
    ]

    raw_pickups = []
    for i in range(1, 41):
        p_code = format_pickup_code(i)
        status = random.choice(statuses_pool)
        if i == 1:
            status = 'pending'
        elif i == 2:
            status = 'collection_reported'
        elif i == 3:
            status = 'collected'
        elif i == 4:
            status = 'delivered'

        score = random.randint(65, 98)
        zone = int(pickup_zones[i - 1])
        van_id = ((zone - 1) % 3) + 1 if status in ['collection_reported', 'collected', 'delivered'] else None
        is_soc = 1 if i in [1, 2, 3, 4] else 0
        soc_id = i if is_soc else None

        raw_pickups.append({
            'id': i,
            'pickup_code': p_code,
            'household_id': i,
            'society_id': soc_id,
            'is_society': is_soc,
            'address': f"{societies_data[soc_id-1][1]}, {societies_data[soc_id-1][4]}" if is_soc else f"{street}, Navrangpura, Ahmedabad, Gujarat 380009",
            'lat': round(float(lats[i - 1]), 5),
            'lng': round(float(lngs[i - 1]), 5),
            'bin_score': score,
            'photo_path': f"/static/images/bins/sample_bin_{((i - 1) % 4) + 1}.svg",
            'status': status,
            'assigned_van_id': van_id,
            'pickup_zone': zone
        })

    # ----------------------------------------------------
    # 6. SEED SEGREGATED STREAMS & ESTIMATED KG PER STREAM
    # ----------------------------------------------------
    streams_data = []
    stream_id = 1
    ledger_data = []
    ledger_id = 1

    for p in raw_pickups:
        p_id = p['id']
        hh_id = p['household_id']
        soc_id = p['society_id']
        is_soc = p['is_society']
        score = p['bin_score']

        # Determine streams present for this pickup
        # Every pickup has Wet and Dry; E-Waste and Residual are optional
        has_wet = True
        has_dry = True
        has_ewaste = (p_id % 3 == 0)
        has_residual = (p_id % 2 == 0)

        stream_kg_dict = {}

        if has_wet:
            wet_kg = round(random.uniform(2.5, 6.0), 1)
            stream_kg_dict['wet'] = wet_kg
            streams_data.append((stream_id, p_id, 'wet', wet_kg, 1, 'pending' if p['status'] == 'pending' else 'delivered', None))
            stream_id += 1

        if has_dry:
            dry_kg = round(random.uniform(1.8, 5.5), 1)
            stream_kg_dict['dry'] = dry_kg
            streams_data.append((stream_id, p_id, 'dry', dry_kg, 2, 'pending' if p['status'] == 'pending' else 'delivered', None))
            stream_id += 1

        if has_ewaste:
            ewaste_kg = round(random.uniform(0.5, 3.0), 1)
            stream_kg_dict['e_waste'] = ewaste_kg
            streams_data.append((stream_id, p_id, 'e_waste', ewaste_kg, 3, 'pending' if p['status'] == 'pending' else 'delivered', None))
            stream_id += 1

        if has_residual:
            residual_kg = round(random.uniform(1.0, 3.5), 1)
            stream_kg_dict['residual'] = residual_kg
            streams_data.append((stream_id, p_id, 'residual', residual_kg, 4, 'pending' if p['status'] == 'pending' else 'delivered', None))
            stream_id += 1

        total_kg = sum(stream_kg_dict.values())
        points = calculate_green_points(stream_kg_dict, bin_score=score, is_society=is_soc)

        p['total_kg'] = round(total_kg, 1)
        p['earned_points'] = points

        # Green points ledger
        ledger_data.append((
            ledger_id,
            hh_id,
            soc_id,
            p_id,
            points,
            f"Segregated 4-Stream Collection {p['pickup_code']} ({p['total_kg']} kg, Score: {score}/100)"
        ))
        ledger_id += 1

    # Insert Pickups
    cursor.executemany("""
        INSERT INTO pickups (
            id, pickup_code, household_id, society_id, is_society,
            address, lat, lng, bin_score, photo_path, status,
            assigned_van_id, pickup_zone, total_kg, earned_points
        )
        VALUES (
            :id, :pickup_code, :household_id, :society_id, :is_society,
            :address, :lat, :lng, :bin_score, :photo_path, :status,
            :assigned_van_id, :pickup_zone, :total_kg, :earned_points
        )
    """, raw_pickups)

    # Insert Streams
    cursor.executemany("""
        INSERT INTO pickup_streams (id, pickup_id, stream_type, estimated_kg, facility_id, status, delivered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, streams_data)

    # Insert Points Ledger
    cursor.executemany("""
        INSERT INTO points_ledger (id, household_id, society_id, pickup_id, points, reason)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ledger_data)

    # ----------------------------------------------------
    # 7. SEED USERS & NOTIFICATION SIMULATION
    # ----------------------------------------------------
    cursor.execute('''
        INSERT INTO users (username, password, name, role, phone, locality, household_id, society_id, van_id)
        VALUES 
            ('jenish', 'jenish123', 'Jenish Patel', 'citizen', '9876543210', 'Navrangpura', 1, NULL, NULL),
            ('society', 'society123', 'Rajesh Mehta', 'society_manager', '9825012345', 'Shivalik Heights', NULL, 1, NULL),
            ('vikram', 'vikram123', 'Vikram Thakor', 'driver', '9988776655', 'Navrangpura Ward', NULL, NULL, 1),
            ('admin', 'admin123', 'Municipal Operations Admin', 'admin', '0792650000', 'Central Control Room', NULL, NULL, NULL)
    ''')

    # Seed Sample SMS Logs
    sms_samples = [
        ('9876543210', 'Your NagarLoop pickup NL-2026-00001 is booked for tomorrow morning. Keep 4 streams segregated.', 'booking_confirmed', 1),
        ('9876543210', 'Your NagarLoop collection van SL-VAN-01 is approaching your society.', 'van_approaching', 1),
        ('9825012345', 'Shivalik Heights: 240L wheelie bins pickup verified. +72 Green Points credited.', 'points_credited', 2)
    ]
    cursor.executemany("""
        INSERT INTO sms_logs (recipient_phone, message, event_type, pickup_id)
        VALUES (?, ?, ?, ?)
    """, sms_samples)

    conn.commit()
    conn.close()

    print(f"Successfully seeded NagarLoop Phase 2 Database:")
    print(f"- 4 Societies (Shivalik Heights, Iscon Platinum, Goyal Intercity, Akshardham)")
    print(f"- 4 Destination Facilities with real capacities")
    print(f"- 3 Collection Vans")
    print(f"- 40 Households (Single Ward: Navrangpura)")
    print(f"- 40 Pickups with NL-2026-XXXXX reference codes & estimated KG per stream")
    print(f"- {len(streams_data)} Segregated Stream records")
    print(f"- 40 Points Ledger records (Proportional formula)")
    print(f"- 4 User Accounts (jenish, society, vikram, admin)")
    print(f"- Simulated SMS Notification logs")

if __name__ == '__main__':
    seed()
