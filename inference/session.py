import onnxruntime as ort
from django.conf import settings
import numpy as np

_session = None

def get_session():
    """
    Returns the onnxruntime InferenceSession.
    Loads once on first call, reuses forever after.
    This is called a singleton pattern.
    """
    global _session
    if _session is None:
        _session = ort.InferenceSession(
            str(settings.MODEL_PATH),
            providers=['CPUExecutionProvider']
        )
        print(f"[DeepMammo] ONNX session loaded from {settings.MODEL_PATH}")
    return _session


def run_inference(image_tensor: np.ndarray) -> dict:
    """
    Runs the ONNX model on a preprocessed image tensor.

    Args:
        image_tensor: float32 numpy array, shape (1, 3, 400, 400)
                      ImageNet normalised, values roughly in [-2, 2]

    Returns:
        dict with raw numpy outputs:
            seg_logits    → (1, 1, 512, 512)
            abnorm_logits → (1, 2)
            path_logits   → (1, 2)
    """
    session = get_session()

    outputs = session.run(
        None,                          # None = return all outputs
        {'input': image_tensor}        # key must match export input_name
    )

    return {
        'seg_logits':    outputs[0],   # raw float32, apply sigmoid later
        'abnorm_logits': outputs[1],   # raw float32, apply softmax later
        'path_logits':   outputs[2],   # raw float32, apply softmax later
    }
