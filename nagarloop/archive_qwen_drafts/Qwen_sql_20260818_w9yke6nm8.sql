CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
  name TEXT NOT NULL, role TEXT NOT NULL,           -- citizen/driver/admin
  household_id INTEGER, van_id INTEGER);