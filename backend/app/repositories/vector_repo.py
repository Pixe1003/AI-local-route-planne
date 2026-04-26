from app.schemas.poi import PoiDetail


class VectorRepository:
    """Lightweight local semantic scorer with the same boundary as a Chroma adapter."""

    def score(self, poi: PoiDetail, persona_tags: list[str], free_text: str | None) -> float:
        text = " ".join([poi.name, poi.category, *poi.tags, *poi.suitable_for, *poi.atmosphere])
        score = 0.0
        for tag in persona_tags:
            if tag in text:
                score += 0.18
        if free_text:
            for keyword in ["拍照", "咖啡", "排队", "晚餐", "情侣", "安静", "文艺", "夜景"]:
                if keyword in free_text and keyword in text:
                    score += 0.12
        if "低排队" in poi.tags:
            score += 0.08
        return min(score, 1.0)
