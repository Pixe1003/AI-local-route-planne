from typing import Literal


WeatherCondition = Literal["normal", "rainy", "hot", "cold"]


def today_iso() -> str:
    from datetime import date

    return date.today().isoformat()
