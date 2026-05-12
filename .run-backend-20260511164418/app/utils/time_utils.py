from datetime import datetime, timedelta


def parse_hhmm(value: str) -> datetime:
    return datetime(2026, 1, 1, int(value[:2]), int(value[3:5]))


def format_hhmm(value: datetime) -> str:
    return value.strftime("%H:%M")


def minutes_between(start: str, end: str) -> int:
    return int((parse_hhmm(end) - parse_hhmm(start)).total_seconds() // 60)


def add_minutes(value: str, minutes: int) -> str:
    return format_hhmm(parse_hhmm(value) + timedelta(minutes=minutes))
