from datetime import datetime, timezone

from app.repositories.poi_repo import get_poi_repository
from app.schemas.chat import ChatResponse, ChatTurn
from app.schemas.plan import RefinedPlan, RefinedStop, UgcSnippet
from app.services.state import PLAN_REGISTRY
from app.services.ugc_service import UgcService


class ChatService:
    def __init__(self) -> None:
        self.repo = get_poi_repository()
        self.ugc_service = UgcService()

    def adjust_plan(
        self,
        plan_id: str,
        user_message: str,
        chat_history: list[ChatTurn],
    ) -> ChatResponse:
        plan = PLAN_REGISTRY.get(plan_id)
        if plan is None:
            return ChatResponse(
                intent_type="unknown",
                updated_plan=None,
                assistant_message="没有找到当前方案，请先重新生成路线。",
                requires_confirmation=False,
            )
        intent_type = self._detect_intent(user_message)
        updated = plan.model_copy(deep=True)
        if intent_type == "replace_poi":
            updated = self._replace_stop(updated, user_message)
            message = "已帮你把目标站点换成排队压力更低的选择。"
        elif intent_type == "add_poi":
            updated = self._add_cafe(updated)
            message = "已在路线中加入一个咖啡休息点，并保留原有主线。"
        elif intent_type == "remove_poi":
            updated.stops = updated.stops[:-1] if len(updated.stops) > 3 else updated.stops
            updated.summary.poi_count = len(updated.stops)
            message = "已压缩路线，保留最关键的站点。"
        elif intent_type == "compress_time":
            updated.stops = updated.stops[: max(3, len(updated.stops) - 1)]
            updated.summary.poi_count = len(updated.stops)
            updated.summary.total_duration_min = max(120, updated.summary.total_duration_min - 60)
            message = "已缩短路线，优先保留高匹配站点。"
        else:
            message = "我先按当前方案保留，如果要换站点可以说“把第二站换成不排队的”。"
        PLAN_REGISTRY[updated.plan_id] = updated
        return ChatResponse(
            intent_type=intent_type,
            updated_plan=updated,
            assistant_message=message,
            requires_confirmation=False,
        )

    def _detect_intent(self, message: str) -> str:
        if "换" in message or "替换" in message:
            return "replace_poi"
        if "加" in message or "增加" in message:
            return "add_poi"
        if "删" in message or "跳过" in message:
            return "remove_poi"
        if "快" in message or "压缩" in message or "赶" in message:
            return "compress_time"
        return "unknown"

    def _replace_stop(self, plan: RefinedPlan, message: str) -> RefinedPlan:
        index = 1 if ("第二" in message or "2" in message) and len(plan.stops) > 1 else 0
        existing_ids = {stop.poi_id for stop in plan.stops}
        old_stop = plan.stops[index]
        replacement = self.repo.find_replacement(
            exclude_ids=existing_ids,
            category_hint=old_stop.category,
            avoid_queue="不排队" in message or "排队" in message,
        )
        if replacement is None:
            return plan
        plan.stops[index] = RefinedStop(
            poi_id=replacement.id,
            poi_name=replacement.name,
            arrival_time=old_stop.arrival_time,
            departure_time=old_stop.departure_time,
            why_this_one=f"{replacement.name}排队预估更低，适合作为替换站点。",
            ugc_evidence=self.ugc_service.get_highlight_quotes(replacement.id, [], 2),
            risk_warning=None,
            transport_to_next=old_stop.transport_to_next,
            latitude=replacement.latitude,
            longitude=replacement.longitude,
            category=replacement.category,
        )
        plan.summary.tradeoffs = ["替换后通勤顺序保持不变，精确交通时间建议现场再刷新一次。"]
        return plan

    def _add_cafe(self, plan: RefinedPlan) -> RefinedPlan:
        existing_ids = {stop.poi_id for stop in plan.stops}
        cafe = self.repo.find_replacement(exclude_ids=existing_ids, category_hint="cafe", avoid_queue=True)
        if cafe is None:
            return plan
        insert_at = min(1, len(plan.stops))
        anchor = plan.stops[insert_at - 1] if plan.stops else None
        arrival = anchor.departure_time if anchor else "15:00"
        new_stop = RefinedStop(
            poi_id=cafe.id,
            poi_name=cafe.name,
            arrival_time=arrival,
            departure_time=arrival,
            why_this_one=f"{cafe.name}适合补充咖啡休息，不会明显增加排队风险。",
            ugc_evidence=[
                UgcSnippet(quote=f"{cafe.name}适合临时休息，下午更安静。", source="dianping")
            ],
            risk_warning=None,
            transport_to_next=None,
            latitude=cafe.latitude,
            longitude=cafe.longitude,
            category=cafe.category,
        )
        plan.stops.insert(insert_at, new_stop)
        plan.summary.poi_count = len(plan.stops)
        plan.summary.total_cost += cafe.price_per_person or 0
        plan.summary.tradeoffs = ["加入咖啡后总时长略增，后续站点建议顺延。"]
        return plan
