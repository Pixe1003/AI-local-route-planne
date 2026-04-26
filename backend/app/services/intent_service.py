from app.schemas.plan import HardConstraints, PlanContext, SoftPreferences, StructuredIntent


class IntentService:
    def parse_intent(
        self,
        user_id: str,
        selected_poi_ids: list[str],
        free_text: str | None,
        context: PlanContext,
    ) -> StructuredIntent:
        text = free_text or ""
        avoid_queue = any(word in text for word in ["不排队", "少排队", "排队太久"])
        photography = any(word in text for word in ["拍照", "打卡", "情侣"])
        food = any(word in text for word in ["吃", "饭", "晚餐", "美食", "探店"])
        pace = "relaxed" if any(word in text for word in ["松弛", "轻松", "慢"]) else "balanced"
        if any(word in text for word in ["多逛", "高效", "打卡"]):
            pace = "efficient"
        budget_total = context.budget_per_person
        if budget_total is not None:
            budget_total *= 2 if context.party == "couple" else 1
        return StructuredIntent(
            hard_constraints=HardConstraints(
                start_time=context.time_window.start,
                end_time=context.time_window.end,
                budget_total=budget_total,
                transport_mode="mixed",
                must_include_meal=food,
            ),
            soft_preferences=SoftPreferences(
                pace=pace,
                avoid_queue=avoid_queue,
                weather_sensitive=False,
                photography_priority=photography or context.party == "couple",
                food_diversity=food,
                custom_notes=[text] if text else [],
            ),
            must_visit_pois=selected_poi_ids,
            avoid_pois=[],
        )
