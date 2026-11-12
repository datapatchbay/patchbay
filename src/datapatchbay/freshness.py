"""The static freshness check: an output port must not promise fresher data than its inputs deliver.

dpb never looks at data. It compares the freshness of an output port with the longest gap in the schedule of each
source input port of the same data product, and with the freshness of each output port the data product reads.
"""

import re
from collections.abc import Iterator
from datetime import date, timedelta
from functools import cache

from datapatchbay.models import OutputPortFile, SourceInputPortFile
from datapatchbay.problems import Problem
from datapatchbay.repomodel import DataProduct, Port, Repo

_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440}
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_WEEKDAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
_DAY_MINUTES = 1440
# Eight years from a leap year hold two leap days, so a schedule on 29 February still has a gap to measure.
_HORIZON_START = date(2024, 1, 1)
_HORIZON_DAYS = 2922
_ATOM = re.compile(r"(?P<first>[0-9]+|[a-z]+)(-(?P<last>[0-9]+|[a-z]+))?")


def duration_minutes(text: str) -> int:
    """Convert a duration such as `30m`, `24h` or `7d` to minutes. The text is already validated."""
    return int(text[:-1]) * _UNIT_MINUTES[text[-1]]


def format_minutes(minutes: int) -> str:
    """Write minutes as hours when they divide evenly and as minutes otherwise, such as `24h` or `90m`."""
    return f"{minutes // 60}h" if minutes % 60 == 0 else f"{minutes}m"


def _expand_field(text: str, low: int, high: int, names: tuple[str, ...], name_offset: int) -> frozenset[int]:
    """Expand one validated cron field to the values it matches."""

    def value(token: str) -> int:
        return int(token) if token.isdigit() else names.index(token) + name_offset

    values: set[int] = set()
    for part in text.lower().split(","):
        base, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if base == "*":
            first, last = low, high
        else:
            match = _ATOM.fullmatch(base)
            assert match is not None  # the field was validated when the port file loaded
            first = value(match["first"])
            last = value(match["last"]) if match["last"] else (high if step_text else first)
        values.update(range(first, last + 1, step))
    return frozenset(values)


@cache
def longest_gap_minutes(cron: str) -> int | None:
    """Return the longest interval, in minutes, between two consecutive firings of a cron expression.

    The walk covers eight years from 2024-01-01, which holds every cycle of the calendar including 29 February.
    When both day-of-month and day-of-week are restricted, a day matches if either does (as in Vixie cron).

    Args:
        cron: A validated five-field cron expression.

    Returns:
        The longest gap, or `None` when the expression fires fewer than twice in the walk.
    """
    minute_f, hour_f, dom_f, month_f, dow_f = cron.split()
    minutes = sorted(_expand_field(minute_f, 0, 59, (), 0))
    hours = sorted(_expand_field(hour_f, 0, 23, (), 0))
    doms = _expand_field(dom_f, 1, 31, (), 0)
    months = _expand_field(month_f, 1, 12, _MONTHS, 1)
    dows = {d % 7 for d in _expand_field(dow_f, 0, 7, _WEEKDAYS, 0)}
    both_restricted = not dom_f.startswith("*") and not dow_f.startswith("*")

    times = [hour * 60 + minute for hour in hours for minute in minutes]
    longest = 0
    previous: int | None = None  # minutes since the start of the walk
    for offset in range(_HORIZON_DAYS):
        day = _HORIZON_START + timedelta(days=offset)
        if day.month not in months:
            continue
        dom_ok = day.day in doms
        dow_ok = (day.weekday() + 1) % 7 in dows
        if not (dom_ok or dow_ok if both_restricted else dom_ok and dow_ok):
            continue
        for time_of_day in times:
            moment = offset * _DAY_MINUTES + time_of_day
            if previous is not None:
                longest = max(longest, moment - previous)
            previous = moment
    return longest or None


def check_freshness(repo: Repo) -> list[Problem]:
    """Compare the freshness of every output port with what its inputs can deliver."""
    problems: list[Problem] = []
    for dataproduct in repo.dataproducts:
        problems.extend(_check_dataproduct(repo, dataproduct))
    return problems


def _check_dataproduct(repo: Repo, dataproduct: DataProduct) -> Iterator[Problem]:
    for output in dataproduct.outputs:
        model = output.file.model
        if not isinstance(model, OutputPortFile) or model.freshness is None:
            continue
        promised = duration_minutes(model.freshness)
        line = output.file.line("freshness")
        for port in dataproduct.inputs:
            source = port.file.model
            if isinstance(source, SourceInputPortFile):
                gap = longest_gap_minutes(source.schedule)
                if gap is not None and promised < gap:
                    yield Problem(
                        output.file.path,
                        line,
                        f"output port '{output.name}' promises freshness {model.freshness}, but source input port "
                        f"'{port.name}' delivers with a longest gap of {format_minutes(gap)} "
                        f'(schedule "{source.schedule}")',
                    )
                continue
            upstream = _read_output(repo, dataproduct, port)
            if upstream is None or not isinstance(upstream.file.model, OutputPortFile):
                continue
            upstream_freshness = upstream.file.model.freshness
            if upstream_freshness is not None and promised < duration_minutes(upstream_freshness):
                yield Problem(
                    output.file.path,
                    line,
                    f"output port '{output.name}' promises freshness {model.freshness}, but the output port "
                    f"'{upstream.name}' that it reads (input port '{port.name}') promises only {upstream_freshness}",
                )


def _read_output(repo: Repo, reader: DataProduct, input_port: Port) -> Port | None:
    """Find the output port of another data product that an input port reads, if it loaded."""
    for other in repo.dataproducts:
        if other is reader:
            continue
        for port in other.outputs:
            if port.name == input_port.reads_port:
                return port
    return None
