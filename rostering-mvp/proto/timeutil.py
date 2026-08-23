"""Time helpers. All times are integer minutes from the start of the horizon
(day 0, 00:00 local). One day = 1440 minutes.
"""
from typing import Tuple

DAY = 1440


def hms(total_min: int) -> str:
    """Format a horizon-minute offset as 'D+HH:MM' (D = day offset)."""
    d, rem = divmod(int(total_min), DAY)
    h, m = divmod(rem, 60)
    return f"D{d}+{h:02d}:{m:02d}"


def tod(minutes_of_day: int) -> str:
    """Format minutes-of-day as HH:MM."""
    h, m = divmod(int(minutes_of_day) % DAY, 60)
    return f"{h:02d}:{m:02d}"


def hm(day: int, hour: int, minute: int = 0) -> int:
    """Build an absolute horizon minute from day + hour + minute."""
    return day * DAY + hour * 60 + minute


def local(absolute_min: int) -> Tuple[int, int, int]:
    """Split absolute minute into (day, hour, minute-of-day)."""
    d, rem = divmod(int(absolute_min), DAY)
    return d, rem // 60, rem % 60