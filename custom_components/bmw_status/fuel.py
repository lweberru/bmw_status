"""Persistent, explicitly estimated fuel accounting from tank-level samples."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import math
from typing import Any

from .presentation import EntitySnapshot


def nonnegative_number(value: Any) -> float | None:
    """Accept finite numeric telemetry, including zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


@dataclass
class FuelPeriod:
    liters: float = 0
    distance_km: float = 0


@dataclass
class FuelState:
    started_at: str | None = None
    initial_odometer: float | None = None
    fuel_reference: float | None = None
    odometer: float | None = None
    fuel_source: str | None = None
    distance_source: str | None = None
    total: FuelPeriod = field(default_factory=FuelPeriod)
    since_refuel: FuelPeriod = field(default_factory=FuelPeriod)
    today: FuelPeriod = field(default_factory=FuelPeriod)
    day: str | None = None
    last_refuel_at: str | None = None
    last_refuel_liters: float | None = None
    refuel_count: int = 0
    incomplete: bool = False
    day_incomplete: bool = True
    refuel_incomplete: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FuelState:
        """Restore only this storage version's fields."""
        values = dict(data)
        for key in ("total", "since_refuel", "today"):
            values[key] = FuelPeriod(**values[key])
        return cls(**values)


class FuelTracker:
    """Track decreases against a low-water mark; small rebounds are not fuel."""

    def __init__(self, state: FuelState | None = None) -> None:
        self.state = state or FuelState()

    def serialize(self) -> dict[str, Any]:
        return asdict(self.state)

    def update(
        self,
        fuel: EntitySnapshot | None,
        odometer: EntitySnapshot | None,
        options: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        """Consume a snapshot once and return the additive card contract."""
        state = self.state
        configured_inputs = set(options) - {"refuel_threshold_liters"}
        if fuel is None and not configured_inputs and state.started_at is None:
            return None
        issues: list[str] = []
        capacity = nonnegative_number(options.get("tank_capacity_liters"))
        level = nonnegative_number(fuel.state) if fuel else None
        unit = (fuel.unit or "").lower() if fuel else ""
        if unit == "%":
            if not capacity:
                issues.append("missing_tank_capacity")
                level = None
            elif level is not None:
                level = level * capacity / 100 if level <= 100 else None
        elif unit not in ("l", "liter", "liters", "litre", "litres"):
            level = None
            if fuel:
                issues.append("unsupported_fuel_unit")
        if capacity and level is not None and level > capacity:
            level = None
        if level is None:
            issues.append("fuel_unavailable")

        distance = nonnegative_number(odometer.state) if odometer else None
        distance_unit = (odometer.unit or "").lower() if odometer else ""
        if distance_unit in ("mi", "mile", "miles") and distance is not None:
            distance *= 1.609344
        elif distance_unit != "km":
            distance = None
            if odometer:
                issues.append("unsupported_distance_unit")
        if distance is None:
            issues.append("odometer_unavailable")

        day = now.date().isoformat()
        new_day = state.day != day
        if new_day:
            # There is no midnight telemetry: the next delta belongs to its
            # observation day, not to an invented split across calendar days.
            state.today = FuelPeriod()
            state.day_incomplete = state.started_at is None
            state.day = day

        fuel_source = f"{fuel.entity_id}:{unit}:{capacity if unit == '%' else ''}" if fuel else None
        distance_source = f"{odometer.entity_id}:{distance_unit}" if odometer else None
        changed_fuel = level is not None and state.fuel_source not in (None, fuel_source)
        changed_distance = distance is not None and state.distance_source not in (None, distance_source)
        if changed_fuel or changed_distance:
            issues.append("source_changed")
            state.incomplete = state.day_incomplete = state.refuel_incomplete = True
        if changed_fuel:
            state.fuel_reference = None
        if changed_distance:
            state.odometer = None

        if state.started_at is None and level is not None:
            state.started_at = now.isoformat()
        if state.started_at is not None:
            if level is None or distance is None:
                state.incomplete = state.day_incomplete = state.refuel_incomplete = True
            if distance is not None:
                if state.initial_odometer is None:
                    state.initial_odometer = distance
                if state.odometer is not None and distance < state.odometer:
                    issues.append("odometer_decreased")
                    state.incomplete = state.day_incomplete = state.refuel_incomplete = True
                    distance = None
                else:
                    delta_km = distance - state.odometer if state.odometer is not None else 0
                    if new_day and delta_km:
                        state.day_incomplete = True
                    for period in (state.total, state.since_refuel, state.today):
                        period.distance_km += delta_km
                    state.odometer = distance
                    state.distance_source = distance_source

            if level is not None:
                state.fuel_source = fuel_source
                reference = state.fuel_reference
                threshold = options.get("refuel_threshold_liters", 5.0)
                if reference is None:
                    state.fuel_reference = level
                elif level - reference >= threshold:
                    state.last_refuel_at = now.isoformat()
                    state.last_refuel_liters = level - reference
                    state.refuel_count += 1
                    state.since_refuel = FuelPeriod()
                    state.refuel_incomplete = distance is None
                    state.fuel_reference = level
                elif level < reference:
                    if new_day:
                        state.day_incomplete = True
                    for period in (state.total, state.since_refuel, state.today):
                        period.liters += reference - level
                    state.fuel_reference = level

        seed = nonnegative_number(options.get("initial_total_liters"))
        if seed is None:
            issues.append("missing_initial_total")
        refuel_seed = nonnegative_number(options.get("initial_since_refuel_liters"))
        refuel_km = nonnegative_number(options.get("initial_since_refuel_km"))
        seeded_refuel = refuel_seed is not None and refuel_km is not None
        refuel_liters = state.since_refuel.liters
        refuel_distance = state.since_refuel.distance_km
        if not state.refuel_count and seeded_refuel:
            refuel_liters += refuel_seed
            refuel_distance += refuel_km
        return {
            "method": "tank_level_estimate",
            "issues": issues,
            "started_at": state.started_at,
            "day": state.day,
            "remaining_liters": _rounded(level),
            "last_refuel_at": state.last_refuel_at,
            "last_refuel_liters": _rounded(state.last_refuel_liters),
            "refuel_count": state.refuel_count,
            "total": _period(
                state.total.liters + seed if seed is not None and state.started_at else None,
                state.total.distance_km + state.initial_odometer if state.initial_odometer is not None else None,
                state.incomplete or seed is None,
            ),
            "since_refuel": _period(
                refuel_liters if state.started_at else None,
                refuel_distance if state.initial_odometer is not None else None,
                state.refuel_incomplete if state.refuel_count else not seeded_refuel or state.incomplete,
            ),
            "today": _period(
                state.today.liters if state.started_at else None,
                state.today.distance_km if state.initial_odometer is not None else None,
                state.day_incomplete,
            ),
        }


def _rounded(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _period(liters: float | None, distance: float | None, incomplete: bool) -> dict[str, Any]:
    return {
        "liters": _rounded(liters),
        "distance_km": _rounded(distance),
        "average_l_per_100km": _rounded(liters / distance * 100) if liters is not None and distance else None,
        "incomplete": incomplete,
    }
