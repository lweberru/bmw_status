"""Pure vehicle presentation building for BMW Status."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any


@dataclass(frozen=True, slots=True)
class EntitySnapshot:
    """The Home Assistant state needed for presentation selection."""

    entity_id: str
    state: str
    name: str
    device_class: str | None = None
    unit: str | None = None
    attributes: dict[str, Any] | None = None

    @property
    def domain(self) -> str:
        """Return the Home Assistant entity domain."""
        return self.entity_id.partition(".")[0]

    @property
    def search_text(self) -> str:
        """Return normalized entity metadata for deterministic matching."""
        return _normalize(f"{self.entity_id} {self.name} {self.device_class or ''}")


def build_presentation(
    vehicle: dict[str, str | None],
    entities: list[EntitySnapshot],
) -> dict[str, Any]:
    """Build a serializable BMW presentation without Home Assistant side effects."""
    used: set[str] = set()
    lock = _pick(entities, used, ("lock", "binary_sensor", "sensor"), ("lock", "locked", "verriegelt"))
    charging = _pick(
        entities,
        used,
        ("binary_sensor", "sensor"),
        ("charging", "charging status", "connector", "plug", "laden", "ladekabel"),
    )
    battery_charge = _pick(
        entities,
        used,
        ("sensor",),
        ("state of charge", "state_of_charge", "soc", "state of energy", "ladezustand"),
    )
    fuel = _pick(
        entities,
        used,
        ("sensor",),
        ("fuel level", "fuel_level", "remaining fuel", "tank", "kraftstoff"),
    )
    electric_range = _pick(
        entities,
        used,
        ("sensor",),
        ("electric range", "electric_range", "remaining electric range", "ev range"),
    )
    total_range = _pick(
        entities,
        used,
        ("sensor",),
        ("remaining range", "remaining_range", "total range", "range", "reichweite"),
    )
    odometer = _pick(
        entities,
        used,
        ("sensor",),
        ("travelled distance", "travelled_distance", "odometer", "mileage", "kilometerstand"),
    )
    motion = _pick(
        entities,
        used,
        ("binary_sensor", "sensor"),
        ("vehicle ismoving", "vehicle motion state", "vehicle_motion_state", "motion state", "motion_state"),
    )
    doors = _pick_many(
        entities,
        used,
        ("binary_sensor", "sensor", "cover"),
        ("door", "window", "trunk", "tailgate", "hood", "sunroof", "fenster", "tür"),
    )
    tires = _pick_many(
        entities,
        used,
        ("sensor",),
        ("tire pressure", "tire_pressure", "tyre pressure", "reifendruck"),
    )
    service = _pick_many(
        entities,
        used,
        ("sensor", "binary_sensor"),
        ("condition based service", "check control", "fault memory", "maintenance", "service"),
    )
    climate = _pick_many(
        entities,
        used,
        ("sensor", "binary_sensor", "switch", "climate"),
        ("preconditioning", "climatization", "climate", "hvac", "defrost", "standklima"),
    )
    tracker = _pick(entities, used, ("device_tracker",), ())

    electrification = _detect_electrification(battery_charge, charging, electric_range, fuel)
    status = _vehicle_status(motion)

    return {
        "vehicle": vehicle,
        "status": status,
        "electrification": electrification,
        "entities": {
            "lock": _entity_data(lock),
            "charging": _entity_data(charging),
            "battery_charge": _entity_data(battery_charge),
            "fuel": _entity_data(fuel),
            "electric_range": _entity_data(electric_range),
            "total_range": _entity_data(total_range),
            "odometer": _entity_data(odometer),
            "motion": _entity_data(motion),
            "device_tracker": _entity_data(tracker),
        },
        "groups": {
            "doors": [_group_entity_data(entity, "doors") for entity in doors],
            "tires": [_group_entity_data(entity, "tires") for entity in tires],
            "service": [_group_entity_data(entity, "service") for entity in service],
            "climate": [_group_entity_data(entity, "climate") for entity in climate],
        },
        "badges": _build_badges(fuel, tires, doors, status["key"]),
        "images": [],
    }


def _pick(
    entities: list[EntitySnapshot],
    used: set[str],
    domains: tuple[str, ...],
    keywords: tuple[str, ...],
) -> EntitySnapshot | None:
    """Pick the best unused entity matching a domain and keyword set."""
    candidates = _matches(entities, used, domains, keywords)
    if not candidates:
        return None
    selected = candidates[0]
    used.add(selected.entity_id)
    return selected


def _pick_many(
    entities: list[EntitySnapshot],
    used: set[str],
    domains: tuple[str, ...],
    keywords: tuple[str, ...],
) -> list[EntitySnapshot]:
    """Pick all matching unused entities in a stable order."""
    selected = _matches(entities, used, domains, keywords)
    used.update(entity.entity_id for entity in selected)
    return selected


def _matches(
    entities: list[EntitySnapshot],
    used: set[str],
    domains: tuple[str, ...],
    keywords: tuple[str, ...],
) -> list[EntitySnapshot]:
    """Return stable ranked matches, preferring available entities."""
    normalized_keywords = tuple(_normalize(keyword) for keyword in keywords)
    candidates = [
        entity
        for entity in entities
        if entity.entity_id not in used
        and entity.domain in domains
        and (not normalized_keywords or any(keyword in entity.search_text for keyword in normalized_keywords))
    ]
    return sorted(candidates, key=lambda entity: (_is_unavailable(entity.state), entity.name, entity.entity_id))


def _entity_data(entity: EntitySnapshot | None) -> dict[str, str] | None:
    """Return the serializable representation consumed by the frontend."""
    if not entity:
        return None
    data = {"entity_id": entity.entity_id, "name": entity.name, "state": entity.state}
    if entity.unit:
        data["unit"] = entity.unit
    return data


def _group_entity_data(entity: EntitySnapshot, group: str) -> dict[str, str]:
    """Add rendering metadata for a presentation group without exposing heuristics."""
    data = _entity_data(entity)
    assert data is not None
    search_text = entity.search_text
    if group == "tires":
        position = _tire_position(search_text)
        data["label"] = f"Reifendruck {position}"
        data["position"] = position
        data["role"] = "target" if _is_tire_target(search_text) else "actual"
    else:
        data["label"] = _group_label(group, search_text, entity.name)
    return data


def _tire_position(search_text: str) -> str:
    """Return the stable human-readable wheel position."""
    front = "front" in search_text or "vorne" in search_text
    rear = "rear" in search_text or "hinten" in search_text
    left = "left" in search_text or "fahrer" in search_text or "links" in search_text
    right = "right" in search_text or "passenger" in search_text or "rechts" in search_text
    axle = "Vorne" if front else "Hinten" if rear else ""
    side = "links" if left else "rechts" if right else ""
    return f"{axle} {side}".strip() or "Unbekannt"


def _is_tire_target(search_text: str) -> bool:
    """Identify a configured tire-pressure target."""
    return any(token in search_text for token in ("target", "soll", "recommended", "reference"))


def _group_label(group: str, search_text: str, fallback: str) -> str:
    """Translate known CarData signal families to concise German titles."""
    if group == "doors":
        if "front driver" in search_text or "front left" in search_text:
            return "Fahrertür" if "door" in search_text else "Fenster vorne links"
        if "front passenger" in search_text or "front right" in search_text:
            return "Beifahrertür" if "door" in search_text else "Fenster vorne rechts"
        if "rear driver" in search_text or "rear left" in search_text:
            return "Hintertür links" if "door" in search_text else "Fenster hinten links"
        if "rear passenger" in search_text or "rear right" in search_text:
            return "Hintertür rechts" if "door" in search_text else "Fenster hinten rechts"
        if "tailgate" in search_text or "trunk" in search_text:
            return "Heckklappe"
        if "hood" in search_text:
            return "Motorhaube"
        if "sunroof" in search_text:
            return "Schiebedach"
        if "doors overall" in search_text:
            return "Türen"
    if group == "climate":
        if "preconditioning" in search_text or "climatization" in search_text:
            return "Vorklimatisierung"
        if "defrost" in search_text:
            return "Entfrosten"
        if "timer" in search_text:
            return "Klimazeitplan"
    if group == "service":
        if "check control" in search_text:
            return "Check-Control"
        if "fault memory" in search_text:
            return "Fehlerspeicher"
        if "condition based service" in search_text:
            return "Wartungsbedarf"
    return fallback


def _detect_electrification(
    battery_charge: EntitySnapshot | None,
    charging: EntitySnapshot | None,
    electric_range: EntitySnapshot | None,
    fuel: EntitySnapshot | None,
) -> str:
    """Classify the vehicle with the available CarData signals."""
    electric = any((battery_charge, charging, electric_range))
    if electric and fuel:
        return "phev"
    if electric:
        return "bev"
    return "ice"


def _vehicle_status(motion: EntitySnapshot | None) -> dict[str, str | None]:
    """Map CarData motion state to the stable presentation vocabulary."""
    if not motion or _is_unavailable(motion.state):
        return {"key": "unknown", "label": "Unbekannt", "entity_id": motion.entity_id if motion else None}
    state = _normalize(motion.state)
    if state in {"on", "true", "1", "yes"} or "driving" in state or "moving" in state:
        return {"key": "driving", "label": "Fährt", "entity_id": motion.entity_id}
    if state in {"off", "false", "0", "no"} or "park" in state or "standing" in state:
        return {"key": "parked", "label": "Geparkt", "entity_id": motion.entity_id}
    return {"key": "unknown", "label": motion.state, "entity_id": motion.entity_id}


def _build_badges(
    fuel: EntitySnapshot | None,
    tires: list[EntitySnapshot],
    doors: list[EntitySnapshot],
    status: str,
) -> list[dict[str, str]]:
    """Build the first semantic warning badges without rendering decisions."""
    badges: list[dict[str, str]] = []
    if fuel and _number(fuel.state) is not None:
        threshold = 15 if fuel.unit == "%" else 10
        if 0 < _number(fuel.state) <= threshold:
            badges.append({"key": "low_fuel", "label": "Tank niedrig", "level": "warning"})
    if status == "parked" and any(_is_open(entity.state) for entity in doors):
        badges.append({"key": "openings", "label": "Öffnungen offen", "level": "warning"})
    if any((_number(entity.state) or 0) < 200 for entity in tires):
        badges.append({"key": "tire_pressure", "label": "Reifendruck niedrig", "level": "alert"})
    return badges


def _normalize(value: str) -> str:
    """Normalize arbitrary entity data for keyword comparisons."""
    decomposed = unicodedata.normalize("NFD", value.lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def _is_unavailable(value: str) -> bool:
    """Identify states that must not win entity selection."""
    return _normalize(value) in {"", "unknown", "unavailable", "none"}


def _is_open(value: str) -> bool:
    """Recognize an opening state across common CarData values."""
    return _normalize(value) in {"on", "true", "1", "yes", "open", "opened"}


def _number(value: str) -> float | None:
    """Convert a localized numeric state when possible."""
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None