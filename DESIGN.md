# Design System: FarmGuard — Satyukt Satellite Surveillance Dashboard

## 1. Visual Theme & Atmosphere

A precision instrument dashboard — dense, clinical, and quietly confident. Warm off-white surfaces, dark stone text, and a single emerald accent signaling healthy agricultural zones. Density **7/10** — every pixel carries data. Motion **4/10** — only status pulses and spring-physics reveals. Variance **6/10** — left-heavy split layout.

Core rule: **data speaks, UI stays out of the way**.

---

## 2. Color Palette & Roles

### Background Hierarchy
- **Warm Floor** (`#f5f5f4`) — Stone-100. Page base.
- **Panel Surface** (`#fafaf9`) — Stone-50. Sidebar, right panel.
- **Card Face** (`#ffffff`) — Pure white. Glass-cards, metric-cards.
- **Card Hover** (`#f4f4f5`) — Zinc-100. Interactive card hover.
- **Glass Overlay** (`rgba(250,250,249,0.88)`) — Frosted overlays, header, floating pills.

### Text Hierarchy
- **Ink** (`#1c1917`) — Stone-900. Primary text. Never `#000000`.
- **Slate** (`#57534e`) — Stone-600. Secondary text, descriptions.
- **Mist** (`#78716c`) — Stone-500. Muted metadata, axis labels.
- **Ghost** (`#a8a29e`) — Stone-400. Placeholders, disabled.

### Borders
- **Whisper** (`rgba(28,25,23,0.09)`) — Default borders. Warm, not cool.
- **Defined** (`rgba(28,25,23,0.18)`) — Hover/focus borders.
- **Active** (`#047857`) — Selected zones, focus rings.

### Accent — Emerald (Single Accent Only)
- **Emerald Active** (`#047857`) — Active tab fills, focus rings. HIGH contrast on white.
- **Emerald Standard** (`#059669`) — CTAs, positive data lines, zone outlines.
- **Emerald Bright** (`#10b981`) — "Healthy" grade badges, chart lines.
- **Emerald Dim** (`rgba(5,150,105,0.08)`) — Tinted card backgrounds.

### Semantic Status Colors
- **Alert Red** (`#dc2626`) — Critical alerts, grade F/D.
- **Warning Amber** (`#d97706`) — Grade C, warnings.
- **Data Sky** (`#0284c7`) — Built-up area chart data series.

### BANNED Colors
- `rgba(5,12,20,...)` — Dark navy. **Completely banned.**
- `rgba(51,90,130,...)` — Muted blue-grey. **Completely banned.**
- `#34d399` — Neon emerald. Too bright for light theme. Use `#059669`.
- `#050c14`, `#0d1826` — Dark backgrounds. **Banned.**
- Neon glow box-shadows. **Banned.**

---

## 3. Typography Rules

- **Data Numbers:** `Geist Mono` — metrics, grades, coordinates, timestamps.
- **UI Labels:** `Geist Sans` — section labels, tab buttons.
- **Scale:** Labels `9px/0.12em`. Body `11–13px`. Metrics `18–28px` Geist Mono.
- **BANNED:** `Inter` for premium contexts. Serifs always banned in dashboards.

---

## 4. Component Stylings

- **Tab Buttons:** Active: `#047857` fill, white text. Inactive: Stone-500. Hover: Stone-900 5% alpha.
- **Glass Cards:** `#ffffff` fill, `rgba(28,25,23,0.09)` border, `border-radius: 12px`.
- **Grade Badges:** 40×40px square, monospace bold, colored border and tinted background.
- **Inputs/Selects:** White background, whisper border, emerald focus ring.
- **Loading:** Skeletal shimmer `#f4f4f5`. Radar animation for satellite load screen.

---

## 5. Anti-Patterns (Banned)

- `rgba(5,12,20,...)` dark navy — **Zero tolerance.**
- `rgba(51,90,130,...)` blue-grey — **Zero tolerance.**
- `#34d399` neon emerald on light backgrounds — use `#059669`.
- Neon glow box-shadows.
- Pure `#000000` — use `#1c1917`.
- Overlapping elements without clear spatial separation.
- Fabricated metrics/statistics as placeholders.
