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

HEFEI_FIXTURES = [
    ("hf_poi_061581", "庐州本地菜馆", "restaurant", "徽菜", "包河区", 31.820, 117.290),
    ("hf_poi_035366", "杏花公园慢行步道", "outdoor", "公园", "庐阳区", 31.870, 117.270),
    ("hf_poi_020889", "安徽博物院新馆", "culture", "博物馆", "蜀山区", 31.838, 117.212),
    ("hf_poi_000086", "罍街小吃集合", "restaurant", "小吃", "包河区", 31.810, 117.300),
    ("hf_poi_083759", "天鹅湖观景平台", "scenic", "景点", "政务区", 31.820, 117.220),
    ("hf_poi_cafe_001", "湖畔安静咖啡", "cafe", "咖啡", "包河区", 31.825, 117.296),
    ("hf_poi_food_002", "蜀山火锅局", "restaurant", "火锅", "蜀山区", 31.850, 117.220),
    ("hf_poi_culture_003", "合柴1972展厅", "culture", "展览", "包河区", 31.795, 117.305),
    ("hf_poi_shop_004", "银泰中心", "shopping", "商场", "庐阳区", 31.865, 117.285),
    ("hf_poi_outdoor_005", "翡翠湖公园", "outdoor", "公园", "经开区", 31.770, 117.210),
    ("hf_poi_fun_006", "滨湖剧场", "entertainment", "剧场", "包河区", 31.755, 117.290),
    ("hf_poi_night_007", "宁国路夜宵街", "nightlife", "夜宵", "包河区", 31.832, 117.300),
    ("hf_poi_food_008", "三河土菜馆", "restaurant", "土菜", "庐阳区", 31.862, 117.278),
    ("hf_poi_cafe_009", "三孝口茶咖", "cafe", "茶咖", "庐阳区", 31.866, 117.273),
    ("hf_poi_scenic_010", "逍遥津公园", "scenic", "公园", "庐阳区", 31.872, 117.292),
    ("hf_poi_culture_011", "包公园历史区", "culture", "历史文化", "包河区", 31.858, 117.295),
    ("hf_poi_shop_012", "之心城", "shopping", "购物中心", "蜀山区", 31.852, 117.237),
    ("hf_poi_food_013", "淮河路徽菜小馆", "restaurant", "徽菜", "庐阳区", 31.866, 117.286),
    ("hf_poi_outdoor_014", "塘西河绿道", "outdoor", "绿道", "包河区", 31.760, 117.308),
    ("hf_poi_fun_015", "合肥脱口秀小剧场", "entertainment", "剧场", "蜀山区", 31.845, 117.238),
    ("hf_poi_night_016", "1912街区小酒馆", "nightlife", "酒吧", "蜀山区", 31.842, 117.230),
    ("hf_poi_food_017", "滨湖徽州菜", "restaurant", "徽菜", "包河区", 31.756, 117.295),
    ("hf_poi_cafe_018", "雨天友好书店咖啡", "cafe", "书店咖啡", "政务区", 31.825, 117.218),
    ("hf_poi_scenic_019", "大蜀山森林公园", "scenic", "森林公园", "蜀山区", 31.856, 117.180),
]


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


def _make_hefei_poi(index: int, fixture: tuple[str, str, str, str, str, float, float]) -> PoiDetail:
    poi_id, name, category, sub_category, district, lat, lng = fixture
    queue = 8 + (index * 5) % 34
    price = None
    tags = CATEGORY_TAGS.get(category, [sub_category]) + [sub_category, district, "hefei"]
    if queue <= 20:
        tags.append("低排队")
    return PoiDetail(
        id=poi_id,
        name=name,
        city="hefei",
        category=category,
        sub_category=sub_category,
        district=district,
        address=f"合肥市{district}{name}",
        latitude=lat,
        longitude=lng,
        rating=round(4.4 + (index % 5) * 0.1, 1),
        price_per_person=price,
        open_hours=OPEN_HOURS,
        tags=list(dict.fromkeys(tags)),
        cover_image=None,
        review_count=180 + index * 23,
        queue_estimate={"weekday_peak": max(5, queue - 8), "weekend_peak": queue},
        visit_duration=60 if category in {"culture", "scenic", "outdoor"} else 50,
        best_time_slots=["weekend_afternoon", "weekday_evening"],
        avoid_time_slots=[],
        highlight_quotes=[
            HighlightQuote(
                quote=f"{name}适合合肥本地路线，{sub_category}体验稳定，排队压力可控。",
                source="seed",
                review_date=date(2025, 10, min(28, 1 + index % 24)),
                category="ugc_review",
            )
        ],
        high_freq_keywords=[
            {"keyword": sub_category, "count": 80 + index},
            {"keyword": district, "count": 50 + index},
        ],
        hidden_menu=[],
        avoid_tips=["真实客流可能变化，出发前建议再次确认。"],
        suitable_for=["friends", "couple"],
        atmosphere=["relaxed", "photogenic"] if category in {"cafe", "scenic", "outdoor"} else ["lively"],
    )


def load_seed_pois() -> list[PoiDetail]:
    pois: list[PoiDetail] = []
    index = 1
    for category, names in CATEGORY_FIXTURES.items():
        for name in names:
            pois.append(_make_poi(index, category, name))
            index += 1
    for hefei_index, fixture in enumerate(HEFEI_FIXTURES, start=1):
        pois.append(_make_hefei_poi(hefei_index, fixture))
    return pois
