import numpy as np
import cv2
import base64
from PIL import Image
import io


ABNORMALITY_LABELS = ['mass', 'calcification']
PATHOLOGY_LABELS   = ['benign', 'malignant']


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def decode_classification(logits: np.ndarray, labels: list) -> dict:
    """
    Converts raw (1, 2) logits → label + confidence score.

    Example:
        logits = [[-0.3, 1.2]]
        softmax → [0.18, 0.82]
        argmax  → 1  → label = 'malignant'
        confidence = 0.82
    """
    probs = softmax(logits[0])          # shape (2,)
    idx   = int(probs.argmax())
    return {
        'label':      labels[idx],
        'confidence': round(float(probs[idx]), 4),
        'probabilities': {
            labels[i]: round(float(probs[i]), 4)
            for i in range(len(labels))
        }
    }


def decode_segmentation(seg_logits: np.ndarray, original_size: tuple) -> dict:
    """
    Converts raw (1, 1, 512, 512) logits → binary mask + overlay images.

    Steps:
        1. sigmoid  → probabilities (0 to 1)
        2. > 0.5    → binary mask (0 or 1)
        3. resize   → match original uploaded image size
        4. encode   → base64 PNG strings for the API response
    """
    prob_map = sigmoid(seg_logits[0, 0])          # (512, 512), float
    binary_mask = (prob_map > 0.5).astype(np.uint8) * 255  # 0 or 255

    h, w = original_size

    # Resize mask back to original image dimensions
    mask_resized = cv2.resize(binary_mask, (w, h), interpolation=cv2.INTER_NEAREST)

    return {
        'mask_b64':    _encode_mask(mask_resized),
        'overlay_b64': None,           # filled in after we have the original image
        'mask_array':  mask_resized,   # kept in memory for overlay generation
        'coverage_pct': round(float((binary_mask > 0).mean() * 100), 2),
    }


def build_overlay(original_image: np.ndarray, mask_array: np.ndarray) -> str:
    """
    Blends the segmentation mask (sky-blue tint) onto the original image.
    Returns base64 PNG string.
    """
    overlay = original_image.copy()
    # Where mask is white (255), tint sky-blue
    overlay[mask_array == 255] = [56, 189, 248]
    blended = cv2.addWeighted(original_image, 0.65, overlay, 0.35, 0)
    return _array_to_b64(blended)


def _encode_mask(mask: np.ndarray) -> str:
    """Converts grayscale mask array → base64 PNG."""
    img = Image.fromarray(mask, mode='L')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')


def _array_to_b64(image: np.ndarray) -> str:
    """Converts BGR numpy array → base64 PNG."""
    success, encoded = cv2.imencode('.png', image)
    if not success:
        raise ValueError("Failed to encode image to PNG")
    return base64.b64encode(encoded.tobytes()).decode('utf-8')


def postprocess(raw_outputs: dict, original_image: np.ndarray) -> dict:
    """
    Master postprocessing function.
    Takes raw model outputs + original image → full structured result dict.
    """
    h, w = original_image.shape[:2]

    abnormality = decode_classification(
        raw_outputs['abnorm_logits'], ABNORMALITY_LABELS
    )
    pathology = decode_classification(
        raw_outputs['path_logits'], PATHOLOGY_LABELS
    )
    segmentation = decode_segmentation(raw_outputs['seg_logits'], (h, w))

    # Build overlay now that we have both mask and original image
    rgb_image = cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB) \
        if len(original_image.shape) == 3 else original_image
    segmentation['overlay_b64'] = build_overlay(rgb_image, segmentation['mask_array'])

    # Clean up — don't send numpy arrays in JSON response
    del segmentation['mask_array']

    return {
        'abnormality':  abnormality,
        'pathology':    pathology,
        'segmentation': segmentation,
    }
