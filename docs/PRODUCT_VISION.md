# OliveIntel Product Vision

**Last Updated:** 2026-07-08  
**Status:** Milestone 1 in progress

---

## Core Vision

**OliveIntel is a satellite-based olive health and yield intelligence platform for the Aegean region.**

The product provides farmers, cooperatives, and agricultural businesses with:
- **Visual health monitoring** via an illustrated line-art map
- **Density analysis** showing olive tree concentration by region
- **Quality scoring** based on vegetation metrics
- **Yield forecasting** accounting for alternate bearing cycles
- **Historical trends and future projections** (2019-2030)

---

## Key Differentiator

**Line Art Map with Data Overlay** - Unlike generic satellite monitoring tools with standard map tiles, OliveIntel uses a **hand-drawn illustration style** showing Turkey and Greek islands with data visualizations overlaid as circles and heatmaps.

Think: *National Geographic meets The Economist data viz*

---

## User Experience

### Primary View: Illustrated Health Map

```
┌─────────────────────────────────────────────────────┐
│  [OliveIntel Logo]        2026  [Timeline Slider]   │
├─────────────────────────────────────────────────────┤
│                                                     │
│   ╭──────────────────────────────────────────╮     │
│   │         İstanbul ●                       │     │
│   │                                          │     │
│   │            ╱──────╲                      │     │
│   │  ╱────────╱  Sea   ╲                     │     │
│   │ │        │   of     │                    │     │
│   │ │ İzmir ⬤│ Marmara  │                    │     │
│   │ │ [LARGE]╲─────────╱                     │     │
│   │ │                                        │     │
│   │ │ Aydın ◉           Aegean Sea          │     │
│   │ │ [MED]              ~~~~~              │     │
│   │ │                                       │     │
│   │ │ Muğla ○                               │     │
│   │  ╲─────────                              │     │
│   │           Mediterranean Sea              │     │
│   ╰──────────────────────────────────────────╯     │
│                                                     │
│   ⬤ Excellent   ◉ Good   ○ Fair   • Poor          │
│   Circle size = Olive tree density                 │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Metrics Panel:                                     │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────┐│
│  │ Quality      │ │ Est. Yield   │ │ Total Area  ││
│  │ Score        │ │              │ │             ││
│  │   87/100     │ │  420K tonnes │ │  3.2M ha    ││
│  │ Excellent ✓  │ │  Medium conf │ │  Aegean     ││
│  └──────────────┘ └──────────────┘ └─────────────┘│
└─────────────────────────────────────────────────────┘
```

### Timeline Toggle

**Visual Design:**
```
Historical (solid)  │  Projected (dashed)
2019 ─ 2020 ─ 2021 ─ 2022 ─ 2023 ─ 2024 ┄ 2025 ┄ 2026 ┄ 2027 ┄ 2028
                                   ▲
                              [You are here]
```

**Behavior:**
- Default: Loads at **current year (2026)**
- Drag slider or click year to time-travel
- Historical years (2019-2024): Show actual satellite data
- Future years (2025-2030): Show ML forecasts with confidence bands
- Smooth animated transitions when changing years

### Data Visualization

**1. Circle Overlay**
- **Size:** Proportional to olive tree count (or grove area)
- **Color:** Health status based on current NDVI
  - 🟢 Excellent: NDVI > 0.65 (dark green)
  - 🟢 Good: NDVI 0.55-0.65 (light green)
  - 🟡 Fair: NDVI 0.45-0.55 (yellow)
  - 🟠 Poor: NDVI 0.35-0.45 (orange)
  - 🔴 Critical: NDVI < 0.35 (red)
- **Interaction:** Click circle → opens province detail panel

**2. Heatmap (Optional Enhancement)**
- When zoomed in to province level
- Shows sub-regional density gradients
- Smooth color interpolation

### Metrics Panel (Below or Beside Map)

**Quality Score (0-100)**
- Computed from: peak NDVI, season length, inter-annual stability
- Badge: Excellent (>85), Good (70-85), Fair (50-70), Poor (<50)

**Estimated Yield**
- Tonnes for current/selected year
- Confidence level: High/Medium/Low
- Compare to previous year (± % change)

**Total Olive Grove Area**
- Hectares across region
- Breakdown by province (expandable)

**Historical Trend Chart**
- Mini line chart showing 5-year NDVI trend
- Indicates if current year is on/off cycle

---

## Design Aesthetic

### Visual Style
- **Line art borders** - Hand-drawn, single-stroke outlines (not realistic satellite view)
- **Muted earth tones** - Cream background (#f5f5f0), dark gray borders (#2c3e50)
- **Data-first** - Map is backdrop for data, not photorealistic imagery
- **Clean typography** - Sans-serif, clear hierarchy

### Color Palette

```css
/* Base */
--bg: #f5f5f0;           /* Cream paper */
--border: #2c3e50;       /* Dark gray-blue lines */

/* Health gradient */
--excellent: #1a9850;    /* Deep green */
--good: #91cf60;         /* Light green */
--fair: #fee08b;         /* Pale yellow */
--poor: #f46d43;         /* Orange */
--critical: #d73027;     /* Red */

/* Accent */
--accent: #3498db;       /* Blue for interactive elements */
--text: #2c3e50;         /* Dark text */
--text-muted: #7f8c8d;  /* Gray text */
```

### Inspiration References
- **The Economist** data visualizations (clean, authoritative)
- **National Geographic** line maps (illustrated borders)
- **Apple Weather** (minimalist data hierarchy)
- **Windy.com** (timeline controls)

---

## Technical Architecture

### Frontend (Next.js 14 + Vercel)

**Map Implementation:**
```tsx
// Option A: SVG (more control over illustration style)
<svg viewBox="0 0 1200 800">
  <TurkeyBorders />  {/* Hand-drawn paths */}
  <GreekIslands />   {/* Simplified outlines */}
  <ProvinceCircles data={healthData} year={selectedYear} />
</svg>

// Option B: Mapbox GL JS (interactive zoom)
<Map
  mapStyle={customLineArtStyle}  // Custom Mapbox Studio style
  interactive={true}
>
  <CircleLayer data={healthData} />
  <HeatmapLayer data={densityData} />
</Map>
```

**State Management:**
```tsx
const [selectedYear, setSelectedYear] = useState(2026);  // Default: current year
const [healthData, setHealthData] = useState([]);
const [densityData, setDensityData] = useState([]);

useEffect(() => {
  if (selectedYear <= 2024) {
    // Fetch historical data
    fetch(`/api/map/health?year=${selectedYear}`).then(...);
  } else {
    // Fetch forecast
    fetch(`/api/forecast/ndvi?year=${selectedYear}`).then(...);
  }
}, [selectedYear]);
```

### Backend (Neon PostgreSQL + Python Processing)

**Data Flow:**
```
Google Earth Engine (Sentinel-2)
         ↓
Python Pipeline (weekly cron)
  • Cloud masking
  • NDVI/NDRE/EVI computation
  • Time series extraction
  • Olive density estimation (tree count or area)
  • Quality score computation
         ↓
Neon PostgreSQL
  • timeseries (historical 2019-2024)
  • forecasts_ndvi (projected 2025-2030)
  • provinces (boundaries + density + quality)
  • phenology (seasonal metrics)
         ↓
Next.js API Routes (Vercel Edge)
  • GET /api/map/health?year={year}
  • GET /api/map/density
  • GET /api/metrics/quality
  • GET /api/forecast?year={year}
         ↓
Frontend (React)
```

---

## Features by Milestone

### Milestone 1: Health Monitoring (Week 1) ✅
- [x] Historical NDVI data (2019-2024)
- [x] Province boundaries (5 Aegean provinces)
- [x] Database schema (PostgreSQL + PostGIS)
- [x] Streamlit prototype (local testing)
- [ ] Complete data extraction for all 5 provinces
- [ ] Compute baseline (5-year average)
- [ ] Health status algorithm (z-score)

### Milestone 2: Density & Quality (Week 2-3)
- [ ] Olive grove area calculation per province
- [ ] **Tree count estimation** (if feasible)
  - Method: Count high-NDVI clusters in 10m imagery
  - Validation: Compare to known orchard densities
  - Fallback: Use grove area if tree count unreliable
- [ ] Quality score model (0-100 based on phenology)
- [ ] Yield forecasting (LightGBM with on/off-year flag)
- [ ] Ground truth labels (TÜİK production data)
- [ ] Weather covariates (ERA5-Land)

### Milestone 3: Line Art Map (Week 4)
- [ ] Next.js frontend setup (Vercel)
- [ ] Line art map design (SVG or Mapbox custom style)
- [ ] Circle overlay (size=density, color=health)
- [ ] Metrics panel (quality, yield, area)
- [ ] Timeline control (2019-2024 historical only)
- [ ] API routes for data fetching
- [ ] Deploy to Vercel

### Milestone 4: Future Projections (Week 5-6)
- [ ] NDVI forecasting model (2025-2030)
  - Train on historical patterns + weather
  - Output: predicted NDVI with confidence intervals
- [ ] Extend timeline to 2030
- [ ] Visual distinction (solid line = past, dashed = future)
- [ ] Confidence bands on future years
- [ ] Animation between years

### Future Enhancements (Post-MVP)
- [ ] Greek islands expansion (Lesbos, Chios, Samos, Rhodes, Crete)
- [ ] Olive oil price tracking (scrape or API)
- [ ] Sub-province detail (district/village level)
- [ ] Individual farm monitoring (10m resolution)
- [ ] Mobile app (iOS/Android)
- [ ] Email alerts (anomaly detection)
- [ ] Export reports (PDF/CSV)

---

## User Answers (Design Decisions)

1. **Map style:** Design frontend when backend done (SVG vs Mapbox decision deferred)
2. **Density metric:** 
   - **Primary:** Tree count estimation (attempt first)
   - **Fallback:** Olive grove area (hectares)
3. **Oil price:** Skip for MVP, add later
4. **Greek islands:** Defer to post-MVP
5. **Timeline default:** Current year (2026)

---

## Key Metrics (KPIs)

### Technical
- **Data freshness:** Weekly updates (Sentinel-2 revisit time)
- **Spatial resolution:** 10m (tree-level) to 100m (province aggregation)
- **Temporal coverage:** 2019-2024 (historical), 2025-2030 (forecast)
- **Model accuracy:** RMSE < 15% on yield predictions

### User Experience
- **Page load:** <2 seconds (Vercel Edge caching)
- **Map interaction:** 60 FPS smooth animations
- **Data latency:** <7 days from satellite acquisition

### Business
- **Target users:** Farmers, cooperatives, agricultural consultants
- **Market:** Aegean region (5-10M olive trees)
- **Pricing:** Free MVP → Freemium (later)

---

## Honest Limitations

### What OliveIntel CAN Do:
- ✅ Province-level health monitoring
- ✅ Detect vegetation stress 2-4 weeks early
- ✅ Forecast yield 2-3 months before harvest
- ✅ Show multi-year trends (is orchard declining?)
- ✅ Estimate olive density by region

### What OliveIntel CANNOT Do:
- ❌ Individual tree health (need <1m resolution, drone data)
- ❌ Disease identification (e.g., Xylella) - requires hyperspectral imagery
- ❌ Real-time alerts (<5 days) - Sentinel-2 revisit + cloud delay
- ❌ Prescriptive irrigation schedules - need soil sensors
- ❌ Fix alternate bearing - it's tree biology, not monitoring

### Confidence & Uncertainty
- **Historical data (2019-2024):** High confidence (direct satellite observations)
- **Current year (2025-2026):** Medium-high (recent data, <1 month lag)
- **Near-term forecast (2027-2028):** Medium (1-2 year ML predictions)
- **Long-term forecast (2029-2030):** Low-medium (3-4 year extrapolation)

**UI Principle:** Always show confidence level. If uncertain, say "Check back in 2 weeks" rather than showing a low-confidence number.

---

## Roadmap Summary

```
2026 Q3 (Now)        Q4              2027 Q1           Q2
│                   │               │                 │
├─ M1: Health      ├─ M3: Map      ├─ M5: Mobile    ├─ M7: Farms
│   Monitoring     │   Frontend    │   App          │   (10m detail)
│                  │               │                │
├─ M2: Yield       ├─ M4: Future   ├─ M6: Greek     ├─ M8: API
│   Forecast       │   Timeline    │   Islands      │   (B2B)
│                  │               │                │
                   MVP Launch      Public Beta      Commercial
```

---

## Open Questions

1. **Tree count estimation feasibility:**
   - Can we reliably count trees from 10m Sentinel-2? (Test in Milestone 2)
   - What's the error margin vs ground truth?
   - Is grove area (ha) sufficient for MVP?

2. **Map rendering performance:**
   - SVG: Scales well for fixed zoom, harder for pan/zoom
   - Mapbox: Better interaction, but needs custom style design
   - Benchmark both with 50+ provinces loaded

3. **Forecast horizon:**
   - How far can we predict with confidence? (2 years? 5 years?)
   - Should we cap timeline at 2028 instead of 2030?

4. **Data update cadence:**
   - Weekly batch processing (low infra cost, 5-7 day lag)
   - Daily updates (higher cost, 1-2 day lag)
   - Start weekly, upgrade later if users demand it

---

## Success Criteria

**Milestone 1 (This Week):**
- [ ] All 5 provinces have complete time series (2019-2024)
- [ ] Health status computes correctly (z-score vs baseline)
- [ ] Streamlit prototype works end-to-end
- [ ] Data loaded into PostgreSQL

**Milestone 2 (Next 2 Weeks):**
- [ ] Quality scores computed for all provinces
- [ ] Yield model trained (RMSE < 20% on test set)
- [ ] Density metrics (tree count or area) calculated
- [ ] Forecasts generated for 2025-2026

**Milestone 3 (Week 4 - MVP Launch):**
- [ ] Line art map renders beautifully
- [ ] Timeline toggle works (2019-2024)
- [ ] All 5 provinces show correct data
- [ ] Page loads <2 seconds
- [ ] Mobile responsive
- [ ] Deployed to oliveintel.app (custom domain)

**Milestone 4 (Week 5-6):**
- [ ] Future projections (2025-2030) visible
- [ ] Confidence intervals shown
- [ ] Animation smooth
- [ ] User testing with 5+ stakeholders
- [ ] No critical bugs

---

**Version:** 1.0  
**Next Review:** After Milestone 1 completion
