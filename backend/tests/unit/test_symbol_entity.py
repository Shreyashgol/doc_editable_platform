from uuid import uuid4

from app.domain.entities import Symbol
from app.domain.enums import ClassificationMethod, SymbolType
from app.domain.value_objects import BBox, Classification


def _symbol() -> Symbol:
    return Symbol(
        document_id=uuid4(),
        page_number=1,
        bbox=BBox(0, 0, 10, 10),
        crop_uri="crops/s.png",
    )


def test_apply_classification_updates_type_and_provenance():
    s = _symbol()
    s.apply_classification(
        Classification(
            symbol_type=SymbolType.VALVE,
            method=ClassificationMethod.RULE,
            confidence=0.95,
            raw_class="XV",
        )
    )
    assert s.symbol_type is SymbolType.VALVE
    assert s.classification_method is ClassificationMethod.RULE
    assert s.classification_confidence == 0.95


def test_edit_geometry_snapshots_prior_state_and_bumps_version():
    s = _symbol()
    user = uuid4()
    prior = s.edit_geometry(bbox=BBox(5, 5, 20, 20), rotation=450, changed_by=user, reason="move")
    # returned version captures the state *before* the edit
    assert prior.version == 1
    assert prior.snapshot["bbox"] == {"x": 0, "y": 0, "width": 10, "height": 10}
    # entity now reflects the edit, rotation normalised mod 360
    assert s.version == 2
    assert s.bbox == BBox(5, 5, 20, 20)
    assert s.rotation == 90.0
    assert prior.changed_by == user


def test_assign_label_and_embedding():
    s = _symbol()
    s.assign_label("XV-200")
    s.set_embedding([0.1, 0.2, 0.3])
    assert s.label == "XV-200"
    assert s.embedding == [0.1, 0.2, 0.3]


def test_snapshot_includes_properties():
    s = _symbol()
    snap = s.snapshot()
    assert snap["symbol_type"] == SymbolType.UNKNOWN.value
    assert snap["properties"] == []
