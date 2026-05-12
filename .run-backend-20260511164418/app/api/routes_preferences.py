from fastapi import APIRouter

from app.schemas.preferences import PreferenceSnapshot, PreferenceSnapshotRequest
from app.services.preference_service import PreferenceService

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.post("/snapshot", response_model=PreferenceSnapshot)
def build_preference_snapshot(request: PreferenceSnapshotRequest) -> PreferenceSnapshot:
    return PreferenceService().build_snapshot(request)
