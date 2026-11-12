from pathlib import Path

import pytest

from datapatchbay.freshness import duration_minutes, longest_gap_minutes
from datapatchbay.validation import validate_repo


@pytest.mark.parametrize(
    ("text", "minutes"),
    [("30m", 30), ("24h", 1440), ("7d", 10080)],
)
def test_duration_minutes_converts_units(text: str, minutes: int):
    assert duration_minutes(text) == minutes


@pytest.mark.parametrize(
    ("cron", "minutes"),
    [
        ("* * * * *", 1),
        ("*/15 * * * *", 15),
        ("0 5 * * *", 1440),
        ("0 * * * *", 60),
        ("0 6,18 * * *", 720),
        ("0 6,8 * * *", 22 * 60),  # 08:00 to 06:00 next day
        ("30 5 * * 1-5", 3 * 1440),  # Friday to Monday
        ("0 5 * * mon", 7 * 1440),
        ("0 5 * * 7", 7 * 1440),  # 7 is Sunday
        ("0 5 1 * *", 31 * 1440),
        ("0 5 1 jan,jul *", 184 * 1440),  # July to January
        ("0 0 1,15 * *", 17 * 1440),  # 15th to the 1st of a 31-day month
        ("0 0 1 * mon", 7 * 1440),  # day of month OR day of week when both are given
        ("0 0 29 2 *", 1461 * 1440),  # leap days, four years apart
        ("10-20/5 3 * * *", 1440 - 10),  # 03:10, 03:15, 03:20
    ],
)
def test_longest_gap_minutes(cron: str, minutes: int):
    assert longest_gap_minutes(cron) == minutes


# --- through dpb validate -----------------------------------------------------------------------------------------


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _table(name: str) -> str:
    return (
        f"schema_version: 1\nname: {name}\ncolumns:\n  - name: id\n    type: text\n"
        f"build:\n  executor: python\n  entrypoint: src/{name}.py:build\n"
    )


def _make_product(
    root: Path, folder: str, *, freshness: str | None, schedule: str | None = None, reads: str | None = None
) -> None:
    dp = f"dataproducts/{folder}"
    inputs = []
    if schedule is not None:
        inputs.append(f"{folder}_in")
        _write(
            root,
            f"{dp}/inputs/{folder}_in/port.yaml",
            f'schema_version: 1\nkind: table\nsource: ilab\nschedule: "{schedule}"\n',
        )
        _write(root, f"{dp}/inputs/{folder}_in/t_in.yaml", _table("t_in"))
        _write(root, f"{dp}/src/t_in.py", "def build(): ...\n")
    if reads is not None:
        inputs.append(reads)
        _write(root, f"{dp}/inputs/{reads}/port.yaml", f"schema_version: 1\nfrom: {reads}\n")
    fresh = f"freshness: {freshness}\n" if freshness else ""
    readers = "access:\n  readers:\n    - product: sa_reader\n"
    _write(root, f"{dp}/outputs/{folder}/port.yaml", f"schema_version: 1\nkind: table\n{fresh}{readers}")
    _write(root, f"{dp}/outputs/{folder}/t_out.yaml", _table("t_out"))
    _write(root, f"{dp}/src/t_out.py", "def build(): ...\n")
    _write(
        root,
        f"{dp}/dataproduct.yaml",
        f"schema_version: 1\nname: {folder.removeprefix('sa_')}\nkind: source-aligned\nowner: o\ninputs: {inputs}\noutputs: [{folder}]\n",
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    _write(tmp_path, "datapatchbay.yaml", "schema_version: 1\n")
    return tmp_path


def _messages(root: Path) -> list[tuple[str, int | None, str]]:
    return [(str(p.file), p.line, p.message) for p in validate_repo(root).problems]


def test_output_fresher_than_source_schedule_gap_fails_naming_both_ports_and_values(root: Path):
    _make_product(root, "sa_reader", freshness="12h", schedule="0 5 * * *")
    problems = _messages(root)
    assert len(problems) == 1
    file, line, message = problems[0]
    assert (file, line) == ("dataproducts/sa_reader/outputs/sa_reader/port.yaml", 3)
    for text in ("sa_reader", "12h", "sa_reader_in", "24h", "0 5 * * *"):
        assert text in message


def test_output_not_fresher_than_source_schedule_gap_passes(root: Path):
    _make_product(root, "sa_reader", freshness="24h", schedule="0 5 * * *")
    assert _messages(root) == []


def test_weekday_schedule_gap_counts_the_weekend(root: Path):
    _make_product(root, "sa_reader", freshness="48h", schedule="0 5 * * 1-5")
    assert len(_messages(root)) == 1


def test_output_without_freshness_is_not_checked(root: Path):
    _make_product(root, "sa_reader", freshness=None, schedule="0 5 1 * *")
    assert _messages(root) == []


def test_output_fresher_than_a_read_output_port_fails_naming_both_ports_and_values(root: Path):
    _make_product(root, "sa_upstream", freshness="24h")
    _make_product(root, "sa_reader", freshness="1h", reads="sa_upstream")
    problems = _messages(root)
    assert len(problems) == 1
    file, line, message = problems[0]
    assert (file, line) == ("dataproducts/sa_reader/outputs/sa_reader/port.yaml", 3)
    for text in ("sa_reader", "1h", "sa_upstream", "24h"):
        assert text in message


def test_output_as_fresh_as_a_read_output_port_passes(root: Path):
    _make_product(root, "sa_upstream", freshness="24h")
    _make_product(root, "sa_reader", freshness="24h", reads="sa_upstream")
    assert _messages(root) == []


def test_read_output_port_without_freshness_is_not_compared(root: Path):
    _make_product(root, "sa_upstream", freshness=None)
    _make_product(root, "sa_reader", freshness="1h", reads="sa_upstream")
    assert _messages(root) == []
