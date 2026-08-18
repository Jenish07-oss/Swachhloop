# NagarLoop — Municipal Circular Waste Platform

**NagarLoop** is a production-ready civic-tech platform for municipal circular waste collection and recovery across housing societies and individual households.

---

## 📁 Directory & File Organization Guide

This folder contains the complete, dedicated, clean **NagarLoop** platform code:

```text
swachhloop/
└── nagarloop/
    │
    ├── 🚀 EXECUTION & SERVER
    │   ├── app.py                      → Main Flask Web Server, API endpoints & routing
    │   ├── brand.py                    → Municipal branding, Gujarati/English translations & points/CO2 calculators
    │   ├── database.py                 → Relational SQLite database manager & table schemas
    │   ├── seed_data.py                → Realistic municipal demo data seeder (40 households, 4 streams, vans, facilities)
    │   ├── requirements.txt            → Python package dependencies
    │   ├── start_nagarloop.bat         → One-click launcher to start NagarLoop server & open browser
    │   ├── stop_nagarloop.bat          → One-click script to stop the server cleanly
    │   │
    │   ├── 🧪 AUTOMATED TESTS
    │   ├── test_nagarloop.py           → Complete 40-test automated verification suite
    │   │
    │   ├── 🎨 USER INTERFACE & WEBPAGES
    │   ├── templates/                  → 22 HTML web templates
    │   │   ├── base.html               → Common navigation bar, responsive layout & footers
    │   │   ├── home.html               → Public landing hero & circular "How It Works"
    │   │   ├── citizen_report.html     → 4-stream doorstep collection booking wizard
    │   │   ├── citizen_my_reports.html → Citizen pickup history & tracking
    │   │   ├── citizen_impact.html     → 4R Impact dashboard & CO2e avoided visualizer
    │   │   ├── driver_portal.html      → Driver mobile console with "Next Stop" card & shift lifecycle
    │   │   ├── driver_history.html     → Driver completed stops manifest history
    │   │   ├── admin_dashboard.html    → Municipal Command Center with KPIs, live map, alerts & chart
    │   │   ├── admin_dispatch.html     → Fleet dispatch hub & live van telematics
    │   │   ├── admin_route.html        → Heuristic route optimization & nearest-neighbor ordering
    │   │   ├── admin_societies.html    → Housing societies management directory
    │   │   ├── admin_society_detail.html → Society audit & stream diversion breakdown
    │   │   ├── admin_reports.html      → Official printable municipal operations audit report
    │   │   ├── society_dashboard.html  → Housing society manager portal & collection station bay
    │   │   ├── society_booking.html    → Housing society bulk waste booking
    │   │   ├── public_report.html      → Civic public waste reporting form (photo & map pin)
    │   │   ├── leaderboard.html        → Public community rankings & points board
    │   │   ├── manifest_view.html      → Chain-of-custody digital manifest with QR & 3-step proof
    │   │   ├── login.html              → Role-isolated secure login portal
    │   │   ├── register.html           → Citizen & Society registration forms
    │   │   └── legal.html              → Privacy policy & Green Rewards terms
    │   │
    │   ├── 📦 STATIC ASSETS
    │   ├── static/
    │   │   ├── css/
    │   │   │   ├── nl.css              → NagarLoop design system (colors, cards, buttons, animations)
    │   │   │   └── style.css           → Base utilities & typography
    │   │   ├── js/                     → Frontend scripts
    │   │   └── uploads/                → Stored bin & public waste images
    │   │
    │   └── 🗄️ ARCHIVE
    │       └── archive_qwen_drafts/    → Archived draft snippets (isolated from active code)
```

---

## 🚀 How to Run NagarLoop

### Option A: Double-Click
Double-click `start_nagarloop.bat`.

### Option B: Terminal Command
```powershell
cd nagarloop
..\venv\Scripts\python.exe app.py
```

Open your browser at **`http://127.0.0.1:5000/`**.

---

## 🔑 Login Accounts (Pre-Seeded):

| Role | Username | Password | Purpose |
|---|---|---|---|
| **Citizen** | `jenish` | `jenish123` | Book 4-stream pickups, track status, view Green Points & impact |
| **Society Manager** | `society` | `society123` | Bulk collection bookings, society metrics, collection station bay |
| **Truck Driver** | `vikram` | `vikram123` | Active route, Next Stop card, Shift lifecycle, report collections/issues |
| **Municipal Admin** | `admin` | `admin123` | Command center, route optimization, facility monitoring, reports & CSV export |

---

## 🧪 Running Automated Tests:

```powershell
..\venv\Scripts\python.exe test_nagarloop.py
```
*(40 out of 40 tests passing)*
