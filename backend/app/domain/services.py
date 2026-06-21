"""Pure domain services — stateless algorithms over domain objects, no I/O.

These are unit-tested directly. Keeping them framework-free is what lets us verify the core
intelligence of the platform (label association, geometry) deterministically.
"""

from __future__ import annotations

from uuid import UUID

from .entities import Symbol
from .value_objects import OcrToken


def associate_text_to_symbol(
    symbols: list[Symbol],
    tokens: list[OcrToken],
    *,
    max_distance: float,
    min_confidence: float = 0.5,
) -> dict[UUID, OcrToken]:
    """Nearest-neighbour association of OCR tokens to symbols.

    For each symbol we pick the highest-confidence token whose centroid is closest to the
    symbol centroid, within ``max_distance``. A token is assigned to at most one symbol
    (the nearest), preventing one label being claimed by several symbols.

    Returns a mapping of ``symbol.id -> chosen token``. Symbols with no match are absent.
    """
    candidates = [t for t in tokens if t.confidence >= min_confidence]
    # Build all (distance, symbol, token) triples within range, then greedily assign by
    # ascending distance so the closest pairings win and tokens are not double-used.
    triples: list[tuple[float, int, int]] = []
    for si, symbol in enumerate(symbols):
        for ti, token in enumerate(candidates):
            dist = symbol.bbox.distance_to(token.centroid)
            if dist <= max_distance:
                triples.append((dist, si, ti))
    triples.sort(key=lambda t: t[0])

    assigned_symbols: set[int] = set()
    assigned_tokens: set[int] = set()
    result: dict[UUID, OcrToken] = {}
    for _dist, si, ti in triples:
        if si in assigned_symbols or ti in assigned_tokens:
            continue
        assigned_symbols.add(si)
        assigned_tokens.add(ti)
        result[symbols[si].id] = candidates[ti]
    return result


def deduplicate_candidates_iou(
    boxes: list,  # list[SymbolCandidate]
    *,
    iou_threshold: float = 0.6,
) -> list:
    """Non-maximum-suppression-style dedupe: drop candidates that overlap an already-kept
    box above ``iou_threshold``. Keeps the first occurrence (callers pass largest-first).
    """
    kept: list = []
    for cand in boxes:
        if all(cand.bbox.iou(k.bbox) < iou_threshold for k in kept):
            kept.append(cand)
    return kept
