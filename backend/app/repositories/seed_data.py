from datetime import date

from app.schemas.poi import HighlightQuote, PoiDetail


OPEN_HOURS = {
    "monday": [{"open": "10:00", "close": "22:00"}],
    "tuesday": [{"open": "10:00", "close": "22:00"}],
    "wednesday": [{"open": "10:00", "close": "22:00"}],
    "thursday": [{"open": "10:00", "close": "22:00"}],
    "friday": [{"open": "10:00", "close": "23:00"}],
    "saturday": [{"open": "09:00", "close": "23:00"}],
    "sunday": [{"open": "09:00", "close": "22:00"}],
}

CATEGORY_FIXTURES = {
    "restaurant": [
        "淮海路本帮菜馆",
        "巨鹿路小酒馆",
        "新天地融合料理",
        "愚园路面馆",
        "静安寺素食餐厅",
        "外滩江景餐厅",
        "陕西南路火锅局",
    ],
    "cafe": [
        "武康路花园咖啡",
        "永康路手冲咖啡",
        "衡山路露台咖啡",
        "安福路书店咖啡",
        "徐家汇安静咖啡",
        "苏河湾河畔咖啡",
        "复兴公园早午茶",
    ],
    "scenic": [
        "外滩观景步道",
        "豫园九曲桥",
        "陆家嘴滨江",
        "武康大楼",
        "上海中心观光厅",
        "思南公馆街区",
        "苏州河步道",
    ],
    "culture": [
        "上海博物馆东馆",
        "当代艺术博物馆",
        "上生新所展厅",
        "朵云书院旗舰店",
        "上海影城电影展",
        "油罐艺术中心",
        "衡复风貌馆",
    ],
    "shopping": [
        "TX淮海年轻力中心",
        "静安嘉里中心",
        "前滩太古里",
        "南京西路买手店",
        "大学路创意市集",
        "K11艺术购物中心",
        "环贸iapm",
    ],
    "outdoor": [
        "复兴公园",
        "徐汇滨江绿地",
        "世纪公园",
        "静安雕塑公园",
        "黄浦滨江跑道",
        "襄阳公园",
        "长风公园",
    ],
    "entertainment": [
        "人民广场脱口秀",
        "新天地Livehouse",
        "徐家汇密室剧场",
        "南京西路桌游馆",
        "衡山路爵士现场",
        "上剧场小剧场",
        "世博源沉浸剧",
    ],
    "nightlife": [
        "巨鹿路精酿酒吧",
        "外滩夜景露台",
        "衡山路鸡尾酒吧",
        "新天地夜色街区",
        "苏河湾夜游码头",
        "安福路小酒馆",
        "大学路夜市",
    ],
}

CATEGORY_TAGS = {
    "restaurant": ["美食", "晚餐", "本地口味", "foodie"],
    "cafe": ["咖啡", "安静", "休息", "photogenic"],
    "scenic": ["打卡", "地标", "拍照", "couple"],
    "culture": ["展览", "文艺", "雨天友好", "literary"],
    "shopping": ["逛街", "潮流", "室内", "friends"],
    "outdoor": ["散步", "松弛", "低预算", "solo"],
    "entertainment": ["互动", "朋友聚会", "夜晚", "friends"],
    "nightlife": ["夜景", "小酌", "氛围", "couple"],
}


def _make_poi(index: int, category: str, name: str) -> PoiDetail:
    lat = 31.205 + (index % 9) * 0.012
    lng = 121.425 + (index % 11) * 0.014
    queue = 8 + (index * 7) % 55
    rating = round(4.2 + ((index * 13) % 8) / 10, 1)
    price = 35 + ((index * 29) % 260)
    tags = CATEGORY_TAGS[category] + (["低排队"] if queue <= 20 else ["热门"])
    suitable = ["couple", "friends"]
    if category in {"culture", "cafe", "scenic"}:
        suitable.append("photographer")
    if category in {"restaurant", "cafe"}:
        suitable.append("foodie")
    return PoiDetail(
        id=f"sh_poi_{index:03d}",
        name=name,
        city="shanghai",
        category=category,
        sub_category=tags[0],
        address=f"上海市核心城区 {name}",
        latitude=lat,
        longitude=lng,
        rating=rating,
        price_per_person=price,
        open_hours=OPEN_HOURS,
        tags=tags,
        cover_image=f"https://picsum.photos/seed/{index}/640/420",
        review_count=120 + index * 17,
        queue_estimate={"weekday_peak": max(5, queue - 12), "weekend_peak": queue},
        visit_duration=55 if category in {"restaurant", "culture"} else 40,
        best_time_slots=["weekend_afternoon", "weekday_evening"],
        avoid_time_slots=["weekend_noon"] if queue > 35 else [],
        highlight_quotes=[
            HighlightQuote(
                quote=f"{name}适合慢慢逛，下午人会少一些。",
                source="dianping",
                review_date=date(2025, 9, min(28, 1 + index % 26)),
                category="time_recommendation",
            ),
            HighlightQuote(
                quote=f"这里的{tags[0]}体验很稳定，拍照和休息都方便。",
                source="xiaohongshu",
                review_date=date(2025, 10, min(28, 1 + index % 24)),
                category="general_praise",
            ),
        ],
        high_freq_keywords=[
            {"keyword": tags[0], "count": 80 + index},
            {"keyword": "位置方便", "count": 60 + index},
        ],
        hidden_menu=["靠窗位", "下午低峰"] if category in {"restaurant", "cafe"} else [],
        avoid_tips=["周末饭点排队较久"] if queue > 35 else ["非高峰到店体验更好"],
        suitable_for=suitable,
        atmosphere=["photogenic", "relaxed"] if category in {"cafe", "scenic"} else ["lively"],
    )


def load_seed_pois() -> list[PoiDetail]:
    pois: list[PoiDetail] = []
    index = 1
    for category, names in CATEGORY_FIXTURES.items():
        for name in names:
            pois.append(_make_poi(index, category, name))
            index += 1
    return pois
