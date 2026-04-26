class ProfileService:
    def get_profile(self, user_id: str) -> dict:
        return {
            "user_id": user_id,
            "persona_tags": [],
            "pace_preference": "balanced",
            "budget_level": "mid",
            "avoid_categories": [],
        }

    def update_from_tags(self, user_id: str, persona_tags: list[str]) -> None:
        return None

    def update_from_selections(self, user_id: str, selected_poi_ids: list[str]) -> None:
        return None
