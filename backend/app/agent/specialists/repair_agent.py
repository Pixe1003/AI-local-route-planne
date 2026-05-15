import re

from pydantic import BaseModel, Field


class FeedbackIntent(BaseModel):
    raw_message: str
    intent_type: str
    event_type: str
    target_stop_index: int | None = None
    category_hint: str | None = None
    budget_per_person: int | None = None
    deltas: dict[str, object] = Field(default_factory=dict)


class RepairAgent:
    def parse(self, message: str) -> FeedbackIntent:
        deltas: dict[str, object] = {}
        target_stop_index = self._target_stop_index(message)
        if target_stop_index is not None:
            deltas["target_stop_index"] = target_stop_index

        category_hint = self._category_hint(message)
        if category_hint:
            deltas["category_hint"] = category_hint

        budget = self._budget(message)
        if budget is not None:
            deltas["budget_per_person"] = budget

        intent_type = "modify_route"
        event_type = "USER_MODIFY_CONSTRAINT"
        if any(keyword in message for keyword in ["换", "替换", "改成"]):
            intent_type = "replace_stop"
            event_type = "REPLACE_POI"
        elif any(keyword in message for keyword in ["预算", "便宜", "省钱"]):
            intent_type = "budget_replan"
            event_type = "BUDGET_EXCEEDED"
        elif any(keyword in message for keyword in ["下雨", "雨天", "室内"]):
            intent_type = "weather_replan"
            event_type = "WEATHER_CHANGED"
        elif any(keyword in message for keyword in ["少排队", "不排队", "排队少"]):
            intent_type = "avoid_queue"
            event_type = "USER_REJECT_POI"

        return FeedbackIntent(
            raw_message=message,
            intent_type=intent_type,
            event_type=event_type,
            target_stop_index=target_stop_index,
            category_hint=category_hint,
            budget_per_person=budget,
            deltas=deltas,
        )

    def _target_stop_index(self, message: str) -> int | None:
        mapping = {"第一": 0, "第1": 0, "第二": 1, "第2": 1, "第三": 2, "第3": 2, "第四": 3, "第4": 3}
        for keyword, index in mapping.items():
            if keyword in message:
                return index
        match = re.search(r"(\d+)\s*站", message)
        if match:
            return max(int(match.group(1)) - 1, 0)
        return None

    def _category_hint(self, message: str) -> str | None:
        if "火锅" in message:
            return "hotpot"
        if any(keyword in message for keyword in ["咖啡", "咖啡馆", "茶"]):
            return "cafe"
        if any(keyword in message for keyword in ["本地菜", "餐", "吃"]):
            return "restaurant"
        if any(keyword in message for keyword in ["夜景", "酒吧", "夜市"]):
            return "nightlife"
        if any(keyword in message for keyword in ["展", "博物馆", "文艺"]):
            return "culture"
        return None

    def _budget(self, message: str) -> int | None:
        match = re.search(r"(?:预算|人均|到|改到)\D{0,4}(\d{2,4})", message)
        if match:
            return int(match.group(1))
        return None
