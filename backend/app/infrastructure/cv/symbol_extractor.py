"""OpenCV symbol extraction adapter.

Pipeline (per the spec): grayscale -> threshold -> denoise (morphology) -> contour detection
-> filter/segment -> bbox + crop. ``cv2``/``numpy`` are imported lazily.

The heuristics (area band, aspect ratio, NMS by IoU) are tuned to pull discrete diagram
symbols while rejecting page-scale frames and speckle noise. They are intentionally simple and
swappable: a learned detector can replace this adapter without touching the pipeline (ADR 0004).
"""

from __future__ import annotations

from ...domain.ports import SymbolExtractor
from ...domain.value_objects import BBox

# Fraction-of-page-area band for a plausible symbol, and shape guards.
_MIN_AREA_FRAC = 0.0004
_MAX_AREA_FRAC = 0.20
_MAX_ASPECT = 8.0
_MAX_SYMBOLS_PER_PAGE = 500
_IOU_DEDUPE = 0.6


class OpenCvSymbolExtractor(SymbolExtractor):
    def extract(self, page_png: bytes, page_number: int) -> list[tuple[BBox, bytes]]:
        import cv2
        import numpy as np

        buf = np.frombuffer(page_png, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            return []
        h, w = img.shape[:2]
        page_area = float(h * w)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Invert + Otsu so foreground strokes become white on black.
        _, thresh = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        # Denoise + connect nearby strokes into symbol blobs.
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(
            closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        candidates: list[tuple[float, BBox]] = []
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = float(bw * bh)
            if area < _MIN_AREA_FRAC * page_area or area > _MAX_AREA_FRAC * page_area:
                continue
            aspect = max(bw, bh) / max(1.0, min(bw, bh))
            if aspect > _MAX_ASPECT:
                continue
            candidates.append((area, BBox(float(x), float(y), float(bw), float(bh))))

        # Largest first, then IoU non-max suppression to drop nested/overlapping detections.
        candidates.sort(key=lambda t: t[0], reverse=True)
        kept: list[BBox] = []
        for _area, box in candidates:
            if all(box.iou(k) < _IOU_DEDUPE for k in kept):
                kept.append(box)
            if len(kept) >= _MAX_SYMBOLS_PER_PAGE:
                break

        results: list[tuple[BBox, bytes]] = []
        for box in kept:
            x, y, bw, bh = int(box.x), int(box.y), int(box.width), int(box.height)
            crop = img[y : y + bh, x : x + bw]
            ok, enc = cv2.imencode(".png", crop)
            if ok:
                results.append((box, enc.tobytes()))
        return results
