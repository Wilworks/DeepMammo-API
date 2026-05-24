---
title: DeepMammo
emoji: 
colorFrom: purple
colorTo: indigo
sdk: docker
pinned: true
license: mit
---

# DeepMammo — AI-Assisted Mammography Analysis

A production-grade multi-task deep learning inference API for breast cancer detection from mammogram images.

## What it does

Upload a mammogram image and get back:

- **Abnormality type** — mass or calcification with confidence score
- **Pathology** — benign or malignant with confidence score
- **Segmentation mask** — pixel-level abnormal region detection
- **Saliency map** — GradCAM-style model attention heatmap
- **Clinical report** — structured radiologist-style narrative (Groq LLM)
- **PDF report** — downloadable clinical document with patient personalisation

## Model Architecture

| Component | Detail |
|---|---|
| Backbone | EfficientNet-B4 |
| Neck | Feature Pyramid Network (FPN) |
| Attention | CBAM (Channel + Spatial) |
| Seg head | Encoder-Decoder with skip connections |
| Cls heads | Abnormality + Pathology (multi-task) |
| Format | ONNX (exported from PyTorch) |

## Training Data

| Dataset | Images |
|---|---|
| CBIS-DDSM | 6,206 |
| INbreast | 266 |
| After augmentation | **45,304** |

Augmentations: Horizontal Flip, Rotate, Random Brightness Contrast, Gauss Noise, Shift Scale Rotate

## API

```
POST /api/predict/
Content-Type: multipart/form-data

Fields:
  image        : PNG or JPG mammogram (required)
  patient_info : JSON string with patient details (optional)
```

## Stack

Python · PyTorch → ONNX · onnxruntime · Django · DRF · Groq LLM · ReportLab · Docker

## Developed by

**Wilfred Ayine** — AI Engineer (Junior)

---
⚠️ This is a research demo. Not validated for clinical use. Always consult a qualified radiologist.
