import json
from pathlib import Path
from .models import (
    Scenario, Physics, Weights, Route, Segment, Station, Bus
)

def load_scenario(file_path: str) -> Scenario:
    """Reads a scenario JSON file and returns a strongly-typed Scenario object."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {file_path}")

    with open(path, 'r') as f:
        data = json.load(f)

    # Parse nested structures
    physics = Physics(
        battery_range_km=data['physics']['battery_range_km'],
        charge_duration_minutes=data['physics']['charge_duration_minutes'],
        speed_kmph=data['physics']['speed_kmph']
    )

    weights = Weights(
        individual_wait=data['weights']['individual_wait'],
        operator_delay=data['weights']['operator_delay'],
        overall_delay=data['weights']['overall_delay']
    )

    segments = [
        Segment(
            from_stop=seg['from'],
            to_stop=seg['to'],
            distance_km=seg['distance_km']
        ) for seg in data['route']['segments']
    ]

    route = Route(
        stops=data['route']['stops'],
        segments=segments
    )

    stations = [
        Station(id=st['id'], chargers=st['chargers'])
        for st in data['stations']
    ]

    buses = [
        Bus(
            id=b['id'],
            operator=b['operator'],
            direction=b['direction'],
            departure_time=b['departure_time']
        ) for b in data['buses']
    ]

    # Return the fully assembled scenario
    return Scenario(
        id=data['metadata']['id'],
        name=data['metadata']['name'],
        description=data['metadata']['description'],
        physics=physics,
        weights=weights,
        route=route,
        stations=stations,
        operators=data['operators'],
        buses=buses
    )