import pytest

from app.services.amap.errors import AmapResponseParseError
from app.services.amap.polyline import parse_amap_polyline


def test_parse_amap_polyline_returns_coordinates() -> None:
    result = parse_amap_polyline("118.8012,32.0735;118.8020,32.0740")

    assert result == [[118.8012, 32.0735], [118.802, 32.074]]


def test_parse_amap_polyline_returns_empty_list_for_empty_string() -> None:
    assert parse_amap_polyline("") == []


def test_parse_amap_polyline_raises_for_invalid_format() -> None:
    with pytest.raises(AmapResponseParseError, match="Invalid Amap polyline"):
        parse_amap_polyline("118.8012;118.8020,32.0740")
