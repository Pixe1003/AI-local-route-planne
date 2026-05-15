from fastapi import APIRouter

from app.schemas.onboarding import (
    OnboardingAnalyzeRequest,
    OnboardingAnalyzeResponse,
    OnboardingProfileRequest,
    OnboardingProfileResponse,
)
from app.services.onboarding_service import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/analyze", response_model=OnboardingAnalyzeResponse)
def analyze_onboarding(request: OnboardingAnalyzeRequest) -> OnboardingAnalyzeResponse:
    return OnboardingService().analyze(request)


@router.post("/profile", response_model=OnboardingProfileResponse)
def build_profile(request: OnboardingProfileRequest) -> OnboardingProfileResponse:
    return OnboardingService().build_profile(request)
