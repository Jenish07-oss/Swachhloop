import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'swachhloop.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Vans table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            van_code TEXT UNIQUE NOT NULL,
            driver_name TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            status TEXT DEFAULT 'idle',
            capacity_kg REAL DEFAULT 500.0
        )
    ''')

    # 3. Facilities table (Circular Economy Destinations)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            facility_type TEXT NOT NULL,
            stream_type TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            registration_note TEXT,
            capacity_kg REAL DEFAULT 10000.0
        )
    ''')

    # 4. Pickups table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pickups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            household_id INTEGER NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            bin_score INTEGER DEFAULT 75,
            photo_path TEXT,
            status TEXT DEFAULT 'pending',
            assigned_van_id INTEGER,
            pickup_zone INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (household_id) REFERENCES households(id),
            FOREIGN KEY (assigned_van_id) REFERENCES vans(id)
        )
    ''')

    # 5. Pickup Streams table (1 Pickup -> Multiple Segregated Streams)
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

    # 6. Points Ledger table (Green Points tracking)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS points_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            household_id INTEGER NOT NULL,
            pickup_id INTEGER,
            points INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (household_id) REFERENCES households(id),
            FOREIGN KEY (pickup_id) REFERENCES pickups(id) ON DELETE SET NULL
        )
    ''')

    # 7. Routes table (Persistent Automatic & Approved Route Batches)
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

    # 8. Audit Logs table (Status Transition History & Recovery Trail)
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

    try:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN actor_type TEXT DEFAULT 'operator'")
    except Exception:
        pass

    # Create helpful indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pickups_status ON pickups(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pickups_zone ON pickups(pickup_zone)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pickup_streams_pickup ON pickup_streams(pickup_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pickup_streams_stream ON pickup_streams(stream_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_points_ledger_hh ON points_ledger(household_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_routes_status ON routes(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_routes_van ON routes(van_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_pickup ON audit_logs(pickup_id)')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("SwachhLoop 4R Database schema initialized successfully.")
