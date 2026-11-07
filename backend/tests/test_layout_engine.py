from app.services import layout_engine as le


def rect(w, h):
    return [(0, 0), (w, 0), (w, h), (0, h)]


def test_autofill_bradvari_roof_matches_report():
    """3.23 x 16.9 m tile roof, Longi 650 Wp landscape -> 14 modules, 3 vertical rails (Aerocompact report)."""
    params = le.FillParams(panel_w_m=1.134, panel_h_m=2.382, setback_m=0.3, gap_x_m=0.02, gap_y_m=0.02, orientation="landscape")
    res = le.auto_fill(rect(3.23, 16.9), [], params)
    assert res.count == 14
    assert len(res.lines) == 1
    assert res.lines[0]["rails"] == 3
    assert res.lines[0]["direction"] == "v"
    assert abs(res.lines[0]["length_m"] - (14 * 1.134 + 13 * 0.02)) < 0.01


def test_autofill_auto_orientation_picks_more_panels():
    params = le.FillParams(panel_w_m=1.134, panel_h_m=2.382, setback_m=0.3, orientation="auto")
    res = le.auto_fill(rect(10, 6), [], params)
    land = le.auto_fill(rect(10, 6), [], le.FillParams(panel_w_m=1.134, panel_h_m=2.382, setback_m=0.3, orientation="landscape"))
    port = le.auto_fill(rect(10, 6), [], le.FillParams(panel_w_m=1.134, panel_h_m=2.382, setback_m=0.3, orientation="portrait"))
    assert res.count == max(land.count, port.count)


def test_obstacle_blocks_panels():
    params = le.FillParams(panel_w_m=1.134, panel_h_m=2.382, setback_m=0.0, orientation="portrait")
    free = le.auto_fill(rect(6, 5), [], params)
    chimney = [(2.5, 2.0), (3.5, 2.0), (3.5, 3.0), (2.5, 3.0)]
    blocked = le.auto_fill(rect(6, 5), [chimney], params)
    assert blocked.count < free.count
    for p in blocked.panels:
        assert not le.polygons_intersect(le.rect_corners(p.x, p.y, p.w, p.h), chimney)


def test_rail_lines_horizontal_rows():
    panels = [{"x": i * 1.154, "y": 0, "w": 1.134, "h": 2.382, "enabled": True} for i in range(10)]
    lines = le.rail_lines(panels, 0.02)
    assert len(lines) == 1
    assert lines[0]["modules"] == 10
    assert lines[0]["rails"] == 2
    assert lines[0]["direction"] == "h"


def test_disabled_panels_are_ignored():
    panels = [{"x": i * 1.154, "y": 0, "w": 1.134, "h": 2.382, "enabled": i != 4} for i in range(10)]
    s = le.summarize(panels, 650, 0.02)
    assert s["count"] == 9
    assert len(s["lines"]) == 2
    assert s["kwp"] == 5.85


def test_polygon_helpers():
    poly = rect(4, 4)
    assert le.polygon_area(poly) == 16
    assert le.point_in_polygon((1, 1), poly)
    assert not le.point_in_polygon((5, 1), poly)
