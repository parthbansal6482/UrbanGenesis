# Platform Specification — FarmGuard

This document details the functional specifications, domain modeling, LULC taxonomy, and core analytical frameworks of the FarmGuard/UrbanGenesis platform.

---

## 1. Context & Business Domain

Rapid urban sprawl degrades surrounding agricultural land and ecosystems. FarmGuard provides spatial remote sensing diagnostics for farmland encroachment monitoring, supporting Satyukt Analytics' core commercial applications:

### A. Sat4Risk (Hydrological Hazard Modeling)
- **Problem**: Urban sprawl converts permeable soil, cropland, and natural wetlands into impermeable built-up surfaces (concrete, roads). This reduces regional water retention, accelerating storm runoff.
- **Application**: Tracks changes in the Agricultural Buffer Index (ABI) to dynamically recalibrate flood and drought hazard models.

### B. MRV Carbon Credit Verification
- **Problem**: Voluntary and compliance carbon markets require verifiable, non-overlapping baselines of agricultural and natural vegetation cover.
- **Application**: Renders multi-year, native-resolution vegetation baselines to audit carbon sequestration claims.

### C. Crop Insurance Underwriting
- **Problem**: Farms adjacent to expanding urban perimeters face increased systemic risks (depleted water tables, soil pollution).
- **Application**: Categorizes agricultural zones into grades (A to F) to adjust actuarial premium tiers.

---

## 2. Land Use / Land Cover (LULC) Class Taxonomy

FarmGuard maps and tracks land cover classifications using a 10m native spatial resolution model aligned with the global annual ESRI land cover dataset:

| Class ID | Class Name | Hex Color | Color Representation | Functional Group |
|:---:|---|---|:---:|---|
| **0** | Background | `#000000` | Black | Noise / unclassified pixels |
| **1** | Buildings | `#DC2626` | Red | Developed Infrastructure (Encroachment) |
| **2** | Cropland | `#D4A017` | Gold | Agricultural Buffer (Buffer) |
| **3** | Dense Vegetation | `#228B22` | Forest Green | Forests & Tree Cover (Buffer) |
| **4** | Water Bodies | `#1E64C8` | Cobalt Blue | Open Water / Reservoirs (Buffer) |
| **5** | Bare Soil | `#D2B48C` | Tan | Fallow / Barren Land |

---

## 3. Mathematical Frameworks

### Agricultural Buffer Index (ABI)
The ABI quantifies the ratio of protective natural buffers to developed urban structures:

$$ABI = \frac{\text{Cropland} + \text{Dense Vegetation} + \text{Water Bodies}}{\text{Buildings}}$$

- **ABI > 2.0 (Grade A / Healthy Buffer)**: Highly resilient; buffer is at least double the infrastructure footprint.
- **ABI 1.0 – 2.0 (Grade B / Stable)**: Moderately resilient; urban expansion is controlled.
- **ABI 0.5 – 1.0 (Grade C / Elevated Risk)**: Development is actively encroaching on natural perimeters.
- **ABI 0.3 – 0.5 (Grade D / High Risk)**: Significant conversion of cropland.
- **ABI < 0.3 (Grade F / Critical Encroachment)**: The buffer is depleted, indicating severe vulnerability.

*Note: For regions with zero buildings, the index is capped at `99.99` to ensure JSON serialization compatibility and correct grading classification.*

### Cropland Loss Quantification (Hectares)
Cropland loss over time is calculated using native pixel counts:

$$\text{Cropland Loss (ha)} = \frac{(\text{Cropland Pixels}_{\text{before}} - \text{Cropland Pixels}_{\text{after}}) \times \text{Pixel Area (m}^2\text{)}}{10,000}$$

*Note: At 10m resolution, each pixel corresponds to exactly $100\text{ m}^2$ (0.01 hectares).*
