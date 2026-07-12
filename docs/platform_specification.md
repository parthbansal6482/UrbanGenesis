# Platform Specification — FarmGuard

This document details the functional specifications, domain modeling, LULC taxonomy, and core analytical frameworks of the FarmGuard/UrbanGenesis platform.

---

## 1. Context & Business Domain

Rapid urban sprawl degrades surrounding agricultural land and ecosystems. FarmGuard provides spatial remote sensing diagnostics for farmland encroachment monitoring, supporting core commercial applications:

### A. Hydrological Hazard Modeling
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

---

## 4. U-Net Forecasting Model & Backtesting Framework

To support long-term risk underwriting and MRV carbon credit baselining, FarmGuard includes a U-Net convolutional neural network model configured to project future land-cover state distributions (for example, forecasting 2025 configurations based on historical trends).

### Forecasting Methodology
The forecast model takes historical multi-year LULC class transitions and spatial maps as input features and outputs a predicted probability map of LULC classes. 

### Backtesting Validation
To establish empirical trustworthiness, a backward-looking validation (backtesting) framework was implemented:
1. **Scenario Setup**: The forecast cutoff is set to `2021`. The model is evaluated on its ability to forecast the state of land cover in `2023` (2-year lookahead).
2. **Ground Truth Comparison**: The predicted 2023 land cover classification mask is compared pixel-by-pixel against the actual `2023` ESRI LULC satellite-derived ground truth.
3. **Evaluation Metrics**:
   - **Pixel Accuracy**: The percentage of pixels correctly classified in the forecast compared to actual LULC ground truth.
   - **ABI Prediction Error**: The relative difference between the predicted ABI and actual ABI for the target year.
     $$\text{ABI Error (\%)} = \frac{|\text{ABI}_{\text{predicted}} - \text{ABI}_{\text{actual}}|}{\text{ABI}_{\text{actual}}} \times 100$$

### Empirical Backtest Results
Across the four pre-registered agricultural zones, the backtesting harness measured the following performance metrics:

| Zone | Pixel Accuracy | ABI Prediction Error | Key Characteristics |
|---|---|---|---|
| **Nashik North** | 93.1% | 13.6% | Grape/onion belt. Stable agricultural buffer. |
| **Hubli Outskirts** | 90.1% | 6.4% | Peri-urban transition zone. |
| **Vijayawada West** | 88.9% | 2.6% | Highly dynamic riverine cropland boundary. |
| **Bengaluru** | 91.1% | 10.9% | Rapid urban encroachment environment. |

*Note: These results validate a 2-year forecast horizon. Projections beyond a 2-3 year horizon (e.g. up to 2041) have higher uncertainty and should be used as directional trend indicators.*

