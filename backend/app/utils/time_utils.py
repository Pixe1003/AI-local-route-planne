from datetime import datetime, timedelta


def parse_hhmm(value: str) -> datetime:
    return datetime(2026, 1, 1, int(value[:2]), int(value[3:5]))


def format_hhmm(value: datetime) -> str:
    return value.strftime("%H:%M")


def minutes_between(start: str, end: str) -> int:
    start_time = parse_hhmm(start)
    end_time = parse_hhmm(end)
    if end_time < start_time:
        end_time += timedelta(days=1)
    return int((end_time - start_time).total_seconds() // 60)


def add_minutes(value: str, minutes: int) -> str:
    return format_hhmm(parse_hhmm(value) + timedelta(minutes=minutes))
