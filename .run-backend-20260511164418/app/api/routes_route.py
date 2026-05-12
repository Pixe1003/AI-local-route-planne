from __future__ import annotations
from collections.abc import Iterable

from fastapi import APIRouter, HTTPException

from app.repositories.poi_repo import get_poi_repository
from app.schemas.route import (
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONLineString,
    RouteChainRequest,
    RouteChainResponse,
    RoutePoi,
    RouteSegmentSummary,
    RouteStepFeatureProperties,
)
from app.services.amap.client import AmapRouteClient
from app.services.amap.errors import AmapConfigError, AmapResponseParseError, AmapUpstreamError
from app.services.amap.schemas import AmapLngLat, AmapRouteResult


router = APIRouter(prefix="/route", tags=["route"])
SEGMENT_ROUTE_ATTEMPTS = 2


@router.post("/chain", response_model=RouteChainResponse)
def create_route_chain(payload: RouteChainRequest) -> RouteChainResponse:
    route_pois = _resolve_route_pois(payload)
    if len(route_pois) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 POIs are required to build a chained route.",
        )

    client: AmapRouteClient | None = None
    try:
        client = AmapRouteClient()
        return build_route_chain(payload=payload, route_pois=route_pois, client=client)
    except AmapConfigError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Amap route client is not configured. Set AMAP_WEB_SERVICE_KEY or AMAP_KEY.",
                "code": "AMAP_CONFIG_MISSING",
            },
        ) from exc
    except AmapUpstreamError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Amap upstream route service returned an error.",
                "info": exc.info,
                "infocode": exc.infocode,
            },
        ) from exc
    except AmapResponseParseError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "Failed to parse Amap route response."},
        ) from exc
    finally:
        if client is not None:
            client.close()


def build_route_chain(
    *,
    payload: RouteChainRequest,
    route_pois: list[RoutePoi],
    client: AmapRouteClient,
) -> RouteChainResponse:
    total_distance_m = 0.0
    total_duration_s = 0.0
    segments: list[RouteSegmentSummary] = []
    features: list[GeoJSONFeature] = []

    for segment_index, (from_poi, to_poi) in enumerate(_pairwise(route_pois), start=1):
        result = _get_route_with_retry(
            client=client,
            mode=payload.mode,
            origin=AmapLngLat(longitude=from_poi.longitude, latitude=from_poi.latitude),
            destination=AmapLngLat(longitude=to_poi.longitude, latitude=to_poi.latitude),
        )
        segment_duration_s = result.duration_s or 0.0
        total_distance_m += result.distance_m
        total_duration_s += segment_duration_s
        segments.append(
            RouteSegmentSummary(
                segment_index=segment_index,
                from_poi_id=from_poi.id,
                from_poi_name=from_poi.name,
                to_poi_id=to_poi.id,
                to_poi_name=to_poi.name,
                distance_m=result.distance_m,
                duration_s=segment_duration_s,
            )
        )
        features.extend(
            _step_features(
                segment_index=segment_index,
                from_poi=from_poi,
                to_poi=to_poi,
                route_result=result,
            )
        )

    return RouteChainResponse(
        mode=payload.mode,
        ordered_pois=route_pois,
        total_distance_m=total_distance_m,
        total_duration_s=total_duration_s,
        segments=segments,
        geojson=GeoJSONFeatureCollection(features=features),
    )


def _get_route_with_retry(
    *,
    client: AmapRouteClient,
    mode,
    origin: AmapLngLat,
    destination: AmapLngLat,
) -> AmapRouteResult:
    last_error: AmapUpstreamError | None = None
    for _ in range(SEGMENT_ROUTE_ATTEMPTS):
        try:
            return client.get_route(mode=mode, origin=origin, destination=destination)
        except AmapUpstreamError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise AmapUpstreamError(info="Amap route request failed", infocode=None)


def _resolve_route_pois(payload: RouteChainRequest) -> list[RoutePoi]:
    if payload.pois:
        return payload.pois

    repo = get_poi_repository()
    route_pois: list[RoutePoi] = []
    missing_ids: list[str] = []
    for poi_id in payload.poi_ids:
        try:
            poi = repo.get(poi_id)
        except KeyError:
            missing_ids.append(poi_id)
            continue
        route_pois.append(
            RoutePoi(
                id=poi.id,
                name=poi.name,
                longitude=poi.longitude,
                latitude=poi.latitude,
                category=poi.category,
                cover_image=poi.cover_image,
            )
        )

    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Unknown POI ids: {', '.join(missing_ids)}")

    return route_pois


def _step_features(
    *,
    segment_index: int,
    from_poi: RoutePoi,
    to_poi: RoutePoi,
    route_result: AmapRouteResult,
) -> list[GeoJSONFeature]:
    features: list[GeoJSONFeature] = []
    for step_index, step in enumerate(route_result.steps, start=1):
        features.append(
            GeoJSONFeature(
                properties=RouteStepFeatureProperties(
                    segment_index=segment_index,
                    step_index=step_index,
                    from_poi_id=from_poi.id,
                    from_poi_name=from_poi.name,
                    to_poi_id=to_poi.id,
                    to_poi_name=to_poi.name,
                    instruction=step.instruction,
                    road_name=step.road_name,
                    distance_m=step.distance_m,
                    duration_s=step.duration_s,
                ),
                geometry=GeoJSONLineString(coordinates=step.polyline_coordinates),
            )
        )
    return features


def _pairwise(pois: Iterable[RoutePoi]) -> Iterable[tuple[RoutePoi, RoutePoi]]:
    poi_list = list(pois)
    return zip(poi_list, poi_list[1:])

