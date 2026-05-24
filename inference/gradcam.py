import numpy as np
import cv2
import base64


def generate_gradcam(
    seg_logits: np.ndarray,
    original_image: np.ndarray
) -> str:
    """
    Produces a Grad-CAM-style saliency heatmap directly from the
    segmentation probability map output by the ONNX model.

    Why not real Grad-CAM?
    Real Grad-CAM requires gradient backprop through intermediate layers —
    something onnxruntime does not support (it's inference-only).
    Instead we use the segmentation probability map as a spatial attention
    signal. It carries the same semantic information: high values = regions
    the model flagged as abnormal. Visually and clinically equivalent for
    a demo/portfolio context.

    Args:
        seg_logits    : raw (1, 1, 512, 512) float32 from ONNX
        original_image: uint8 BGR numpy array (original upload)

    Returns:
        base64-encoded PNG string of the heatmap overlay
    """
    prob_map = _sigmoid(seg_logits[0, 0])           # (512, 512) float [0,1]

    h, w = original_image.shape[:2]

    # Resize prob map to match original image
    heatmap = cv2.resize(prob_map, (w, h))

    # Normalise to [0, 255] for colormap application
    heatmap_uint8 = (heatmap * 255).astype(np.uint8)

    # Apply JET colormap — blue=low attention, red=high attention
    heatmap_color = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)

    # Convert original to BGR if needed
    if len(original_image.shape) == 2:
        base = cv2.cvtColor(original_image, cv2.COLOR_GRAY2BGR)
    else:
        base = original_image.copy()

    # Blend: 50% original + 50% heatmap
    overlay = cv2.addWeighted(base, 0.5, heatmap_color, 0.5, 0)

    return _array_to_b64(overlay)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _array_to_b64(image: np.ndarray) -> str:
    success, encoded = cv2.imencode('.png', image)
    if not success:
        raise ValueError("Failed to encode GradCAM image")
    return base64.b64encode(encoded.tobytes()).decode('utf-8')
