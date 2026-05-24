from app.schemas.poi import PoiDetail


SYNONYMS = {
    "老人": ["老人", "长辈", "父母", "爸妈", "senior"],
    "散步": ["散步", "走走", "慢慢逛", "步道", "平缓"],
    "雨天": ["雨天", "下雨", "室内", "避雨"],
    "拍照": ["拍照", "出片", "打卡", "photogenic"],
    "低排队": ["少排队", "不排队", "低排队", "排队短"],
    "安静": ["安静", "清静", "不吵", "relaxed"],
    "咖啡": ["咖啡", "休息", "下午茶"],
    "本地菜": ["本地菜", "徽菜", "安徽菜", "本地口味"],
}


class VectorRepository:
    """Lightweight local semantic scorer with the same boundary as a Chroma adapter."""

    def score(self, poi: PoiDetail, persona_tags: list[str], free_text: str | None) -> float:
        text = " ".join(
            [
                poi.name,
                poi.category,
                poi.sub_category or "",
                *poi.tags,
                *poi.suitable_for,
                *poi.atmosphere,
                *[str(item.get("keyword", "")) for item in poi.high_freq_keywords],
            ]
        )
        score = 0.0
        for tag in persona_tags:
            if tag in text:
                score += 0.18
        if free_text:
            for canonical, words in SYNONYMS.items():
                query_hit = any(word in free_text for word in words)
                poi_hit = any(word in text for word in [canonical, *words])
                if query_hit and poi_hit:
                    score += 0.12
            for item in poi.high_freq_keywords:
                keyword = str(item.get("keyword", ""))
                if keyword and keyword in free_text:
                    score += 0.08
        if "低排队" in poi.tags:
            score += 0.08
        return min(score, 1.0)
