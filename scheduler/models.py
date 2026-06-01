from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Physics:
    battery_range_km: float
    charge_duration_minutes: int
    speed_kmph: float

@dataclass
class Weights:
    individual_wait: float
    operator_delay: float
    overall_delay: float

@dataclass
class Segment:
    from_stop: str
    to_stop: str
    distance_km: float

@dataclass
class Route:
    stops: List[str]
    segments: List[Segment]

@dataclass
class Station:
    id: str
    chargers: int

@dataclass
class Bus:
    id: str
    operator: str
    direction: str
    departure_time: str  # Format: "HH:MM"

@dataclass
class Scenario:
    id: str
    name: str
    description: str
    physics: Physics
    weights: Weights
    route: Route
    stations: List[Station]
    operators: List[str]
    buses: List[Bus]