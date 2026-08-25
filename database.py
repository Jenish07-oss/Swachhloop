import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'swachhloop.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Households table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS households (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            household_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            street_segment TEXT NOT NULL,
            is_society INTEGER DEFAULT 0,
            society_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Societies table (Phase 2 First-Class Entity)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS societies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            society_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            manager_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            collection_point TEXT NOT NULL,
            ward TEXT DEFAULT 'Navrangpura',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. Vans table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            van_code TEXT UNIQUE NOT NULL,
            driver_name TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            status TEXT DEFAULT 'idle',
            capacity_kg REAL DEFAULT 500.0,
            current_payload_kg REAL DEFAULT 0.0
        )
    ''')

    # 4. Facilities table (Circular Economy Destinations & Capacities)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            facility_type TEXT NOT NULL,
            stream_type TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            registration_note TEXT,
            capacity_kg REAL DEFAULT 1000.0,
            current_load_kg REAL DEFAULT 0.0
        )
    ''')

    # 5. Pickups table (Rich Phase 2 Model)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pickups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pickup_code TEXT,
            household_id INTEGER,
            society_id INTEGER,
            is_public INTEGER DEFAULT 0,
            is_society INTEGER DEFAULT 0,
            reporter_name TEXT,
            reporter_phone TEXT,
            public_description TEXT,
            address TEXT,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            bin_score INTEGER DEFAULT 75,
            photo_path TEXT,
            status TEXT DEFAULT 'pending',
            problem_reason TEXT,
            problem_notes TEXT,
            rescheduled_date TEXT,
            rescheduled_window TEXT,
            assigned_van_id INTEGER,
            pickup_zone INTEGER DEFAULT 1,
            total_kg REAL DEFAULT 0.0,
            earned_points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (household_id) REFERENCES households(id),
            FOREIGN KEY (society_id) REFERENCES societies(id),
            FOREIGN KEY (assigned_van_id) REFERENCES vans(id)
        )
    ''')

    # 6. Pickup Streams table (1 Pickup -> Multiple Segregated Streams with Estimated KG)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pickup_streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pickup_id INTEGER NOT NULL,
            stream_type TEXT NOT NULL,
            estimated_kg REAL DEFAULT 0.0,
            facility_id INTEGER,
            status TEXT DEFAULT 'pending',
            delivered_at TIMESTAMP,
            UNIQUE(pickup_id, stream_type),
            FOREIGN KEY (pickup_id) REFERENCES pickups(id) ON DELETE CASCADE,
            FOREIGN KEY (facility_id) REFERENCES facilities(id)
        )
    ''')

    # 7. Points Ledger table (Green Points tracking)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS points_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            household_id INTEGER,
            society_id INTEGER,
            pickup_id INTEGER,
            points INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (household_id) REFERENCES households(id),
            FOREIGN KEY (society_id) REFERENCES societies(id),
            FOREIGN KEY (pickup_id) REFERENCES pickups(id) ON DELETE SET NULL
        )
    ''')

    # 8. Routes table (Persistent Route Batches)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            van_id INTEGER NOT NULL,
            stream_type TEXT NOT NULL,
            pickup_zone INTEGER DEFAULT 1,
            status TEXT DEFAULT 'recommended',
            naive_dist_km REAL DEFAULT 0.0,
            opt_dist_km REAL DEFAULT 0.0,
            saved_pct REAL DEFAULT 0.0,
            stop_order_json TEXT,
            explanation TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            applied_at TIMESTAMP,
            FOREIGN KEY (van_id) REFERENCES vans(id)
        )
    ''')

    # 9. Audit Logs table (Status Transition History)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pickup_id INTEGER NOT NULL,
            previous_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_type TEXT DEFAULT 'operator',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pickup_id) REFERENCES pickups(id) ON DELETE CASCADE
        )
    ''')

    # 10. SMS / Notification Simulation table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sms_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_phone TEXT NOT NULL,
            message TEXT NOT NULL,
            event_type TEXT NOT NULL,
            pickup_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 11. Users table (NagarLoop 4-Role Authentication)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT,
            locality TEXT,
            household_id INTEGER,
            society_id INTEGER,
            van_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (household_id) REFERENCES households(id),
            FOREIGN KEY (society_id) REFERENCES societies(id),
            FOREIGN KEY (van_id) REFERENCES vans(id)
        )
    ''')

    # 13. Email OTPs table (Secure Hashed OTP Storage & Verification)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            attempts INTEGER DEFAULT 0,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 12. Driver Shifts table (Phase 3 Shift Operations & Summaries)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS driver_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER,
            van_id INTEGER NOT NULL,
            shift_date TEXT NOT NULL,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            status TEXT DEFAULT 'not_started', -- 'not_started', 'active', 'completed'
            total_stops INTEGER DEFAULT 0,
            collected_count INTEGER DEFAULT 0,
            reported_count INTEGER DEFAULT 0,
            problem_count INTEGER DEFAULT 0,
            delivered_count INTEGER DEFAULT 0,
            waste_kg REAL DEFAULT 0.0,
            route_dist_km REAL DEFAULT 0.0,
            saved_pct REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (van_id) REFERENCES vans(id)
        )
    ''')

    # Schema Migrations (safe column additions if table existed before)
    migrations = [
        ("pickups", "pickup_code", "TEXT"),
        ("pickups", "is_public", "INTEGER DEFAULT 0"),
        ("pickups", "is_society", "INTEGER DEFAULT 0"),
        ("pickups", "society_id", "INTEGER"),
        ("pickups", "reporter_name", "TEXT"),
        ("pickups", "reporter_phone", "TEXT"),
        ("pickups", "public_description", "TEXT"),
        ("pickups", "problem_reason", "TEXT"),
        ("pickups", "problem_notes", "TEXT"),
        ("pickups", "rescheduled_date", "TEXT"),
        ("pickups", "rescheduled_window", "TEXT"),
        ("pickups", "total_kg", "REAL DEFAULT 0.0"),
        ("pickups", "earned_points", "INTEGER DEFAULT 0"),
        ("facilities", "capacity_kg", "REAL DEFAULT 1000.0"),
        ("facilities", "current_load_kg", "REAL DEFAULT 0.0"),
        ("vans", "current_payload_kg", "REAL DEFAULT 0.0"),
        ("households", "is_society", "INTEGER DEFAULT 0"),
        ("households", "society_id", "INTEGER"),
        ("users", "phone", "TEXT"),
        ("users", "email", "TEXT"),
        ("users", "is_verified", "INTEGER DEFAULT 0"),
        ("users", "locality", "TEXT"),
        ("users", "society_id", "INTEGER"),
        ("points_ledger", "society_id", "INTEGER"),
        ("pickups", "address", "TEXT"),
        ("pickups", "ai_image_check", "TEXT DEFAULT 'passed'"),
        ("pickups", "ai_confidence", "REAL DEFAULT 0.0"),
    ]

    for table, col, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except Exception:
            pass



    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pickups_status ON pickups(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pickups_code ON pickups(pickup_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pickups_zone ON pickups(pickup_zone)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pickup_streams_pickup ON pickup_streams(pickup_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pickup_streams_stream ON pickup_streams(stream_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_points_ledger_hh ON points_ledger(household_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_points_ledger_soc ON points_ledger(society_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_routes_status ON routes(status)')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
