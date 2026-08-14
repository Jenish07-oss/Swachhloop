# SwachhLoop 🌍♻️ — Smart Waste Management Platform

**SIH 2026 | Problem Statement 8-L** | *Smart Waste Management and Citizen Reporting Platform*

> **Citizens Report. City Acts. Everyone Sees It Resolved.**

## 🎯 Overview

SwachhLoop is a closed-loop smart waste management platform that enables citizens to report waste issues via photo + GPS, allows municipal admins to dispatch vehicles and optimize routes using KMeans hotspot prediction and nearest-neighbor route optimization. Citizens earn Green Points for verified reports and see a transparent status timeline with before/after photo proof.

## ✨ Features

### 🧑 Citizen Portal
- 📸 **Report Waste**: Photo upload, GPS auto-detect (or manual map pin), waste category dropdown
- 🗺️ **My Reports Dashboard**: Real-time status timeline (Reported → Assigned → In Progress → Resolved)
- 🌿 **Green Points**: Gamification — +10 points per verified report
- ✅ **Before/After Proof**: Mandatory resolution photo for transparency

### 🛡️ Admin Command Center
- 🎯 **Live Map**: Real-time colored pins (red/amber/blue/green) by status
- 🚛 **Vehicle Tracking**: 3 simulated trucks moving on map every 5 sec
- 🔥 **Hotspot Prediction**: KMeans (k=5) clustering to predict waste generation zones
- 🛣️ **Route Optimization**: Nearest-neighbor algorithm with "distance saved %" KPI
- 📊 **Analytics**: Chart.js dashboards (waste type, status distribution)
- 📝 **Complaint Queue**: Drag-and-click status updates with resolution photo proof

### 🧠 Tech Stack
| Layer | Technology |
|-------|-----------|
| Frontend | HTML5, CSS3, Bootstrap 5, JavaScript |
| Maps | Leaflet 1.9 + Leaflet.heat + OpenStreetMap (free) |
| Charts | Chart.js 4.4 |
| Backend | Python 3.11 + Flask 3.0 |
| Database | SQLite 3 |
| ML | scikit-learn KMeans clustering |
| Deploy | Render Free Tier (Gunicorn) |

## 📦 Installation & Setup

### Prerequisites
- Python 3.10+
- Git

### Windows (PowerShell / Git Bash)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/swachhloop.git
cd swachhloop

# 2. Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1   # PowerShell
# OR
source venv/Scripts/activate    # Git Bash

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize & seed database
python seed_data.py

# 5. Run the app
python app.py

# 6. Open in browser
# Citizen:  http://localhost:5000
# Admin:    http://localhost:5000/admin
# API:      http://localhost:5000/api/reports
```

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 seed_data.py
python3 app.py
```

## 🗂️ Project Structure

```
swachhloop/
├── app.py                 # Flask app + routes + auto-simulation
├── database.py            # SQLite schema & helpers
├── seed_data.py           # 50 demo reports + 3 vehicles
├── simulate_trucks.py     # Truck movement simulation
├── requirements.txt
├── .gitignore
├── README.md
├── templates/
│   ├── base.html
│   ├── citizen_report.html
│   ├── citizen_my_reports.html
│   ├── admin_dashboard.html
│   └── admin_route.html
├── static/
│   ├── css/style.css
│   ├── js/
│   └── uploads/           # User-uploaded photos
└── swachhloop.db          # SQLite DB (created on first run)
```

## 🚀 API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Citizen report form (home) |
| POST | `/report` | Submit new waste report |
| GET | `/my-reports` | View citizen's reports timeline |
| GET | `/admin` | Admin command center dashboard |
| GET | `/admin/route/<vehicle_id>` | Route optimization page |
| GET | `/api/reports` | JSON list of all reports |
| GET | `/api/vehicles` | JSON list of all vehicles |
| POST | `/api/assign` | Assign vehicle to report |
| POST | `/api/status/<id>` | Update report status |
| GET | `/api/hotspots` | KMeans hotspot centroids |
| GET | `/api/charts` | Aggregated chart data |

## 🧮 Algorithms

### Hotspot Prediction (KMeans)
```python
from sklearn.cluster import KMeans
kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
clusters = kmeans.fit_predict([[lat, lon], ...])
```

### Route Optimization (Nearest-Neighbor)
```python
def nearest_neighbor_route(stops):
    # Greedy O(n²) — explainable, no OR-Tools dependency
    current = 0
    route = [0]
    while unvisited:
        nearest = min(unvisited, key=lambda i: haversine(stops[current], stops[i]))
        route.append(nearest)
        current = nearest
    return route
```

Distance saved % is calculated against the naive DB order.

## 🌐 Deployment (Render Free Tier)

1. Push this repo to GitHub (public)
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect GitHub repo
4. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
5. Live URL auto-generated: `https://swachhloop.onrender.com`

⚠️ **Note:** Render free tier SQLite DB is **ephemeral** (resets on restart). For persistent data, upgrade to Postgres or use [Render Persistent Disk](https://render.com/docs/disks).

## 🧪 Test Checklist

- [x] Citizen submits report → appears in `/my-reports` with photo
- [x] Green Points increment (+10)
- [x] Admin assigns vehicle → status changes to "Assigned"
- [x] Truck moves on admin map (every 5 sec)
- [x] Status updates to "In Progress" when within 50m of report
- [x] Route optimization page shows distance saved %
- [x] Hotspot API returns 5 KMeans centroids
- [x] Chart endpoints return waste-type & status data

## 🎨 SDG Alignment

- **SDG 11**: Sustainable Cities & Communities — Target 11.6 (reduce adverse environmental impact)
- **SDG 12**: Responsible Consumption — Target 12.5 (reduce waste generation)

## 📚 References

1. [SmartWasteAI (SIH 2025 Top-30)](https://github.com/allknowledge34/SmartWasteManagementApp-SIH2025)
2. [Kaggle: SIH 2024 Winning Teams Dataset](https://www.kaggle.com/datasets/adharshinikumar/sih-2024-ps-with-winning-teams-and-solutions)
3. [Leaflet JS](https://leafletjs.com)
4. [Leaflet.heat plugin](https://github.com/Leaflet/Leaflet.heat)
5. [SDG 11 Targets](https://sdgs.un.org/goals/goal11)
6. [SDG 12 Targets](https://sdgs.un.org/goals/goal12)
7. [Render Flask Deployment Guide](https://render.com/docs/deploy-flask)

---

**Made with 🌱 by team SwachhLoop for SIH 2026 @ LDRP-ITR**
