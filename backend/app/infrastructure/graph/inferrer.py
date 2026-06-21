"""Proximity-based relationship inferrer (Phase-1 graph construction).

Connects spatially adjacent symbols on the same page and assigns an edge type from the source
symbol's role (e.g. a Pump 'feeds', a Controller 'controls', a Transmitter 'measures'). This is
a deliberately simple, deterministic heuristic; a learned/edge-detection inferrer implements the
same ``RelationshipInferrer`` port later without pipeline changes.
"""

from __future__ import annotations

from ...domain.entities import Relationship, Symbol
from ...domain.enums import RelationshipType, SymbolType
from ...domain.ports import RelationshipInferrer

_TYPE_TO_RELATION: dict[SymbolType, RelationshipType] = {
    SymbolType.PUMP: RelationshipType.FEEDS,
    SymbolType.COMPRESSOR: RelationshipType.FEEDS,
    SymbolType.CONTROLLER: RelationshipType.CONTROLS,
    SymbolType.PRESSURE_TRANSMITTER: RelationshipType.MEASURES,
    SymbolType.INSTRUMENT: RelationshipType.MEASURES,
    SymbolType.VALVE: RelationshipType.REGULATES,
}


class ProximityRelationshipInferrer(RelationshipInferrer):
    def __init__(self, *, confidence_scale: float = 600.0) -> None:
        # Distance (in render pixels) at which edge confidence decays to ~0; tuning knob only,
        # it does not gate edge creation. A learned inferrer would replace this entirely.
        self._scale = confidence_scale

    def infer(self, symbols: list[Symbol]) -> list[Relationship]:
        edges: list[Relationship] = []
        seen: set[tuple] = set()
        by_page: dict[int, list[Symbol]] = {}
        for s in symbols:
            by_page.setdefault(s.page_number, []).append(s)

        for page_symbols in by_page.values():
            if len(page_symbols) < 2:
                continue
            for src in page_symbols:
                rel_type = _TYPE_TO_RELATION.get(src.symbol_type)
                if rel_type is None:
                    continue
                # Connect each role-bearing symbol to its nearest neighbour on the page.
                nearest: Symbol | None = None
                nearest_dist = float("inf")
                for dst in page_symbols:
                    if dst.id == src.id:
                        continue
                    dist = src.bbox.distance_to(dst.centroid)
                    if dist < nearest_dist:
                        nearest, nearest_dist = dst, dist
                if nearest is None:
                    continue
                key = (src.id, nearest.id)
                if key in seen:
                    continue
                seen.add(key)
                confidence = max(0.1, 1.0 - nearest_dist / self._scale)
                edges.append(
                    Relationship(
                        document_id=src.document_id,
                        source_symbol_id=src.id,
                        target_symbol_id=nearest.id,
                        type=rel_type,
                        confidence=round(confidence, 3),
                    )
                )
        return edges
