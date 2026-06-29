# Design

## Overview
A clean, structured modern dark-theme dashboard designed for agriculture analysts and risk underwriters. It highlights native 10m satellite imagery, land cover changes, and encroachment warning alerts.

## Colors
- **Primary Accent**: `#10b981` (Emerald 500) — used for primary action buttons, active states, and stable indicators.
- **Encroachment Alert**: `#ef4444` (Red 500) — used for critical encroachment alerts and warning badges.
- **Warning Accent**: `#f59e0b` (Amber 500) — used for cropland visualization and warning status.
- **Neutral Background**: `#090a0f` — main application background.
- **Neutral Surface**: `#0f1016` — panel elements and base containers.
- **Neutral Card**: `#15171f` — card backgrounds and list elements.
- **Neutral Border**: `rgba(255, 255, 255, 0.07)` — crisp dividers and borders.
- **Text Primary**: `#f1f5f9` (Slate 100) — main headings and body text.
- **Text Secondary**: `#94a3b8` (Slate 400) — supporting text and metrics.
- **Text Muted**: `#64748b` (Slate 500) — captions and helper labels.

## Typography
- **Font Family**: `ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` for both display and body copy to ensure high readability and consistency.
- **Font Sizes**:
  - Title: `1.0625rem` (17px)
  - Subheaders: `0.8125rem` (13px)
  - Body: `0.75rem` (12px)
  - Label: `0.625rem` (10px) / `0.5625rem` (9px)

## Elevation
- **Flat Surface**: `border: 1px solid rgba(255, 255, 255, 0.07)` with zero shadow for general structure. No glowing wide-blur shadows are allowed.

## Components
- **Primary Button**: `#059669` background, `#FFFFFF` text, `border-radius: 8px`, `padding: 10px 20px`, active hover state `#047857`.
- **Panel Card**: `#15171f` background, `border-radius: 12px`, `border: 1px solid rgba(255, 255, 255, 0.07)`, `padding: 20px`.
- **Form Inputs**: Coordinate entry boxes with clear placeholder labels, border color transitions (neutral `rgba(255, 255, 255, 0.07)` to active Emerald `#10b981`), and compact descriptive helper text.
- **Status Badge**:
  - Critical: background `rgba(239, 68, 68, 0.08)`, text `#f87171`, border `rgba(220, 38, 38, 0.3)`.
  - Stable: background `rgba(16, 185, 129, 0.08)`, text `#34d399`, border `rgba(5, 150, 105, 0.3)`.
  - Neutral: background `rgba(255, 255, 255, 0.05)`, text `#94a3b8`, border `rgba(255, 255, 255, 0.07)`.

## Do's and Don'ts
### Do's
- Do use solid colors for buttons and typography.
- Do use subtle micro-animations (e.g. lift-up hover) to indicate interactivity.
- Do keep card corners crisp with `border-radius: 12px`.
- Do ensure text contrast ratio is above 4.5:1.

### Don'ts
- Don't use gradient text or gradient backgrounds on buttons.
- Don't pair 1px borders with heavy blur shadows.
- Don't use display fonts for labels.
- Don't use saturated cream/beige default backgrounds.
- Don't use decorative animated lines (e.g., scanning lines) or scanline overlays.
- Don't use linear-gradient area chart fills; use flat, low-opacity fills.
