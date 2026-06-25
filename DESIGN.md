# Design

## Overview
A clean, structured modern light-mode dashboard designed for agriculture analysts and risk underwriters. It highlights native 10m satellite imagery, land cover changes, and encroachment warning alerts.

## Colors
- **Primary Accent**: `#059669` (Emerald 600) — used for primary action buttons, active states, and stable indicators.
- **Encroachment Alert**: `#DC2626` (Red 600) — used for critical encroachment alerts and warning badges.
- **Warning Accent**: `#D4A017` (Cropland Gold) — used for cropland visualization and warning status.
- **Neutral Background**: `#F8FAFC` (Slate 50) — main application background.
- **Neutral Surface**: `#FFFFFF` (White) — card backgrounds and panel elements.
- **Neutral Border**: `#E2E8F0` (Slate 200) — crisp dividers and borders.
- **Text Ink**: `#0F172A` (Slate 900) — main headings.
- **Text Muted**: `#475569` (Slate 600) — supporting text and labels.

## Typography
- **Font Family**: `'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` for both display and body copy to ensure high readability and consistency.
- **Font Sizes**:
  - H1: `2.25rem` (Title)
  - H2: `1.25rem` (Section Headers)
  - Body: `0.875rem` (Text)
  - Label: `0.75rem` (Muted metrics)

## Elevation
- **Flat Surface**: `border: 1px solid #E2E8F0` with zero shadow for general structure.
- **Card Hover Elevation**: `box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05)` with `border-color: #CBD5E1` for hover feedback.

## Components
- **Primary Button**: `#059669` background, `#FFFFFF` text, `border-radius: 8px`, `padding: 10px 20px`, active hover state `#047857`.
- **Panel Card**: `#FFFFFF` background, `border-radius: 12px`, `border: 1px solid #E2E8F0`, `padding: 20px`.
- **Segmented Toggle**: Grouped buttons with `#059669` background and `#FFFFFF` text for the active item, and `#FFFFFF` background with `#E2E8F0` borders and `#475569` text for inactive options.
- **Form Inputs**: Numeric coordinate entry boxes with clear placeholder labels, border color transitions (neutral `#E2E8F0` to active Emerald `#059669`), and compact descriptive helper text.
- **Status Badge**:
  - Critical: background `#FEE2E2`, text `#991B1B`.
  - Stable: background `#D1FAE5`, text `#065F46`.
  - Neutral: background `#F1F5F9`, text `#334155`.

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
