"""Which backups to keep (D-100): the newest few, and the first of each recent week and month."""

from datetime import date, datetime, timedelta

from taskboard.domain.backups import LIMITS, KeptAs, Retention, kept_backups


def nightly(first: date, last: date, hour: int = 2) -> list[datetime]:
    """One backup each night from `first` to `last`, as the scheduled task makes them."""
    days = (last - first).days
    return [
        datetime(first.year, first.month, first.day, hour) + timedelta(days=d)
        for d in range(days + 1)
    ]


def at(day: str, hour: int = 2) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour)


def test_a_season_of_nightly_backups_keeps_five() -> None:
    """Saturday 10 October 2026, with every night since August: the scheme the owner asked for."""
    kept = kept_backups(nightly(date(2026, 8, 1), date(2026, 10, 10)), Retention())
    assert kept == {
        at("2026-10-10"): [KeptAs.NEWEST],
        at("2026-10-09"): [KeptAs.NEWEST],
        at("2026-10-05"): [KeptAs.WEEKLY],  # Monday: the week's first
        at("2026-10-01"): [KeptAs.MONTHLY],
        at("2026-09-01"): [KeptAs.MONTHLY],
    }


def test_one_backup_can_be_kept_for_every_reason() -> None:
    """Thursday 1 October: the newest backup is also the month's first; Monday is the week's."""
    kept = kept_backups(nightly(date(2026, 9, 1), date(2026, 10, 1)), Retention())
    assert kept == {
        at("2026-10-01"): [KeptAs.NEWEST, KeptAs.MONTHLY],
        at("2026-09-30"): [KeptAs.NEWEST],
        at("2026-09-28"): [KeptAs.WEEKLY],
        at("2026-09-01"): [KeptAs.MONTHLY],
    }
    monday = kept_backups(nightly(date(2026, 9, 1), date(2026, 10, 5)), Retention())
    assert monday[at("2026-10-05")] == [KeptAs.NEWEST, KeptAs.WEEKLY]


def test_the_first_run_counts_when_a_night_was_missed() -> None:
    """The server was down on the 1st and on Monday: the first backup after it stands in."""
    taken = [at("2026-09-30"), at("2026-10-02"), at("2026-10-07"), at("2026-10-08")]
    kept = kept_backups(taken, Retention(newest=2, weekly=1, monthly=1))
    assert kept == {
        at("2026-10-08"): [KeptAs.NEWEST],
        at("2026-10-07"): [KeptAs.NEWEST, KeptAs.WEEKLY],
        at("2026-10-02"): [KeptAs.MONTHLY],
    }


def test_several_backups_on_one_day() -> None:
    """An extra backup before an upgrade: the earlier one of the day is still the week's first."""
    taken = [at("2026-10-05"), at("2026-10-05", 15), at("2026-10-06")]
    kept = kept_backups(taken, Retention(newest=2, weekly=1, monthly=1))
    assert kept[at("2026-10-05")] == [KeptAs.WEEKLY, KeptAs.MONTHLY]
    assert at("2026-10-05", 15) in kept and len(kept) == 3


def test_weeks_and_months_without_backups_do_not_count() -> None:
    """The task stopped in August: two months later, August's and July's backups are still kept."""
    taken = nightly(date(2026, 7, 20), date(2026, 8, 20))
    kept = kept_backups(taken, Retention())
    assert kept == {
        at("2026-08-20"): [KeptAs.NEWEST],
        at("2026-08-19"): [KeptAs.NEWEST],
        at("2026-08-17"): [KeptAs.WEEKLY],
        at("2026-08-01"): [KeptAs.MONTHLY],
        at("2026-07-20"): [KeptAs.MONTHLY],
    }


def test_weeks_run_monday_to_sunday_across_the_new_year() -> None:
    """ISO weeks: 31 December 2026 (a Thursday) and 1 January 2027 share week 53."""
    taken = [at("2026-12-28"), at("2026-12-31"), at("2027-01-01"), at("2027-01-04")]
    kept = kept_backups(taken, Retention(newest=2, weekly=2, monthly=1))
    assert kept == {
        at("2027-01-04"): [KeptAs.NEWEST, KeptAs.WEEKLY],
        at("2027-01-01"): [KeptAs.NEWEST, KeptAs.MONTHLY],
        at("2026-12-28"): [KeptAs.WEEKLY],
    }


def test_few_backups_are_all_kept() -> None:
    assert kept_backups([], Retention()) == {}
    assert kept_backups([at("2026-10-10")], Retention()) == {
        at("2026-10-10"): [KeptAs.NEWEST, KeptAs.WEEKLY, KeptAs.MONTHLY]
    }


def test_limits_keep_older_backups_and_allow_the_defaults() -> None:
    """Even the lowest setting keeps more than the last backup; the defaults are within limits."""
    assert all(1 <= bounds.low < bounds.high for bounds in LIMITS.values())
    assert LIMITS[KeptAs.NEWEST].low >= 2
    defaults = Retention()
    for kind, value in (
        (KeptAs.NEWEST, defaults.newest),
        (KeptAs.WEEKLY, defaults.weekly),
        (KeptAs.MONTHLY, defaults.monthly),
    ):
        assert LIMITS[kind].low <= value <= LIMITS[kind].high
