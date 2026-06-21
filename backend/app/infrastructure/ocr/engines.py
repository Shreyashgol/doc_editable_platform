"""OCR adapters: PaddleOCR (production, lazy) and a no-op engine for ML-free environments."""

from __future__ import annotations

from ...domain.ports import OcrEngine
from ...domain.value_objects import BBox, OcrToken


class NoOpOcrEngine(OcrEngine):
    """Returns no tokens. Used when ocr_backend=none; symbols simply stay unlabelled."""

    def extract_text(self, page_png: bytes) -> list[OcrToken]:
        return []


class PaddleOcrEngine(OcrEngine):  # pragma: no cover - heavy ML dependency
    def __init__(self, *, lang: str = "en", min_confidence: float = 0.5) -> None:
        self._lang = lang
        self._min_confidence = min_confidence
        self._ocr = None

    def _ensure_loaded(self) -> None:
        if self._ocr is not None:
            return
        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(use_angle_cls=True, lang=self._lang, show_log=False)

    def extract_text(self, page_png: bytes) -> list[OcrToken]:
        import cv2
        import numpy as np

        self._ensure_loaded()
        buf = np.frombuffer(page_png, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            return []
        raw = self._ocr.ocr(img, cls=True)
        tokens: list[OcrToken] = []
        for line in raw or []:
            for box, (text, conf) in line or []:
                if conf < self._min_confidence:
                    continue
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                x, y = min(xs), min(ys)
                w, h = max(xs) - x, max(ys) - y
                if w <= 0 or h <= 0:
                    continue
                tokens.append(
                    OcrToken(
                        text=text,
                        bbox=BBox(float(x), float(y), float(w), float(h)),
                        confidence=float(conf),
                    )
                )
        return tokens
