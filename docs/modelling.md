# Mathematical Modeling, Data Ingestion, and Forecasting System

This reference manual provides an exhaustive, production-grade guide to the system architecture, mathematical formulations, remote-sensing data ingestion routines, feature engineering pipelines, neural network architecture, and evaluation frameworks of the FarmGuard platform.

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

## 5. Predictive Modeling: U-Net ConvNet (The Future Predictor)

To forecast future growth (such as predicting the map of 2025), we train and deploy a **U-Net Convolutional Neural Network (CNN)**.

```
Input (22 Channels) ──> [Encoder (Downsample)] ──┐  (Skip Connections)
                                                 ▼
Output (6 Classes)  <── [Decoder (Upsample)]  <──┘
```

### A. What is a U-Net?
A U-Net is a symmetric neural network shaped like a "U":
1. **The Encoder (Left Side):** Takes the input and repeatedly applies convolutions and downsamplings. It reduces the spatial resolution while extracting highly abstract features (e.g., recognizing "neighborhood shapes" rather than individual pixels).
2. **The Decoder (Right Side):** Upsamples the features back to the original resolution, constructing a clean pixel map.
3. **Skip Connections:** Connect the high-resolution layers of the encoder directly to the decoder. This allows the network to preserve fine spatial details (like sharp road borders and small fields) that would otherwise be lost during downsampling.

### B. Convolution Layer Basics (For Beginners)
A convolution is like a small flashlight (called a **kernel**) sliding across the image.
* **Kernel Size (3x3):** The flashlight looks at a $3 \times 3$ grid of pixels at a time. It multiplies the pixel values by a set of weights (which the model learns during training) to detect features like edges, corners, or textures.
* **Stride (1):** The flashlight moves 1 pixel at a time.
* **Padding (1):** We add empty border pixels around the image edges so the flashlight can slide over the border pixels without shrinking the output size.
* **Max Pooling (2x2):** Downsamples the image by taking the maximum value in every $2 \times 2$ pixel block, reducing the image size by half.
* **Transposed Convolution:** The opposite of pooling; it scales up the image by inserting spacing and applying learning weights to reconstruct the original size.

### C. Input Channels (The 22-Channel Matrix)
When predicting a future year $T$ (e.g., 2025), we feed a **22-channel tensor** representing past states into the model:

| Channel Range | Feature Type | Channels Description |
|---|---|---|
| **0 – 5** | Class Mask at $T-4$ | One-hot encoded probability maps for classes 0 to 5. |
| **6 – 11** | Class Mask at $T-2$ | One-hot encoded probability maps for classes 0 to 5. |
| **12 – 16** | EDT at $T-2$ | Euclidean Distance Transforms for classes 1 to 5. |
| **17 – 21** | Drift Velocity | EDT differences (velocity of expansion) for classes 1 to 5. |

$$\text{Total Channels} = 6 \text{ (one-hot T-4)} + 6 \text{ (one-hot T-2)} + 5 \text{ (EDT)} + 5 \text{ (velocity)} = 22$$

### D. Detailed Layer-by-Layer Architecture
The PyTorch U-Net contains the following layer modules:
* **DoubleConv Blocks**: Consist of two consecutive 3x3 Convolutions, each followed by a 2D Batch Normalization layer (which stabilizes training by normalizing pixel values) and a rectified linear unit (ReLU) activation function (which replaces negative values with zero to introduce non-linearity).
  $$\text{Conv2d(3x3)} \rightarrow \text{BatchNorm2d} \rightarrow \text{ReLU} \rightarrow \text{Conv2d(3x3)} \rightarrow \text{BatchNorm2d} \rightarrow \text{ReLU}$$
* **Encoder Downsampling**: DoubleConv blocks combined with 2x2 Max Pooling layers to reduce dimensions:
  * Input (22 ch) $\rightarrow$ `inc` (DoubleConv 64)
  * `down1`: MaxPool2d(2x2) $\rightarrow$ DoubleConv (64 $\rightarrow$ 128 ch)
  * `down2`: MaxPool2d(2x2) $\rightarrow$ DoubleConv (128 $\rightarrow$ 256 ch)
  * `down3`: MaxPool2d(2x2) $\rightarrow$ DoubleConv (256 $\rightarrow$ 512 ch)
* **Decoder Upsampling**: 2x2 Transposed Convolutions (`ConvTranspose2d` with stride=2) combined with skip connection concatenations along the channel dimension (`dim=1`):
  * `up1`: ConvTranspose2d (512 $\rightarrow$ 256 ch) $\rightarrow$ Concat with `down2` output (512 total channels) $\rightarrow$ DoubleConv (256 ch)
  * `up2`: ConvTranspose2d (256 $\rightarrow$ 128 ch) $\rightarrow$ Concat with `down1` output (256 total channels) $\rightarrow$ DoubleConv (128 ch)
  * `up3`: ConvTranspose2d (128 $\rightarrow$ 64 ch) $\rightarrow$ Concat with `inc` output (128 total channels) $\rightarrow$ DoubleConv (64 ch)
  * Output: 1x1 Convolution (`nn.Conv2d(64, out_channels, 1)`) mapping the 64 features to target LULC classes.

### E. Hybrid Loss with Transition Weights
To handle class imbalance (the fact that cities are much smaller than agricultural buffers), and to penalize the network if it fails to predict changes, we use a custom **Change-Weighted Hybrid Loss**:

$$\text{Loss}_{Total} = 0.5 \times \text{Loss}_{WeightedCE} + 0.5 \times \text{Loss}_{Dice}$$

#### 1. Multi-Class Dice Loss
Dice Loss directly optimizes the overlapping region between the predicted probability map $P_c$ and the true one-hot mask $T_c$:

$$\text{Loss}_{Dice} = 1.0 - \frac{1}{C} \sum_{c=1}^{C} \frac{2 \sum (P_c \times T_c) + \epsilon}{\sum P_c + \sum T_c + \epsilon}$$

where $\epsilon = 1.0$ is a smoothing factor to prevent division by zero and handle empty classes.

#### 2. Change-Weighted Cross-Entropy
Traditional Cross-Entropy computes the pixel log-likelihood. However, we multiply this loss by a weighting factor $\omega = 3.0$ on any pixel that actually transitioned (changed class) between $T-2$ and $T$:

$$\text{Loss}_{WeightedCE} = - \frac{1}{N} \sum_{i=1}^{N} \omega_i \log(P(T_i))$$

$$\omega_i = \begin{cases} 3.0 & \text{if } T_i \neq \text{Prev}_i \quad (\text{pixel transitioned}) \\ 1.0 & \text{otherwise} \end{cases}$$

This forces the U-Net to focus heavily on the boundaries of expanding urban corridors, overcoming the "no change" bias common in static environments.

---

## 6. Inference Constraints (The Safety Rails)

Neural networks are statistical engines and can make physically impossible predictions. To prevent this, we enforce two manual constraints during inference:

### A. Allowed Transitions Masking
We build a strict boolean matrix defining which changes are physically possible. For example:
* Cropland $\rightarrow$ Buildings is **Allowed** (urbanization).
* Buildings $\rightarrow$ Cropland is **Banned** (concrete does not revert to fields).
* Buildings $\rightarrow$ Water is **Banned**.

During prediction, the model outputs "logits" (raw scores). We check the previous land state. If a transition is banned, we set its logit to negative infinity (`-1e9`), mathematically blocking the network from choosing it.

### B. Building Permanence Rule
Once a pixel is classified as a building, we force it to remain a building in all future predictions:

$$\text{Mask}_{T}[x, y] = 1 \quad \text{if} \quad \text{Mask}_{T-2}[x, y] == 1$$

This ensures concrete infrastructure never disappears from our dashboard timeline.

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

Across our monitored zones, this backtest achieved the following verified scores:

* **Nashik North:** 93.1% Pixel Accuracy (13.6% ABI Error)
* **Hubli Outskirts:** 90.1% Pixel Accuracy (6.4% ABI Error)
* **Vijayawada West:** 88.9% Pixel Accuracy (2.6% ABI Error)
* **Bengaluru:** 91.1% Pixel Accuracy (10.9% ABI Error)
