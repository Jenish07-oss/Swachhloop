# PRD — NagarLoop (formerly SwachhLoop 4R)
> Source of truth for product decisions. Read AGENTS.md for working rules.

## 1. Vision
Society-first, 4-stream segregated waste collection for Indian cities.
One pickup → four streams → real destinations → rewards back to society.
Tagline: "Your society's waste, back in the loop."

## 2. Hard Principles (never violate)
- 100% software, ZERO hardware/IoT.
- Free & open-source stack only (Flask, SQLite, Leaflet/OSM, Chart.js, Bootstrap/vanilla CSS).
- NEVER mix streams at collection; mixing only at END (residual → RDF).
- Chain-of-custody visible: Booked → Collected → (citizen verify/dispute) → Delivered.
- All weights/CO2 shown as **estimates** with "estimated" tag; formulas NEVER shown in UI.
- Website = REAL PRODUCT look. NO SIH / hackathon / PS-ID / SDG badge text anywhere in UI.
- Elderly-friendly: base font ≥17px, buttons ≥48px, one primary action per screen, plain words.
- i18n: English + Gujarati only (brand.T). Every new UI string added in BOTH languages.

## 3. Roles
| Role | Core jobs |
|---|---|
| Citizen (society manager / individual home / public reporter) | Book society/home pickup, report road/event waste, track status, see points & impact |
| Driver | Shift card, start route, next-stop actions (Navigate / Collected / Report Issue), end shift |
| Admin | See all reports, auto best route, assign vans, disputes, facility board, leaderboards |

## 4. The 4 Streams & Destinations
wet → compost/bio-CNG • dry → MRF • ewaste → CPCB-registered recycler • residual → RDF/cement kiln.

## 5. Features by Phase (acceptance criteria)
### P1 (done — integrate & test)
Rebrand NagarLoop • compact Home + loop animation • EN/ગુ toggle • Privacy/Reward/Help pages • 3 separate logins (session-based).
### P2 (current)
- societies table + society booking: streams + est. kg + photo + saved collection point (auto-set if same place) + daily-pile recurring note.
- Proportional Green Points: `points = round(Σ(kg×rate)×mult)`; rates/kg: wet 2, dry 6, ewaste 20, residual 1; mult by bin score ≥80:1.5 / 60–79:1.2 / 40–59:1.0 / <40:0.5.
- Threshold: society booking <5 kg total → 0 points (still collected).
- Tax credit policy line: 1 pt = ₹1 society property-tax offset, "subject to municipal policy".
- Public road/event report: 15 pts after admin verify (+5 medium / +10 large).
- Individual home booking kept.
- AC example: 12 kg wet + 4 kg dry, score 84 → round((24+24)×1.5) = 72 pts.
### P3
- SMS simulation (sms_log table): day-before schedule msg • ~15-min-before arrival msg • cancellation msg. UI toast + log; NO paid gateway.
- Driver portal (mobile-first, giant buttons) + end-shift summary.
- Admin: society view, disputes (existing), auto best route (existing TSP).
### P4
- Leaderboards: weekly + monthly tabs; society rank + individual rank.
- Impact equivalents: CO2e kg + "≈ km of car driving" (CO2e ÷ 0.17).
- Motion polish (fade-up, count-up, pulsing vans) + prefers-reduced-motion off-switch.
- Tests updated; README updated.

## 6. CO2e factors (kg CO2e/kg — backend only)
wet 0.85 • dry 1.95 • ewaste 3.20 • residual 0.60.

## 7. Data Model Additions (P2/P3)
societies(id,name,area,point_lat,point_lng,point_address,manager_user_id)
users(+role,+society_id) • pickups(+society_id,+reporter_type: society|home|public)
sms_log(id,pickup_id,phone,message,kind:schedule|eta|cancel,sent_at)