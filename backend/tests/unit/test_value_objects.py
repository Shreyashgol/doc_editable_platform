import math

import pytest
from app.domain.value_objects import BBox, Centroid


def test_bbox_area_and_centroid():
    box = BBox(x=10, y=20, width=40, height=60)
    assert box.area == 2400
    assert box.centroid == Centroid(30.0, 50.0)
    assert box.right == 50
    assert box.bottom == 80


@pytest.mark.parametrize(
    "kwargs",
    [
        {"x": 0, "y": 0, "width": 0, "height": 10},
        {"x": 0, "y": 0, "width": 10, "height": -1},
        {"x": -1, "y": 0, "width": 10, "height": 10},
    ],
)
def test_bbox_rejects_invalid_geometry(kwargs):
    with pytest.raises(ValueError):
        BBox(**kwargs)


def test_bbox_iou_identical_is_one():
    a = BBox(0, 0, 10, 10)
    assert a.iou(a) == pytest.approx(1.0)


def test_bbox_iou_disjoint_is_zero():
    a = BBox(0, 0, 10, 10)
    b = BBox(100, 100, 10, 10)
    assert a.iou(b) == 0.0


def test_bbox_iou_half_overlap():
    a = BBox(0, 0, 10, 10)
    b = BBox(5, 0, 10, 10)  # overlap area 50, union 150
    assert a.iou(b) == pytest.approx(50 / 150)


def test_bbox_contains_and_distance():
    box = BBox(0, 0, 10, 10)
    assert box.contains(Centroid(5, 5))
    assert not box.contains(Centroid(50, 50))
    assert box.distance_to(Centroid(5, 5)) == pytest.approx(0.0)
    assert box.distance_to(Centroid(5, 15)) == pytest.approx(10.0)
    assert box.distance_to(Centroid(8, 9)) == pytest.approx(math.hypot(3, 4))


def test_bbox_roundtrip_dict():
    box = BBox(1, 2, 3, 4)
    assert BBox.from_dict(box.to_dict()) == box
