from uuid import uuid4

from app.domain.entities import Symbol
from app.domain.services import associate_text_to_symbol, deduplicate_candidates_iou
from app.domain.value_objects import BBox, OcrToken, SymbolCandidate


def _symbol(x: float, y: float) -> Symbol:
    return Symbol(
        document_id=uuid4(),
        page_number=1,
        bbox=BBox(x, y, 10, 10),
        crop_uri="crops/x.png",
    )


def _token(text: str, x: float, y: float, conf: float = 0.9) -> OcrToken:
    return OcrToken(text=text, bbox=BBox(x, y, 8, 4), confidence=conf)


def test_nearest_token_is_associated():
    s = _symbol(0, 0)  # centroid (5,5)
    near = _token("XV-200", 4, 4)  # centroid (8,6) -> close
    far = _token("PT-100", 500, 500)
    result = associate_text_to_symbol([s], [near, far], max_distance=20)
    assert result[s.id].text == "XV-200"


def test_low_confidence_tokens_ignored():
    s = _symbol(0, 0)
    weak = _token("noise", 4, 4, conf=0.2)
    result = associate_text_to_symbol([s], [weak], max_distance=50, min_confidence=0.5)
    assert s.id not in result


def test_token_not_double_assigned():
    s1 = _symbol(0, 0)  # centroid (5,5)
    s2 = _symbol(6, 0)  # centroid (11,5)
    token = _token("LBL", 3, 0)  # centroid (7,2): closer to s1
    result = associate_text_to_symbol([s1, s2], [token], max_distance=50)
    assert s1.id in result and s2.id not in result
    assert result[s1.id].text == "LBL"


def test_out_of_range_not_associated():
    s = _symbol(0, 0)
    token = _token("X", 100, 100)
    result = associate_text_to_symbol([s], [token], max_distance=10)
    assert result == {}


def test_dedupe_iou_drops_overlaps():
    big = SymbolCandidate(1, BBox(0, 0, 100, 100), "a")
    overlap = SymbolCandidate(1, BBox(5, 5, 100, 100), "b")  # high IoU with big
    distinct = SymbolCandidate(1, BBox(500, 500, 20, 20), "c")
    kept = deduplicate_candidates_iou([big, overlap, distinct], iou_threshold=0.5)
    assert big in kept and distinct in kept and overlap not in kept
