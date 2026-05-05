import re

from pydantic import ValidationError

from app.llm.client import LlmClient
from app.schemas.onboarding import (
    BudgetProfile,
    DestinationProfile,
    OnboardingAnalyzeRequest,
    OnboardingAnalyzeResponse,
    OnboardingProfileRequest,
    OnboardingProfileResponse,
    TimeProfile,
    UserNeedProfile,
)


class OnboardingService:
    SLOT_QUESTIONS = {
        "start_location": "你从哪里出发？",
        "time_budget": "你大概有多长时间？",
        "party_type": "这次和谁一起出行？",
        "budget_per_person": "人均预算大概是多少？",
        "preference": "更想吃什么或玩什么？",
    }

    def analyze(self, request: OnboardingAnalyzeRequest) -> OnboardingAnalyzeResponse:
        profile = self._profile_from_text(request.query, request.user_id)
        missing_slots, score = self._score_profile(profile)
        profile.completeness_score = score
        return OnboardingAnalyzeResponse(
            completeness_score=score,
            missing_slots=missing_slots,
            suggested_questions=[self.SLOT_QUESTIONS[slot] for slot in missing_slots],
            can_plan=score >= 0.5,
            should_ask_followup=bool(missing_slots) and score < 0.8,
            extracted_profile=profile,
        )

    def build_profile(self, request: OnboardingProfileRequest) -> OnboardingProfileResponse:
        profile = self._profile_from_text(request.query, request.user_id)
        self._apply_answers(profile, request.answers)
        missing_slots, score = self._score_profile(profile)
        profile.completeness_score = score
        return OnboardingProfileResponse(profile=profile)

    def _profile_from_text(self, query: str, user_id: str) -> UserNeedProfile:
        text = query.strip()
        profile = UserNeedProfile(
            user_id=user_id,
            destination=self._destination_from_text(text),
            time=self._time_from_text(text),
            party_type=self._party_from_text(text),
            budget=self._budget_from_text(text),
            activity_preferences=self._activity_preferences(text),
            food_preferences=self._food_preferences(text),
            route_style=self._route_style(text),
            avoid=self._avoid(text),
            raw_query=text,
        )
        return self._enhance_profile_with_llm(text, profile)

    def _enhance_profile_with_llm(self, text: str, fallback: UserNeedProfile) -> UserNeedProfile:
        prompt = f"""
请将用户输入解析为 UserNeedProfile JSON。仅补充你能从文本中确定的信息，不要编造 POI 或路线。

UserNeedProfile 字段：
- destination.city: 城市英文标识，上海用 shanghai，南京用 nanjing
- destination.start_location: 出发地
- time.start_time/end_time/time_budget_minutes
- activity_preferences: 活动偏好数组
- food_preferences: 美食偏好数组
- party_type: solo/couple/friends/family/senior
- budget.budget_per_person/budget.strict
- route_style: 如 少排队、轻松、雨天室内、省钱
- avoid: 如 长时间排队、长距离步行

用户输入：{text}
"""
        llm_data = LlmClient().complete_json(prompt, fallback.model_dump())
        try:
            merged = self._deep_merge(fallback.model_dump(), llm_data)
            merged["user_id"] = fallback.user_id
            merged["raw_query"] = text
            return UserNeedProfile.model_validate(merged)
        except (TypeError, ValidationError, ValueError):
            return fallback

    def _destination_from_text(self, text: str) -> DestinationProfile:
        city = "shanghai"
        if "南京" in text:
            city = "nanjing"
        elif "上海" in text:
            city = "shanghai"
        start_location = None
        start_match = re.search(r"从([^，,。]+?)出发", text)
        if start_match:
            start_location = start_match.group(1).strip()
        return DestinationProfile(city=city, start_location=start_location)

    def _time_from_text(self, text: str) -> TimeProfile:
        range_match = re.search(r"(\d{1,2}:\d{2})\s*(?:到|-|至)\s*(\d{1,2}:\d{2})", text)
        if range_match:
            return TimeProfile(
                start_time=range_match.group(1),
                end_time=range_match.group(2),
                time_budget_minutes=self._minutes_between(range_match.group(1), range_match.group(2)),
            )
        if "晚上" in text or "夜游" in text:
            return TimeProfile(start_time="18:00", end_time="22:00", time_budget_minutes=240)
        if "下午" in text or "半天" in text:
            return TimeProfile(start_time="13:00", end_time="18:00", time_budget_minutes=300)
        if "2小时" in text or "2 小时" in text:
            return TimeProfile(start_time="13:00", end_time="15:00", time_budget_minutes=120)
        return TimeProfile()

    def _party_from_text(self, text: str) -> str | None:
        if "情侣" in text or "约会" in text:
            return "couple"
        if "亲子" in text or "孩子" in text or "小孩" in text:
            return "family"
        if "老人" in text or "长辈" in text:
            return "senior"
        if "朋友" in text:
            return "friends"
        if "独自" in text or "一个人" in text:
            return "solo"
        return None

    def _budget_from_text(self, text: str) -> BudgetProfile:
        match = re.search(r"(?:人均|预算|每人)\s*(\d{2,4})", text)
        return BudgetProfile(budget_per_person=int(match.group(1))) if match else BudgetProfile()

    def _activity_preferences(self, text: str) -> list[str]:
        preferences: list[str] = []
        for keyword in ["拍照", "打卡", "展览", "博物馆", "夜景", "公园", "逛街", "Citywalk"]:
            if keyword in text:
                preferences.append(keyword)
        if "轻松" in text or "松弛" in text:
            preferences.append("轻松漫游")
        return list(dict.fromkeys(preferences))

    def _food_preferences(self, text: str) -> list[str]:
        preferences: list[str] = []
        if "本地菜" in text or "本地美食" in text:
            preferences.append("本地菜")
        for keyword in ["咖啡", "甜品", "火锅", "小吃", "烧烤"]:
            if keyword in text:
                preferences.append(keyword)
        if any(keyword in text for keyword in ["吃", "饭", "美食"]):
            preferences.append("美食")
        return list(dict.fromkeys(preferences))

    def _route_style(self, text: str) -> list[str]:
        styles: list[str] = []
        if "不想排队" in text or "少排队" in text or "不排队" in text:
            styles.append("少排队")
        if "轻松" in text or "松弛" in text:
            styles.append("轻松")
        if "省钱" in text or "性价比" in text:
            styles.append("省钱")
        if "雨天" in text or "下雨" in text:
            styles.append("雨天室内")
        return styles

    def _avoid(self, text: str) -> list[str]:
        avoid: list[str] = []
        if "不想排队" in text or "少排队" in text or "不排队" in text:
            avoid.append("长时间排队")
        if "少走路" in text or "怕累" in text or "老人" in text:
            avoid.append("长距离步行")
        return avoid

    def _apply_answers(self, profile: UserNeedProfile, answers: dict) -> None:
        if not answers:
            return
        profile.destination.city = answers.get("city", profile.destination.city)
        profile.destination.start_location = answers.get(
            "start_location", profile.destination.start_location
        )
        profile.date = answers.get("date", profile.date)
        profile.time.start_time = answers.get("start_time", profile.time.start_time)
        profile.time.end_time = answers.get("end_time", profile.time.end_time)
        if profile.time.start_time and profile.time.end_time:
            profile.time.time_budget_minutes = self._minutes_between(
                profile.time.start_time, profile.time.end_time
            )
        profile.party_type = answers.get("party_type", profile.party_type)
        if answers.get("budget_per_person") is not None:
            profile.budget.budget_per_person = int(answers["budget_per_person"])
        if answers.get("activity_preferences"):
            profile.activity_preferences = list(answers["activity_preferences"])
        if answers.get("food_preferences"):
            profile.food_preferences = list(answers["food_preferences"])
        if answers.get("route_style"):
            profile.route_style = list(dict.fromkeys(profile.route_style + list(answers["route_style"])))

    def _deep_merge(self, base: dict, override: dict) -> dict:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge(merged[key], value)
            elif value is not None:
                merged[key] = value
        return merged

    def _score_profile(self, profile: UserNeedProfile) -> tuple[list[str], float]:
        missing: list[str] = []
        score = 0.0
        if profile.destination.city:
            score += 0.15
        if profile.destination.start_location:
            score += 0.15
        else:
            missing.append("start_location")
        if profile.time.start_time and profile.time.end_time:
            score += 0.20
        else:
            missing.append("time_budget")
        if profile.activity_preferences or profile.food_preferences:
            score += 0.20
        else:
            missing.append("preference")
        if profile.party_type:
            score += 0.15
        else:
            missing.append("party_type")
        if profile.budget.budget_per_person is not None:
            score += 0.15
        else:
            missing.append("budget_per_person")
        return missing, round(score, 2)

    def _minutes_between(self, start: str, end: str) -> int:
        start_hour, start_minute = [int(part) for part in start.split(":")]
        end_hour, end_minute = [int(part) for part in end.split(":")]
        return max(0, (end_hour * 60 + end_minute) - (start_hour * 60 + start_minute))
