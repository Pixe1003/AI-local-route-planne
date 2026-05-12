from __future__ import annotations
from app.schemas.chat import ChatResponse, ChatTurn
from app.services.pool_service import PoolService
from app.services.route_replanner import ReplanEvent, RouteReplanner
from app.services.state import PLAN_REGISTRY


class ChatService:
    def adjust_recommendations(
        self,
        *,
        pool_id: str | None,
        current_poi_ids: list[str],
        user_message: str,
    ) -> ChatResponse:
        recommended_ids, alternative_ids = PoolService().recommend_route_update(
            pool_id=pool_id,
            current_poi_ids=current_poi_ids,
            feedback_text=user_message,
        )
        intent_type, event_type = self._detect_intent(user_message)
        return ChatResponse(
            intent_type=intent_type,
            updated_plan=None,
            assistant_message=self._recommendation_message(intent_type, recommended_ids),
            requires_confirmation=False,
            event_type=event_type,
            replan_level="poi_recommendation",
            recommended_poi_ids=recommended_ids,
            alternative_poi_ids=alternative_ids,
        )

    def adjust_plan(
        self,
        plan_id: str,
        user_message: str,
        chat_history: list[ChatTurn],
        action_type: str | None = None,
        target_stop_index: int | None = None,
        replacement_poi_id: str | None = None,
    ) -> ChatResponse:
        plan = PLAN_REGISTRY.get(plan_id)
        if plan is None:
            return ChatResponse(
                intent_type="unknown",
                updated_plan=None,
                assistant_message="没有找到当前方案，请先重新生成路线。",
                requires_confirmation=False,
            )
        intent_type, event_type = self._detect_intent(user_message, action_type)
        if event_type == "USER_ASK_WHY":
            return ChatResponse(
                intent_type=intent_type,
                updated_plan=plan,
                assistant_message="这条路线的推荐理由来自每站评分、UGC 高频关键词、收藏偏好和约束校验结果。",
                requires_confirmation=False,
                event_type=event_type,
                replan_level=None,
            )
        response = RouteReplanner().replan(
            plan,
            ReplanEvent(
                event_type=event_type,
                message=user_message,
                target_stop_index=target_stop_index,
                replacement_poi_id=replacement_poi_id,
            ),
        )
        updated = response.plan
        PLAN_REGISTRY[updated.plan_id] = updated
        return ChatResponse(
            intent_type=intent_type,
            updated_plan=updated,
            assistant_message=response.assistant_message,
            requires_confirmation=False,
            event_type=event_type,
            replan_level=response.replan_level,
        )

    def _detect_intent(self, message: str, action_type: str | None = None) -> tuple[str, str]:
        if action_type == "replace_stop":
            return "replace_stop", "REPLACE_WITH_ALTERNATIVE"
        if "为什么" in message or "原因" in message:
            return "ask_why", "USER_ASK_WHY"
        if "下雨" in message or "雨天" in message:
            return "weather_replan", "WEATHER_CHANGED"
        if "省钱" in message or "预算" in message or "便宜" in message:
            return "budget_replan", "BUDGET_EXCEEDED"
        if "快" in message or "压缩" in message or "赶" in message or "只剩" in message:
            return "compress_time", "TIME_DELAYED"
        if "加" in message or "增加" in message:
            return "add_poi", "USER_MODIFY_CONSTRAINT"
        if "删" in message or "跳过" in message:
            return "compress_time", "TIME_DELAYED"
        if "换" in message or "替换" in message or "排队" in message:
            return "replace_poi", "USER_REJECT_POI"
        return "unknown", "USER_MODIFY_CONSTRAINT"

    def _recommendation_message(self, intent_type: str, recommended_ids: list[str]) -> str:
        if intent_type == "weather_replan":
            return f"已按天气反馈更新推荐 POI，并保留 {len(recommended_ids)} 个可重新计算高德路线的点位。"
        if intent_type == "budget_replan":
            return f"已按预算反馈更新推荐 POI，并保留 {len(recommended_ids)} 个可重新计算高德路线的点位。"
        if intent_type == "compress_time":
            return f"已按时间和距离反馈更新推荐 POI，并保留 {len(recommended_ids)} 个可重新计算高德路线的点位。"
        return f"已根据你的反馈更新推荐 POI，并保留 {len(recommended_ids)} 个可重新计算高德路线的点位。"

