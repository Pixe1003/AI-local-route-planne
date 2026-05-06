from fastapi import APIRouter, HTTPException

from app.schemas.trip import SaveRouteVersionRequest, TripRecord, TripSummary
from app.services.orchestrator import AgentOrchestrator

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("", response_model=list[TripSummary])
def list_trips(user_id: str = "mock_user") -> list[TripSummary]:
    return AgentOrchestrator().list_trips(user_id)


@router.post("/versions", response_model=TripRecord)
def save_route_version(request: SaveRouteVersionRequest) -> TripRecord:
    try:
        return AgentOrchestrator().save_route_version(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Trip not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{trip_id}", response_model=TripRecord)
def get_trip(trip_id: str) -> TripRecord:
    trip = AgentOrchestrator().get_trip(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip
