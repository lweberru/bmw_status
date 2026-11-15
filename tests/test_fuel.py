"""Fuel estimates must survive restarts without inventing historical data."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.bmw_status.fuel import FuelState, FuelTracker
from custom_components.bmw_status.presentation import EntitySnapshot


def sample(tracker, level, distance, *, options=None, time="2026-11-15T12:00:00+01:00", unit="L"):
    return tracker.update(
        EntitySnapshot("sensor.tank", str(level), "Tank", unit=unit),
        EntitySnapshot("sensor.odometer", str(distance), "Odometer", unit="km"),
        options or {"initial_total_liters": 8000},
        datetime.fromisoformat(time),
    )


def test_consumption_refueling_noise_and_restart():
    tracker = FuelTracker()
    options = {"initial_total_liters": 8000, "initial_since_refuel_liters": 10, "initial_since_refuel_km": 125}
    sample(tracker, 40, 100000, options=options)
    result = sample(tracker, 38, 100025, options=options)
    assert result["total"]["liters"] == 8002
    assert result["total"]["distance_km"] == 100025
    assert result["since_refuel"] == {
        "liters": 12, "distance_km": 150, "average_l_per_100km": 8, "incomplete": False,
    }
    assert result["today"]["average_l_per_100km"] == 8
    assert result["today"]["incomplete"]

    tracker = FuelTracker(FuelState.from_dict(tracker.serialize()))
    assert sample(tracker, 38, 100025, options=options) == result
    sample(tracker, 38.5, 100025, options=options)
    assert sample(tracker, 38, 100025, options=options)["total"]["liters"] == 8002

    result = sample(tracker, 50, 100025, options=options)
    assert result["total"]["liters"] == 8002
    assert result["today"]["liters"] == 2
    assert result["last_refuel_liters"] == 12
    assert result["refuel_count"] == 1
    assert result["since_refuel"]["liters"] == 0
    assert result["since_refuel"]["average_l_per_100km"] is None
    assert not result["since_refuel"]["incomplete"]
    result = sample(tracker, 49, 100045, options=options)
    assert result["since_refuel"]["average_l_per_100km"] == 5
    assert result["total"]["liters"] == 8003


def test_missing_baselines_capacity_and_late_configuration():
    tracker = FuelTracker()
    result = sample(tracker, 80, 100, options={"refuel_threshold_liters": 5}, unit="%")
    assert "missing_tank_capacity" in result["issues"]
    assert result["total"]["liters"] is None
    assert result["today"]["liters"] is None
    assert tracker.state.fuel_reference is None

    options = {"tank_capacity_liters": 50}
    result = sample(tracker, 80, 100, options=options, unit="%")
    assert result["remaining_liters"] == 40
    assert result["since_refuel"]["incomplete"]
    sample(tracker, 78, 120, options=options, unit="%")
    result = sample(tracker, 78, 120, options={**options, "initial_total_liters": 8}, unit="%")
    assert result["total"]["liters"] == 9
    assert result["total"]["average_l_per_100km"] == 7.5
    assert result["since_refuel"]["liters"] == 1


def test_day_rollover_uses_local_calendar_and_preserves_other_periods():
    tracker = FuelTracker()
    sample(tracker, 40, 100000, time="2026-11-15T23:00:00+01:00")
    sample(tracker, 39, 100020, time="2026-11-15T23:59:00+01:00")
    result = sample(tracker, 39, 100020, time="2026-11-16T00:00:00+01:00")
    assert result["day"] == "2026-11-16"
    assert result["today"] == {
        "liters": 0, "distance_km": 0, "average_l_per_100km": None, "incomplete": False,
    }
    result = sample(tracker, 38, 100040, time="2026-11-16T00:05:00+01:00")
    assert result["today"]["liters"] == 1
    assert result["today"]["distance_km"] == 20
    assert result["since_refuel"]["liters"] == 2
    assert result["total"]["liters"] == 8002

    # A restart across midnight attributes the unsplittable delta to today.
    tracker = FuelTracker(FuelState.from_dict(tracker.serialize()))
    result = sample(tracker, 37, 100060, time="2026-11-18T09:00:00+01:00")
    assert result["today"]["liters"] == 1
    assert result["today"]["incomplete"]


@pytest.mark.parametrize("invalid", ["unavailable", "unknown", "nan", "inf", "-1"])
def test_invalid_readings_preserve_references(invalid):
    tracker = FuelTracker()
    sample(tracker, 40, 100000)
    result = sample(tracker, invalid, invalid)
    assert result["total"]["liters"] == 8000
    assert "fuel_unavailable" in result["issues"]
    assert "odometer_unavailable" in result["issues"]
    result = sample(tracker, 39, 100020)
    assert result["total"]["liters"] == 8001
    assert result["since_refuel"]["distance_km"] == 20
    assert result["today"]["incomplete"]


def test_capacity_and_source_changes_do_not_create_consumption_or_refuels():
    tracker = FuelTracker()
    sample(tracker, 80, 100000, options={"tank_capacity_liters": 50}, unit="%")
    result = sample(tracker, 80, 100000, options={"tank_capacity_liters": 60}, unit="%")
    assert result["refuel_count"] == 0
    assert result["since_refuel"]["liters"] == 0
    assert "source_changed" in result["issues"]
    result = tracker.update(
        EntitySnapshot("sensor.other_tank", "20", "Tank", unit="L"),
        EntitySnapshot("sensor.other_odometer", "10", "Distance", unit="mi"),
        {"initial_total_liters": 8000},
        datetime(2026, 11, 15, 13, tzinfo=ZoneInfo("Europe/Berlin")),
    )
    assert result["total"]["liters"] == 8000
    assert result["since_refuel"]["distance_km"] == 0


def test_odometer_rollback_is_rejected_and_miles_are_converted():
    tracker = FuelTracker()
    sample(tracker, 40, 100000)
    result = sample(tracker, 39, 99999)
    assert "odometer_decreased" in result["issues"]
    result = sample(tracker, 39, 100020)
    assert result["since_refuel"]["distance_km"] == 20

    tracker = FuelTracker()
    for level, miles in ((40, 100), (39, 110)):
        result = tracker.update(
            EntitySnapshot("sensor.tank", str(level), "Tank", unit="L"),
            EntitySnapshot("sensor.odometer", str(miles), "Distance", unit="mi"),
            {"initial_total_liters": 0},
            datetime.fromisoformat("2026-11-15T12:00:00+01:00"),
        )
    assert result["since_refuel"]["distance_km"] == 16.093
    assert result["total"]["distance_km"] == 177.028


def test_zero_tank_is_valid_but_out_of_range_percent_is_not():
    tracker = FuelTracker()
    sample(tracker, 1, 100, options={"tank_capacity_liters": 50}, unit="%")
    result = sample(tracker, 101, 100, options={"tank_capacity_liters": 50}, unit="%")
    assert result["remaining_liters"] is None
    result = sample(tracker, 0, 110, options={"tank_capacity_liters": 50}, unit="%")
    assert result["remaining_liters"] == 0
    assert result["since_refuel"]["liters"] == 0.5
    assert result["refuel_count"] == 0
