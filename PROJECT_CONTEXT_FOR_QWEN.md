# SwachhLoop 4R — Complete Project Blueprint & Architecture for Qwen AI

> **Smart India Hackathon 2026 (SIH 2026) — Circular Economy Problem Statement**
> **Project Directory:** `C:\Users\patel jenish\swachhloop`
> **Repository:** `Jenish07-oss/Swachhloop`

---

## 1. Executive Summary
**SwachhLoop 4R** is an end-to-end municipal circular economy waste management system. It replaces untracked mixed-waste dumping with a verified, segregated chain-of-custody model across **4 Circular Streams**:
1. 🥬 **Wet Waste** $\rightarrow$ Bio-CNG / Organic Composting Plants
2. 📦 **Dry Waste** $\rightarrow$ Material Recovery Facilities (MRF) & Plastic Upcyclers
3. ⚡ **E-Waste** $\rightarrow$ Certified Electronics Recyclers & Urban Mining
4. 🗑️ **Residual Waste** $\rightarrow$ Waste-to-Energy (WtE) Incineration

---

## 2. Technology Stack & Architecture

### Backend & Core Engines
- **Language & Framework:** Python 3, Flask (`app.py`)
- **Database:** SQLite3 (`database.py`, `swachhloop.db`)
- **Machine Learning / Spatial Clustering:** `scikit-learn` (`KMeans`), `numpy`
- **Geospatial & Mathematics:** Great Circle Haversine formula for distance & fuel-saving estimation
- **QR Manifest Engine:** Python `qrcode` library generating base64 SVG/PNG manifests for chain-of-custody verification

### Frontend & UI/UX
- **Templates:** Jinja2 HTML5 (`templates/`)
- **Styling:** Custom Vanilla CSS Design System with responsive grid & dark mode accents (`static/css/style.css`)
- **Interactive Maps:** Leaflet.js with dynamic van telemetry, multi-stop paths, and destination pins
- **Icons & Modals:** FontAwesome 6, Bootstrap 5 UI modals

---

## 3. Machine Learning & Mathematical Algorithms

### 3.1 Spatial Zone Clustering (K-Means)
- Groups all pending pickup coordinates $(\text{latitude}, \text{longitude})$ within an urban ward (Navrangpura, Ahmedabad) into $K$ operational clusters using `sklearn.cluster.KMeans(n_clusters=5)`.
- Eliminates random cross-city van routing and prevents traffic congestion.

### 3.2 Nearest-Neighbor TSP Route Optimization
- Calculates the optimal pickup sequence starting from the depot:
  $$\text{Depot} \xrightarrow{\min d} \text{Stop}_1 \xrightarrow{\min d} \text{Stop}_2 \dots \xrightarrow{\min d} \text{Stop}_n \xrightarrow{} \text{Destination Facility}$$
- Computes both **Naive Distance** (unoptimized sequence) and **Optimized Distance** to deliver:
  $$\text{Distance Saved \%} = \frac{\text{Naive Dist} - \text{Optimized Dist}}{\text{Naive Dist}} \times 100$$

### 3.3 Transparent Green Points Gamification Engine
- Rewards citizens based on AI/Operator Bin Quality Score ($0 - 100$):
  $$\text{Green Points} = 20 + \lfloor \frac{\text{Bin Score}}{10} \rfloor$$
- Populates the **Ward Green Champions Leaderboard** with Podium Rankings (🥇 Gold, 🥈 Silver, 🥉 Bronze).

---

## 4. End-to-End Safe Chain-of-Custody Lifecycle

```text
[ CITIZEN BOOKING ] (PENDING)
         │
         ▼
[ VAN OPERATOR COLLECTS ] ──► (COLLECTION REPORTED)
         │
         ▼
[ CITIZEN VERIFICATION PROMPT (/my-pickups) ]
   ├── Citizen clicks "Yes, Collected" ────► (COLLECTED)
   └── Citizen clicks "No, Not Collected" ──► (DISPUTED)
                                                  │
                                                  ▼
                                      [ MUNICIPAL DISPATCH REVIEW ]
                                         ├── Admin Confirms ──────► (COLLECTED)
                                         └── Admin Returns ───────► (PENDING)
                                                  │
                                                  ▼
[ CIRCULAR FACILITY ARRIVAL ] ────────────► (DELIVERED)
```

Every transition generates an immutable record in the `audit_logs` table (`actor_type: 'citizen' | 'operator' | 'admin'`).

---

## 5. Web Routes & API Directory

| Route / Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/` | `GET` | Citizen Booking Portal & AI Bin Quality Calculator |
| `/report` | `POST` | Book a segregated waste pickup |
| `/my-pickups` | `GET` | Citizen Verification Portal (Yes/No prompt & live status) |
| `/impact` | `GET` | 4R Environmental Impact Dashboard & CO₂ Reduction stats |
| `/manifest/<id>` | `GET` | Digital QR Manifest & Immutable Audit Timeline |
| `/admin` | `GET` | Municipal Command Center & Civic Champions Leaderboard |
| `/admin/dispatch` | `GET` | Operations Dispatch Center with Leaflet GPS map & Next Stop |
| `/admin/route/<van_id>` | `GET` | Interactive Route Optimizer with drag-and-drop stop reordering |
| `/api/status/<id>` | `POST` | Status lifecycle updates (`report_collection`, `reopen_pickup`, `admin_confirm`) |
| `/api/citizen/verify/<id>` | `POST` | Citizen verification (`confirm` / `dispute`) |
| `/api/route/deliver` | `POST` | Bulk facility delivery confirmation |
| `/api/project-summary` | `GET` | Live JSON/Markdown summary for AI / Qwen inspection |
| `/api/reset-demo` | `POST` | Resets SQLite database to 40 seeded pickups across 5 clusters |

---

## 6. How to Run Locally

### Start Website:
Double-click `start_swachhloop.bat` or run:
```bash
.\venv\Scripts\python.exe app.py
```
- Open browser: **http://127.0.0.1:5000/**

### Run Test Suite:
```bash
.\venv\Scripts\python.exe test_swachhloop.py
```
*(All 15 unit/integration tests validate route optimization, dispute workflows, and manifest generation).*
