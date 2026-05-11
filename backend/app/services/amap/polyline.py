from app.services.amap.errors import AmapResponseParseError


def parse_amap_polyline(polyline: str) -> list[list[float]]:
    if not polyline:
        return []

    coordinates: list[list[float]] = []
    for index, point in enumerate(polyline.split(";"), start=1):
        parts = point.split(",")
        if len(parts) != 2:
            raise AmapResponseParseError(
                f"Invalid Amap polyline point at position {index}: {point!r}"
            )

        try:
            longitude = float(parts[0])
            latitude = float(parts[1])
        except ValueError as exc:
            raise AmapResponseParseError(
                f"Invalid Amap polyline coordinate at position {index}: {point!r}"
            ) from exc

        coordinates.append([longitude, latitude])

    return coordinates
