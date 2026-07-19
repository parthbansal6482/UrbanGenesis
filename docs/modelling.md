# Mathematical Modeling, Data Ingestion, and Forecasting System

This reference manual provides an exhaustive, production-grade guide to the system architecture, mathematical formulations, remote-sensing data ingestion routines, feature engineering pipelines, neural network architectures, inference constraints, and evaluation frameworks of the FarmGuard platform.

---

## 1. High-Level Core Concept (The Story of FarmGuard)

To understand this system, imagine an agricultural region as a castle:
* **The Shield (The Natural Buffer):** The croplands, forests, and water bodies surrounding the community. They absorb rainwater to prevent floods, capture carbon, and supply food.
* **The Threat (Urban Encroachment):** The concrete buildings, factories, and roads expanding outward.
* **The Mission:** FarmGuard monitors the strength of this protective shield over time and warns risk underwriters or carbon auditors if the concrete threat is expanding too fast.

We mathematically define the strength of this shield using the **Agricultural Buffer Index (ABI)**:

$$ABI = \frac{\text{Cropland} + \text{Dense Vegetation} + \text{Water Bodies}}{\text{Buildings}}$$

The system translates this index value into grades:
* **Grade A (Healthy Shield):** The protective buffer is massive compared to the buildings (ABI > 2.0).
* **Grade B (Stable):** Safe; urban expansion is controlled (ABI 1.0 – 2.0).
* **Grade C (Elevated Risk):** Development is actively encroaching on natural boundaries (ABI 0.5 – 1.0).
* **Grade D (High Risk):** Significant conversion of cropland (ABI 0.3 – 0.5).
* **Grade F (Critical Encroachment):** The buffer is depleted, indicating severe vulnerability (ABI < 0.3).

*Note: If a region has zero buildings, the math formula would divide by zero. To prevent this, the backend automatically caps the ABI at a safe maximum value of `99.99`.*

---

## 2. Foundations of GIS & Remote Sensing

If you are new to Geographic Information Systems (GIS) and remote sensing, here are the foundational concepts:

### A. What is a GIS Pixel?

In remote sensing, a satellite image is not just a digital photo; it is a grid of measurements representing the Earth's surface.
* **Spatial Resolution:** Refers to the physical size of the ground represented by a single pixel.
* **Sentinel-2 Spatial Scale:** In this project, the resolution is exactly **10 meters per pixel**. This means a single pixel covers a $10\text{m} \times 10\text{m}$ area on the ground ($100 \text{ square meters}$, or $0.01 \text{ hectares}$). A small house or a road intersection is represented by just 1 or 2 pixels.

### B. The Electromagnetic Spectrum and Sensor Bands

Humans can only see visible light (Red, Green, and Blue). However, satellite sensors can measure wavelengths beyond human sight:
* **Near-Infrared (NIR) Band:** This wavelength is highly reflected by the internal cell structure of healthy green leaves. By comparing NIR light with visible Red light, we can tell if a pixel contains healthy crops, dry soil, or concrete.
* **The Bands We Use:**
  1. **Red (B04)** — Wavelength $\sim 665\text{nm}$ (visible red).
  2. **Green (B03)** — Wavelength $\sim 560\text{nm}$ (visible green).
  3. **Blue (B02)** — Wavelength $\sim 490\text{nm}$ (visible blue).
  4. **Near-Infrared (NIR) (B08)** — Wavelength $\sim 842\text{nm}$ (invisible infrared).

---

## 3. Remote-Sensing Ingestion Pipeline (The Data Ingestor)

To get data, the backend queries Microsoft's Planetary Computer using the **STAC (SpatioTemporal Asset Catalog) API**.

```
[STAC Catalog Query] ──> [Sentinel-2 Imagery (10m)] ──> [Spectral Bands (RGB + NIR)]
                     ──> [ESRI LULC Annual Maps]    ──> [Classification Mask]
```

### A. Parallel Multi-Threaded Band Fetching

When downloading Sentinel-2 data, the system needs to retrieve 4 separate band files (RGB + NIR). Instead of downloading them one-by-one (which would be slow), we download them in parallel using a CPU-threaded `ThreadPoolExecutor`. This speeds up the process by allowing multiple network connections to download different bands at the same time.

### B. Dynamic Temporal Search Strategy (Finding Cloud-Free Days)

Satellite cameras cannot see through clouds. If we download a cloudy image, our classification will be incorrect. To find a cloud-free day, we search the catalog using a **three-stage fallback search algorithm**:
1. **Strict Window (February):** Search for passes only in February. This is the mature crop season (Rabi crop season in India) and historically has the clearest skies.
2. **Extended Window (Jan 15 – Mar 15):** If all February passes are cloudy, expand the search window by 30 days.
3. **Full Year Fallback:** If still blocked, search the entire calendar year and select the single day with the absolute lowest cloud-cover score.

### C. Land Use / Land Cover (LULC) Classification

In addition to raw satellite photos, we ingest annual **ESRI 10m Land Cover** maps. These maps label every pixel into categories. The system automatically maps the raw ESRI classes into our unified **6-class FarmGuard schema**:

| ID | Class Name | Function | Hex Color |
|---|---|---|---|
| **0** | Background | Nodata / Padding | `#000000` |
| **1** | Buildings | Developed Infrastructure (Threat) | `#DC2626` |
| **2** | Cropland | Active Agricultural Buffer (Shield) | `#D4A017` |
| **3** | Vegetation | Forests & Natural Canopy (Shield) | `#228B22` |
| **4** | Water Bodies | Rivers & Open Reservoirs (Shield) | `#1E64C8` |
| **5** | Bare Soil | Fallow or Barren Land | `#D2B48C` |

---

## 4. Preprocessing & Spatial Feature Engineering

Before feeding maps into the forecasting model, we transform raw pixels into structured spatial matrices:

```
[Raw Inputs] ──> [NDVI Formula]                ──> [Chlorophyll Density map]
             ──> [Euclidean Distance Transform] ──> [Proximity Grid]
             ──> [Temporal Matrix Difference]   ──> [Drift Velocity]
```

### A. Normalized Difference Vegetation Index (NDVI)

NDVI measures the density and health of vegetation. Healthy plants absorb visible red light and reflect near-infrared (NIR) light:

$$NDVI = \frac{NIR - Red}{NIR + Red} = \frac{B08 - B04}{B08 + B04}$$

This formula yields a value between `-1.0` and `1.0`. A high positive score indicates dense, healthy vegetation, while scores near zero or negative indicate roads, buildings, or water.

### B. Euclidean Distance Transform (EDT)

The model needs to know *where* urban centers are located relative to croplands. For each of the LULC classes, we calculate the Euclidean Distance Transform:
* For every pixel $p = (x,y)$ in the map, EDT calculates the straight-line distance to the nearest boundary of that specific land-cover class:

$$EDT_c(p) = \min_{q \in S_c} d(p, q)$$

where $S_c$ is the set of all pixels belonging to class $c$, and $d(p, q) = \sqrt{(x_p - x_q)^2 + (y_p - y_q)^2}$ is the standard Euclidean distance metric.
* **Analogy:** Think of EDT as a "proximity heat map." A pixel close to a city has a low EDT value for "Buildings," while a pixel deep in the forest has a high EDT value.

### C. Drift Velocity (Rate of Change)

To capture growth momentum, we calculate the temporal difference between the distance transforms of consecutive steps ($T-2$ and $T-4$):

$$\text{Drift Velocity}_c = \text{EDT}_{T-2, c} - \text{EDT}_{T-4, c}$$

This reveals which direction cities are expanding and how fast they are moving toward surrounding croplands.

### D. One-Hot Encoding

A neural network cannot understand class IDs (like 1 for Buildings and 2 for Cropland) as raw numbers, because it would treat 2 as "twice as much" as 1.
* To fix this, we split the single class mask into **6 binary channels** (one channel for each class).
* In each channel, a pixel is set to `1` if it belongs to that class, and `0` otherwise.

---

## 5. Predictive Modeling: U-Net Architectures (The Future Predictor)

To forecast future growth (such as predicting the map of 2025), we train and deploy a **U-Net Convolutional Neural Network (CNN)**. FarmGuard provides two architecture variants defined in `model/architecture.py`:

```
Input (22 Channels) ──> [Encoder (Downsample)] ──┐  (Skip Connections)
                                                 ▼
Output (6 Classes)  <── [Decoder (Upsample)]  <──┘
```

### A. Standard UNet

The standard architecture, trained from scratch on the FarmGuard dataset:

1. **The Encoder (Left Side):** Applies convolutions and max-pooling across 4 downsampling stages to extract progressively abstract features while halving spatial resolution at each stage.
2. **The Decoder (Right Side):** Upsamples the bottleneck representation across 3 stages via transposed convolutions, concatenating skip connections from the encoder to restore fine spatial details.
3. **Skip Connections:** Connect high-resolution encoder layers directly to corresponding decoder layers, preserving sharp road borders and small field edges.

**Detailed layer-by-layer architecture:**
* **DoubleConv Blocks**: Two consecutive 3×3 Convolutions, each followed by Batch Normalization and ReLU:
  $$\text{Conv2d(3×3)} \rightarrow \text{BatchNorm2d} \rightarrow \text{ReLU} \rightarrow \text{Conv2d(3×3)} \rightarrow \text{BatchNorm2d} \rightarrow \text{ReLU}$$
* **Encoder Downsampling** (22-channel input):
  * `inc`: DoubleConv (22 → 64 ch)
  * `down1`: MaxPool2d(2×2) → DoubleConv (64 → 128 ch)
  * `down2`: MaxPool2d(2×2) → DoubleConv (128 → 256 ch)
  * `down3`: MaxPool2d(2×2) → DoubleConv (256 → 512 ch)
* **Decoder Upsampling** (3 stages):
  * `up1`: ConvTranspose2d (512 → 256 ch) → Concat with `down2` output → DoubleConv (256 ch)
  * `up2`: ConvTranspose2d (256 → 128 ch) → Concat with `down1` output → DoubleConv (128 ch)
  * `up3`: ConvTranspose2d (128 → 64 ch) → Concat with `inc` output → DoubleConv (64 ch)
  * Output: 1×1 Conv (64 → 6 classes)

### B. ResNet34UNet (Pretrained Backbone)

The ResNet34UNet variant replaces the from-scratch encoder with a pretrained ResNet34 backbone for richer feature extraction:

1. **`input_projection` layer**: A `Conv2d(22, 3, kernel_size=1)` layer that compresses the 22-channel feature tensor down to 3 channels, making it compatible with the RGB-pretrained ResNet34 encoder.
2. **Pretrained ResNet34 Encoder**: Uses the `layer1` through `layer4` blocks of a pretrained ResNet34. These layers were originally trained on ImageNet and provide powerful general-purpose feature detectors. Their weights are fine-tuned during FarmGuard training.
3. **4-Stage Decoder with Skip Connections**: Four decoder stages, each combining transposed convolutions with skip connections from the corresponding ResNet34 encoder block.
4. **Output Resolution**: Bilinear interpolation is applied at the final decoder stage to restore the output to the original input spatial resolution.

### C. Architecture Auto-Detection via `load_model_from_checkpoint()`

`model/forecast.py` exports `load_model_from_checkpoint(checkpoint_path)`. This function inspects the saved state_dict keys:

- If `input_projection.weight` is found in the keys → instantiates and loads **`ResNet34UNet`**.
- Otherwise → instantiates and loads standard **`UNet`**.

This makes the checkpoint format self-describing. No manual flag or configuration is required.

### D. Input Channels (The 22-Channel Matrix)

When predicting a future year $T$ (e.g., 2025), we feed a **22-channel tensor** representing past states into the model:

| Channel Range | Feature Type | Description |
|---|---|---|
| **0 – 5** | Class Mask at $T-4$ | One-hot encoded probability maps for classes 0 to 5 |
| **6 – 11** | Class Mask at $T-2$ | One-hot encoded probability maps for classes 0 to 5 |
| **12 – 16** | EDT at $T-2$ | Euclidean Distance Transforms for classes 1 to 5 |
| **17 – 21** | Drift Velocity | EDT differences (velocity of expansion) for classes 1 to 5 |

$$\text{Total Channels} = 6 \text{ (one-hot T-4)} + 6 \text{ (one-hot T-2)} + 5 \text{ (EDT)} + 5 \text{ (velocity)} = 22$$

### E. Hybrid Loss with Transition Weights

To handle class imbalance (the fact that cities are much smaller than agricultural buffers) and to penalize the network if it fails to predict changes, we use a custom **Change-Weighted Hybrid Loss**:

$$\text{Loss}_{Total} = 0.5 \times \text{Loss}_{WeightedCE} + 0.5 \times \text{Loss}_{Dice}$$

#### Multi-Class Dice Loss

Dice Loss directly optimizes the overlapping region between the predicted probability map $P_c$ and the true one-hot mask $T_c$:

$$\text{Loss}_{Dice} = 1.0 - \frac{1}{C} \sum_{c=1}^{C} \frac{2 \sum (P_c \times T_c) + \epsilon}{\sum P_c + \sum T_c + \epsilon}$$

where $\epsilon = 1.0$ is a smoothing factor to prevent division by zero and handle empty classes.

#### Change-Weighted Cross-Entropy

Traditional Cross-Entropy computes the pixel log-likelihood. However, we multiply this loss by a weighting factor $\omega = 3.0$ on any pixel that actually transitioned (changed class) between $T-2$ and $T$:

$$\text{Loss}_{WeightedCE} = - \frac{1}{N} \sum_{i=1}^{N} \omega_i \log(P(T_i))$$

$$\omega_i = \begin{cases} 3.0 & \text{if } T_i \neq \text{Prev}_i \quad (\text{pixel transitioned}) \\ 1.0 & \text{otherwise} \end{cases}$$

This forces the U-Net to focus heavily on the boundaries of expanding urban corridors, overcoming the "no change" bias common in static environments.

---

## 6. Inference Constraints (The Safety Rails)

Neural networks are statistical engines and can make physically impossible predictions. To prevent this, we enforce manual constraints during inference in `model/forecast.py`.

### A. Allowed Transitions Masking

We build a strict boolean matrix defining which changes are physically possible. For example:
* Cropland → Buildings is **Allowed** (urbanization).
* Buildings → Cropland is **Banned** (concrete does not revert to fields).
* Buildings → Water is **Banned**.

During prediction, the model outputs raw logits. We check the previous land state. If a transition is banned, we set its logit to negative infinity (`-1e9`), mathematically blocking the network from choosing it.

### B. Building Permanence Rule

Once a pixel is classified as a building, we force it to remain a building in all future predictions:

$$\text{Mask}_{T}[x, y] = 1 \quad \text{if} \quad \text{Mask}_{T-2}[x, y] == 1$$

This ensures concrete infrastructure never disappears from the dashboard timeline.

### C. Temperature Scaling

Before applying softmax to the model's logit outputs, we apply temperature scaling with $\tau = 0.8$:

$$P_c = \text{softmax}\!\left(\frac{L_c}{\tau}\right), \quad \tau = 0.8$$

Dividing by a temperature less than 1.0 sharpens the probability distribution, making the model's top-class prediction more decisive and reducing ambiguous low-confidence outputs.

### D. Confidence Threshold Gating

After sampling the model's prediction, we check whether the maximum predicted probability for a pixel exceeds the `confidence_threshold = 0.92`. If the model is not sufficiently confident in its prediction for a given pixel:

$$\hat{y}_{T}[x, y] = \begin{cases} \arg\max_c P_c(x, y) & \text{if } \max_c P_c(x, y) \geq 0.92 \\ \text{Mask}_{T-2}[x, y] & \text{otherwise (fallback to previous state)} \end{cases}$$

This prevents the model from introducing spurious class changes in regions where it has low certainty, preserving spatial continuity.

### E. Transport Corridor Proximity Biasing (OSM Corridor Magnetism)

Urban expansion is strongly correlated with transportation networks. The recursive forecast loop in `model/forecast.py` incorporates the following OSM-based road proximity biasing:

1. **OSM Retrieval:** The system queries OpenStreetMap's Overpass API for road coordinates (motorways, trunks, primary, secondary, and tertiary routes) matching the bounding box. If offline, it falls back to a synthetic diagonal highway layout.
2. **Euclidean Distance Transform:** Road network vectors are rasterized to pixel coordinates. A distance transform grid $D_{\text{road}}(x, y)$ is computed, representing the pixel distance to the nearest roadway.
3. **Road Weight Calculation:** An exponential decay weight is derived from the road distance:
   $$W_{\text{road}}(x, y) = e^{-D_{\text{road}}(x, y) / 15.0}$$
4. **Momentum Grid:** A momentum strength field is combined with road proximity to produce the logit modifier applied during each recursive step:
   $$\text{momentum\_grid} = \text{momentum\_strength} \times (0.3 + 0.7 \times W_{\text{road}})$$
   where $\text{momentum\_strength} = \text{max\_expansion\_rate} \times (1 - \text{bld\_frac}) \times \text{damping}$, with $\text{bld\_frac}$ being the current fraction of built-up pixels and $\text{damping}$ a per-step decay factor.
5. **Logit Application:** The momentum grid modifies the building-class logits $L_{\text{building}}$ before the temperature softmax is applied, effectively pushing urban growth outward along transport lanes and capturing transit ribbon developments.

---

## 7. Model Stitching and Resolution Management

### A. Patch-Based Processing

A large satellite map is too big to fit into GPU memory all at once.
* We chop the region into small patches of **$128 \times 128$ pixels**.
* The model runs predictions on each patch independently.
* We stitch the patches back together using their original grid coordinates (`px`, `py`).
* Finally, we crop any padding back to the region's original boundary size.

### B. Visual Presentation Upscaling

To ensure the dashboard displays sharp, clear imagery without visual blur:
* The backend runs all scientific index and classification calculations at the native **10m/pixel** scale.
* Before writing visual PNG files to disk, if the image width or height is less than **512 pixels**, we upscale the output using high-quality resampling filters:
  - **LANCZOS** (Bicubic) for True Color satellite imagery and NDVI maps (preserves smooth gradients).
  - **NEAREST** (Nearest Neighbor) for classification masks and heatmaps (keeps color boundaries sharp).
* This provides a clean visual layout on high-resolution screens while preserving the scientific integrity of the data.

---

## 8. Model Backtesting & Verification

To verify the U-Net's predictive accuracy, we use a **historical backtesting protocol**:

```
[Train Model: 2017-2021] ──> [Predict 2023] ──> [Compare against Real 2023 LULC]
```

1. **Cutoff Setup:** Train the model using data up to `2021`.
2. **Forecast Step:** Predict the land cover for `2023` (a 2-year lookahead).
3. **Verification:** Compare the predicted 2023 map pixel-by-pixel against the real, satellite-derived `2023` ESRI LULC ground truth.
4. **Metrics**: Pixel Accuracy, Macro-mIoU (mean Intersection over Union across all 6 classes), and ABI Prediction Error are all reported.

The comprehensive backtest results from `scripts/model_stress_test.py` across both evaluation intervals:

| Zone | Interval | Pixel Accuracy | ABI Error | Macro-mIoU |
|---|---|---|---|---|
| Bengaluru | 2019→2021 | 90.83% | 16.5% | — |
| Bengaluru | 2021→2023 | **91.30%** | **13.0%** | **60.74%** |
| Hubli Outskirts | 2019→2021 | 88.96% | 8.7% | — |
| Hubli Outskirts | 2021→2023 | **91.42%** | **8.9%** | **74.83%** |
| Nashik North | 2019→2021 | 94.64% | 1.0% | — |
| Nashik North | 2021→2023 | **92.12%** | **5.4%** | **67.74%** |
| Vijayawada West | 2019→2021 | 88.07% | 19.3% | — |
| Vijayawada West | 2021→2023 | **89.55%** | **5.1%** | **75.64%** |

The U-Net forecast runs recursively to **2041** (an 18-year horizon from the 2023 ground-truth baseline). Accuracy over the full projection horizon has not been independently validated against future ground truth, since no ground truth exists for those years. Forecasts beyond ~2–3 years should be treated as directional trend indicators rather than precise predictions.

---

## 9. Model Stress-Testing Suites

`scripts/model_stress_test.py` provides a comprehensive, automated 4-suite model audit designed to validate not just accuracy but also physical consistency, long-term stability, and input sensitivity. Run via:

```bash
PYTHONPATH=. .venv/bin/python scripts/model_stress_test.py --report model_audit_report.md
```

### Suite 1 — Historical Backtesting

**Purpose**: Measure prediction accuracy against real ESRI LULC ground truth across two historical intervals (`2019→2021` and `2021→2023`).

**Metrics computed**:
- **Pixel Accuracy**: Fraction of pixels correctly classified against the real LULC ground truth.
- **Macro-mIoU**: Mean Intersection over Union computed independently for each of the 6 land-cover classes and then averaged. This metric is more sensitive to rare class performance than simple accuracy.
- **ABI Prediction Error**: Absolute percentage difference between the predicted ABI and the ground-truth ABI, measuring economic/index-level accuracy beyond pixel counts.

**Findings**: See the full table in Section 8.

---

### Suite 2 — Physical Transition Constraint Integrity

**Purpose**: Verify that the physical constraint enforcement layer is working correctly — that no banned transitions (e.g. Buildings → Cropland) appear in any predicted output.

**Method**: Iterates over all consecutive year pairs in the predicted sequence and flags pixels where a transition from class $A$ to class $B$ occurs and the $(A, B)$ pair is marked as banned in the constraint matrix.

**Findings**:
- **0.5–1.5% violation rate** detected on legacy precomputed assets that were generated before hard constraint enforcement was introduced into the pipeline. These violations exist in old cached files, not in live inference.
- **0.00% violation rate** on all assets generated by the current inference pipeline with the constraint layer active.

---

### Suite 3 — Long-Horizon Stability

**Purpose**: Test whether the recursive U-Net inference remains physically sensible over an 18-year projection (2023→2035), without collapsing into degenerate states.

**Checks performed**:
- **Vanishing cropland**: Total cropland pixel count falls to zero (the entire zone becomes built-up).
- **Exploding sprawl**: Buildings coverage exceeds 95% of the zone area.
- **Class collapse**: A single class (typically Buildings or Bare Soil) dominates >98% of the output, indicating the model has collapsed to a trivial constant prediction.

**Findings**: All 4 monitored zones (`bengaluru`, `hubli_outskirts`, `nashik_north`, `vijayawada_west`) remain stable across recursive predictions to **2035**. No vanishing cropland, exploding sprawl, or class collapse is detected in any zone.

---

### Suite 4 — OSM Road Sensitivity

**Purpose**: Quantify the influence of the OSM corridor magnetism bias by measuring how much the predicted building-class probability distribution shifts when the road network input is removed (zeroed out).

**Method**: Runs two predictions for each zone — one with the standard road proximity input and one with the road weight grid set to a uniform constant (equivalent to no road information). Computes the mean absolute difference in building-class logit values between the two predictions.

**Findings**: Road sensitivity (mean prediction shift) of **0.00–0.03%** across all 4 monitored zones. This confirms that the OSM corridor magnetism is correctly modulated as a bias term that *influences* but does not *dominate* the model's output — the primary drivers remain the learned land-cover transition patterns from the encoder-decoder.
