"""Durations and cron expressions: what is valid and what it means. The file models and the freshness check share it."""

import re
from typing import NamedTuple

DURATION = re.compile(r"[1-9][0-9]*[mhd]")
_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440}
_ATOM = re.compile(r"(?P<first>[0-9]+|[a-z]+)(-(?P<last>[0-9]+|[a-z]+))?")


class CronField(NamedTuple):
    """One of the five fields of a cron expression.

    Attributes:
        name: How a message calls the field.
        low: The lowest value.
        high: The highest value.
        names: The names accepted instead of numbers, in order.
        name_offset: The value of the first name.
    """

    name: str
    low: int
    high: int
    names: tuple[str, ...] = ()
    name_offset: int = 0


MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
WEEKDAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
CRON_FIELDS = (
    CronField("minute", 0, 59),
    CronField("hour", 0, 23),
    CronField("day of month", 1, 31),
    CronField("month", 1, 12, MONTHS, 1),
    CronField("day of week", 0, 7, WEEKDAYS, 0),
)


def duration_minutes(text: str) -> int:
    """Convert a duration such as `30m`, `24h` or `7d` to minutes. The text is already validated."""
    return int(text[:-1]) * _UNIT_MINUTES[text[-1]]


def format_minutes(minutes: int) -> str:
    """Write minutes as hours when they divide evenly and as minutes otherwise, such as `24h` or `90m`."""
    return f"{minutes // 60}h" if minutes % 60 == 0 else f"{minutes}m"


def _value(token: str, field: CronField) -> int:
    """The number a token stands for.

    Raises:
        ValueError: If the token is neither a number nor a name of the field.
    """
    if token.isdigit():
        return int(token)
    if token not in field.names:
        raise ValueError(f"'{token}' is not a {field.name}")
    return field.names.index(token) + field.name_offset


def is_valid_cron_field(text: str, field: CronField) -> bool:
    """Whether one field of a cron expression is written correctly and stays within the field's range."""
    for part in text.lower().split(","):
        part, _, step = part.partition("/")
        if step and (not step.isdigit() or int(step) == 0):
            return False
        if part == "*":
            continue
        match = _ATOM.fullmatch(part)
        if match is None:
            return False
        for token in (match["first"], match["last"]):
            if token is None:
                continue
            try:
                value = _value(token, field)
            except ValueError:
                return False
            if not field.low <= value <= field.high:
                return False
    return True


def expand_cron_field(text: str, field: CronField) -> frozenset[int]:
    """Expand one validated cron field to the values it matches."""
    values: set[int] = set()
    for part in text.lower().split(","):
        base, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if base == "*":
            first, last = field.low, field.high
        else:
            match = _ATOM.fullmatch(base)
            if match is None:
                raise ValueError(f"'{text}' is not a valid {field.name} field")  # validated when the port file loaded
            first = _value(match["first"], field)
            last = _value(match["last"], field) if match["last"] else (field.high if step_text else first)
        values.update(range(first, last + 1, step))
    return frozenset(values)
