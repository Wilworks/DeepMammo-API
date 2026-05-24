import cv2
import numpy as np


class MammographyPreprocessor:
    """
    Replicates the exact preprocessing pipeline from the original
    Predictor_mammo.py. Every step must match training exactly —
    the model was trained on images processed this way, so any
    deviation will hurt predictions.

    Pipeline:
        1. Convert to grayscale
        2. CLAHE  — enhances local contrast (same as training)
        3. Otsu threshold → breast mask
        4. XLargestBlob  → keep only the biggest connected region
        5. ApplyMask     → zero out background
        6. Resize to (400, 400)
        7. Normalize to [0, 1]
        8. Convert to 3-channel RGB
        9. ImageNet normalize
        10. → numpy float32 tensor (1, 3, 400, 400)
    """

    INPUT_SIZE   = (400, 400)
    IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    IMAGENET_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def __call__(self, image_bytes: bytes) -> tuple:
        """
        Args:
            image_bytes: raw bytes of uploaded image (PNG/JPG)

        Returns:
            tensor      : float32 numpy (1, 3, 400, 400) ready for ONNX
            original_img: uint8 numpy (H, W, 3) BGR for overlay generation
        """
        original = self._decode(image_bytes)
        gray     = self._to_grayscale(original)
        clahe    = self._apply_clahe(gray)
        mask     = self._otsu_mask(clahe)
        mask     = self._largest_blob(mask)
        masked   = self._apply_mask(clahe, mask)
        resized  = cv2.resize(masked, self.INPUT_SIZE)
        tensor   = self._to_tensor(resized)
        return tensor, original

    # ── private helpers ──────────────────────────────────────────────

    def _decode(self, image_bytes: bytes) -> np.ndarray:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image. Ensure it is PNG or JPG.")
        return img

    def _to_grayscale(self, img: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def _apply_clahe(self, gray: np.ndarray) -> np.ndarray:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _otsu_mask(self, gray: np.ndarray) -> np.ndarray:
        _, mask = cv2.threshold(
            gray, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        # Morphological cleanup — remove small noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel, iterations=2)
        return mask

    def _largest_blob(self, mask: np.ndarray) -> np.ndarray:
        """Keep only the single largest connected component (the breast)."""
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )
        if num_labels <= 1:
            return mask
        # stats[:, cv2.CC_STAT_AREA] gives area of each component
        # component 0 is background, so start from 1
        largest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        clean_mask = np.zeros_like(mask)
        clean_mask[labels == largest] = 255
        return clean_mask

    def _apply_mask(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        return cv2.bitwise_and(image, image, mask=mask)

    def _to_tensor(self, gray: np.ndarray) -> np.ndarray:
        """
        gray (400,400) uint8
        → float32 (400,400) in [0,1]
        → RGB (400,400,3)
        → ImageNet normalised
        → (1, 3, 400, 400) channel-first for ONNX
        """
        normalized = gray.astype(np.float32) / 255.0
        rgb        = np.stack([normalized] * 3, axis=-1)        # (400,400,3)
        rgb        = (rgb - self.IMAGENET_MEAN) / self.IMAGENET_STD
        chw        = rgb.transpose(2, 0, 1)                     # (3,400,400)
        return chw[np.newaxis, ...].astype(np.float32)          # (1,3,400,400)
