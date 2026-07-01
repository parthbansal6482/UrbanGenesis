# FarmGuard — Next.js 16 Analytics Dashboard

This is the interactive frontend dashboard client for the FarmGuard Farmland Encroachment & Risk Analytics platform. It connects to the FastAPI backend service to visualize regional crop buffers, monitor historical land cover transitions, and execute dynamic arbitrary-region analyses.

---

## 🌟 Key UI Features

- **Multi-Mode Location Inputs**:
  - **Named Zones**: Select from curated registered regions (e.g. Nashik North, Bengaluru).
  - **Draw BBox**: Select custom regions by dragging a rectangle directly onto the map.
  - **Coordinates Entry**: Manually input numerical lat/lon values with live area calculations.
- **Symmetric Slider Comparison**:
  - Split-screen comparison slider separating historical crop masks or true-color imagery.
  - **Synchronized Panning & Zooming**: Drag to pan and use the mouse wheel (or float controls HUD) to zoom in/out on both overlays in unison without stretching or distortion.
- **Custom Region Management**:
  - **Refresh**: Force the backend satellite pipeline to purge cache and regenerate visual layers.
  - **Delete**: Safely delete the cache directory on disk and remove the bounding box from your local selector list.
- **Durability & Persistence**:
  - Custom bounding boxes are persisted locally using `localStorage` to survive browser refreshes.
- **Simulation Mode Alerting**:
  - Automatically renders prominent warning status indicators (`⚠️ SIMULATED DATA ACTIVE`) when offline cache fallbacks or mock data is in use.

---

## 🛠️ Technology Stack

- **Framework**: Next.js 16 (App Router)
- **Map Renderers**: React Leaflet (OSM / CARTO Light tiles basemaps)
- **3D Visualization**: WebGL (Three.js) for globe and map projection slates
- **Typography**: Geist Mono & Geist Sans
- **Styling**: Premium, utility-first off-white design system (Vanilla CSS variables)

---

## 🚀 Getting Started

### 1. Configure Settings
Create or copy the environment variables inside the `dashboard/.env.local` or root `.env` file:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Start Dev Client
Run the development client:
```bash
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the dashboard.

### 3. Verify Codebase Quality
Run typescript type checking and ESLint:
```bash
# Typecheck
npx tsc --noEmit

# Lint check
npm run lint
```
