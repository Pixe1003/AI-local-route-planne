from pydantic import ValidationError

from app.llm.client import LlmClient
from app.schemas.plan import HardConstraints, PlanContext, SoftPreferences, StructuredIntent
from app.services.agent_skill_registry import get_agent_skill_registry


class IntentService:
    def __init__(self) -> None:
        self.agent_skill = get_agent_skill_registry().get_skill("route_planning")

    def parse_intent(
        self,
        user_id: str,
        selected_poi_ids: list[str],
        free_text: str | None,
        context: PlanContext,
    ) -> StructuredIntent:
        text = free_text or ""
        avoid_queue = any(word in text for word in ["不排队", "少排队", "排队太久"])
        photography = any(word in text for word in ["拍照", "打卡", "情侣", "顺路拍照"])
        food = any(word in text for word in ["吃", "饭", "晚餐", "美食", "探店", "本地菜"])
        pace = "relaxed" if any(word in text for word in ["松弛", "轻松", "不赶"]) else "balanced"
        if any(word in text for word in ["多逛", "高效", "打卡"]):
            pace = "efficient"
        budget_total = context.budget_per_person
        if budget_total is not None and context.party == "couple":
            budget_total *= 2
        strict_budget = any(
            word in text
            for word in ["严格预算", "预算不能超", "不能超预算", "不超过", "控制在", "预算上限", "no expensive", "strict budget"]
        )
        strict_queue = any(word in text for word in ["绝不排队", "不能排队", "不要排队", "不排队", "avoid waiting lines", "no waiting"])
        strict_indoor = any(word in text for word in ["必须室内", "只要室内", "全室内", "不要户外", "indoor only"])
        experience_required = any(
            word in text
            for word in [
                "文化",
                "博物馆",
                "展览",
                "景点",
                "娱乐",
                "夜景",
                "商场",
                "购物",
                "culture",
                "museum",
                "shopping",
                "entertainment",
            ]
        )
        fallback = StructuredIntent(
            hard_constraints=HardConstraints(
                start_time=context.time_window.start,
                end_time=context.time_window.end,
                budget_total=budget_total,
                transport_mode="mixed",
                must_include_meal=food,
                must_include_experience=experience_required,
                strict_budget=strict_budget,
                strict_queue=strict_queue,
                strict_indoor=strict_indoor,
            ),
            soft_preferences=SoftPreferences(
                pace=pace,
                avoid_queue=avoid_queue or strict_queue,
                weather_sensitive=context.weather_condition != "normal" or any(word in text for word in ["下雨", "雨天", "室内", "热", "冷"]),
                photography_priority=photography or context.party == "couple",
                food_diversity=food,
                custom_notes=[text] if text else [],
            ),
            must_visit_pois=selected_poi_ids,
            avoid_pois=[],
        )
        return self._enhance_intent_with_llm(text, context, selected_poi_ids, fallback)

    def _enhance_intent_with_llm(
        self,
        text: str,
        context: PlanContext,
        selected_poi_ids: list[str],
        fallback: StructuredIntent,
    ) -> StructuredIntent:
        prompt = f"""
请将用户输入解析为 StructuredIntent JSON。你只负责理解需求，不要生成路线，不要新增 POI。
StructuredIntent 字段：
- hard_constraints.must_include_meal: 是否必须包含正餐
- soft_preferences.pace: relaxed/balanced/efficient
- soft_preferences.avoid_queue/weather_sensitive/photography_priority/food_diversity
- soft_preferences.custom_notes: 简短证据
- avoid_pois: 用户明确排除的 POI id，无法确定则 []

硬约束 start_time/end_time/budget_total 和 must_visit_pois 由系统上下文决定，不要覆盖。
系统上下文：
city={context.city}
time_window={context.time_window.start}-{context.time_window.end}
party={context.party}
budget_per_person={context.budget_per_person}
selected_poi_ids={selected_poi_ids}

用户输入：{text}
"""
        llm_data = LlmClient().complete_json(
            prompt,
            fallback.model_dump(),
            agent_name="route_planning",
        )
        try:
            merged = fallback.model_dump()
            if isinstance(llm_data.get("soft_preferences"), dict):
                merged["soft_preferences"] = {
                    **merged["soft_preferences"],
                    **llm_data["soft_preferences"],
                }
            if isinstance(llm_data.get("hard_constraints"), dict) and isinstance(
                llm_data["hard_constraints"].get("must_include_meal"), bool
            ):
                merged["hard_constraints"]["must_include_meal"] = llm_data["hard_constraints"][
                    "must_include_meal"
                ]
            if isinstance(llm_data.get("avoid_pois"), list):
                merged["avoid_pois"] = llm_data["avoid_pois"]
            merged["hard_constraints"]["start_time"] = context.time_window.start
            merged["hard_constraints"]["end_time"] = context.time_window.end
            merged["hard_constraints"]["budget_total"] = fallback.hard_constraints.budget_total
            merged["must_visit_pois"] = selected_poi_ids
            return StructuredIntent.model_validate(merged)
        except (TypeError, ValidationError, ValueError):
            return fallback
