"""The static freshness check: an output port must not promise fresher data than its inputs deliver.

dpb never looks at data. It compares the freshness of an output port with the longest gap in the schedule of each
source input port of the same data product, and with the freshness of each output port the data product reads.
"""

from collections.abc import Iterator
from datetime import date, timedelta
from functools import cache

from datapatchbay.crosschecks import find_other_output
from datapatchbay.models import OutputPortFile, SourceInputPortFile
from datapatchbay.problems import Problem
from datapatchbay.repomodel import DataProduct, Repo
from datapatchbay.schedule import CRON_FIELDS, duration_minutes, expand_cron_field, format_minutes

_DAY_MINUTES = 1440
# Eight years from a leap year hold two leap days, so a schedule on 29 February still has a gap to measure.
_HORIZON_START = date(2024, 1, 1)
_HORIZON_DAYS = 2922


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
    minutes = sorted(expand_cron_field(minute_f, CRON_FIELDS[0]))
    hours = sorted(expand_cron_field(hour_f, CRON_FIELDS[1]))
    doms = expand_cron_field(dom_f, CRON_FIELDS[2])
    months = expand_cron_field(month_f, CRON_FIELDS[3])
    dows = {d % 7 for d in expand_cron_field(dow_f, CRON_FIELDS[4])}
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
            upstream = find_other_output(repo, dataproduct, port.reads_port) if port.reads_port else None
            if upstream is None or upstream == "unreadable" or not isinstance(upstream.file.model, OutputPortFile):
                continue
            upstream_freshness = upstream.file.model.freshness
            if upstream_freshness is not None and promised < duration_minutes(upstream_freshness):
                yield Problem(
                    output.file.path,
                    line,
                    f"output port '{output.name}' promises freshness {model.freshness}, but the output port "
                    f"'{upstream.name}' that it reads (input port '{port.name}') promises only {upstream_freshness}",
                )
