import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'swachhloop.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'citizen',
            phone TEXT UNIQUE,
            green_points INTEGER DEFAULT 0
        )
    ''')
    
    # Waste reports table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waste_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            waste_type TEXT NOT NULL,
            description TEXT,
            image_url TEXT,
            status TEXT DEFAULT 'Reported',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_image_url TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Vehicles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL UNIQUE,
            driver TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            status TEXT DEFAULT 'Idle',
            phone TEXT
        )
    ''')
    
    # Assignments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL,
            status TEXT DEFAULT 'Assigned',
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_id) REFERENCES waste_reports(id),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
