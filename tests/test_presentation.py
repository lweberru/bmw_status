"""Tests for the pure BMW Status presentation contract."""

from custom_components.bmw_status.presentation import EntitySnapshot, build_presentation


VEHICLE = {"name": "Test BMW", "vin": "TESTVIN"}


def snapshot(entity_id: str, state: str, name: str, unit: str | None = None) -> EntitySnapshot:
    """Create a concise entity snapshot for presentation tests."""
    return EntitySnapshot(entity_id=entity_id, state=state, name=name, unit=unit)


def test_build_presentation_for_phev_includes_status_and_warnings():
    """PHEV signals are selected without confusing charge level and charging state."""
    presentation = build_presentation(
        VEHICLE,
        [
            snapshot("sensor.bmw_state_of_charge", "67", "State of Charge", "%"),
            snapshot("binary_sensor.bmw_charging_status", "off", "Charging Status"),
            snapshot("sensor.bmw_remaining_fuel", "8", "Remaining Fuel", "L"),
            snapshot("binary_sensor.bmw_vehicle_motion_state", "off", "Vehicle Motion State"),
            snapshot("binary_sensor.bmw_driver_door", "on", "Driver Door"),
            snapshot("sensor.bmw_tire_pressure_front_left", "190", "Tire Pressure Front Left", "kPa"),
            snapshot("sensor.bmw_travelled_distance", "12345", "Travelled Distance", "km"),
        ],
    )

    assert presentation["electrification"] == "phev"
    assert presentation["status"]["key"] == "parked"
    assert presentation["entities"]["battery_charge"]["entity_id"] == "sensor.bmw_state_of_charge"
    assert presentation["entities"]["charging"]["entity_id"] == "binary_sensor.bmw_charging_status"
    assert {badge["key"] for badge in presentation["badges"]} == {"low_fuel", "openings", "tire_pressure"}


def test_build_presentation_classifies_bev_and_ice():
    """Electrification remains semantic when only electric or fuel signals exist."""
    bev = build_presentation(
        VEHICLE,
        [snapshot("sensor.bmw_state_of_charge", "80", "State of Charge", "%")],
    )
    ice = build_presentation(
        VEHICLE,
        [snapshot("sensor.bmw_remaining_fuel", "45", "Remaining Fuel", "L")],
    )

    assert bev["electrification"] == "bev"
    assert ice["electrification"] == "ice"


def test_build_presentation_includes_mild_hybrid_trip_charge_and_tracker_altitude():
    """Mildhybrid charge and current GPS altitude remain linked to their source entities."""
    tracker = EntitySnapshot(
        entity_id="device_tracker.bmw_320d_xdrive",
        state="not_home",
        name="BMW 320d xDrive",
        attributes={"latitude": 48.1, "longitude": 11.5, "gps_altitude": 524.6, "gps_altitude_unit": "m"},
    )
    presentation = build_presentation(
        VEHICLE,
        [
            snapshot("sensor.320d_xdrive_trip_battery_charge_level_at_end_of_trip", "68", "Trip Battery charge level at end of trip", "%"),
            snapshot("sensor.320d_xdrive_remaining_fuel", "45", "Remaining Fuel", "%"),
            tracker,
        ],
    )

    assert presentation["electrification"] == "mhev"
    assert presentation["entities"]["mild_hybrid_battery_charge"]["entity_id"] == "sensor.320d_xdrive_trip_battery_charge_level_at_end_of_trip"
    assert presentation["entities"]["altitude"] == {
        "entity_id": tracker.entity_id,
        "name": "GPS altitude",
        "state": "524.6",
        "unit": "m",
    }


def test_build_presentation_adds_semantic_tire_metadata():
    """The frontend receives wheel position and actual-versus-target roles."""
    presentation = build_presentation(
        VEHICLE,
        [
            snapshot("sensor.bmw_tire_pressure_front_left", "250", "Tire Pressure Front Left", "kPa"),
            snapshot("sensor.bmw_tire_pressure_target_front_left", "230", "Tire Pressure Target Front Left", "kPa"),
        ],
    )

    actual, target = presentation["groups"]["tires"]
    assert actual["label"] == "Reifendruck Vorne links"
    assert actual["position"] == "Vorne links"
    assert actual["role"] == "actual"
    assert target["role"] == "target"