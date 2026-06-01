from typing import Any, Dict, List

from .models import Scenario
from .plan_generator import get_distance, get_route_sequence


def validate_results(scenario: Scenario, results: Dict[str, Any]) -> List[Dict[str, str]]:
    checks: List[Dict[str, str]] = []
    bus_states = results.get("bus_states", {})
    station_rows = results.get("station_timelines", [])

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({
            "Check": name,
            "Status": "PASS" if ok else "FAIL",
            "Detail": detail,
        })

    expected_buses = {bus.id for bus in scenario.buses}
    completed_buses = {
        bus_id for bus_id, state in bus_states.items()
        if state.get("arrival_time") is not None
    }
    missing = sorted(expected_buses - completed_buses)
    add(
        "Every bus reaches destination",
        not missing,
        "All scheduled buses completed" if not missing else f"Missing: {', '.join(missing)}",
    )

    range_errors = []
    order_errors = []
    for bus_id, state in bus_states.items():
        bus = state["bus"]
        sequence = get_route_sequence(scenario.route, bus.direction)
        stops = [state["origin"]] + state["plan"] + [state["destination"]]
        indexes = [sequence.index(stop) for stop in stops]
        if indexes != sorted(indexes):
            order_errors.append(bus_id)

        for start, end in zip(stops, stops[1:]):
            distance = get_distance(scenario.route, start, end, sequence)
            if distance > scenario.physics.battery_range_km:
                range_errors.append(f"{bus_id}: {start}->{end} is {distance} km")

    add(
        "Battery range respected",
        not range_errors,
        "All legs are within range" if not range_errors else "; ".join(range_errors[:5]),
    )
    add(
        "Route order respected",
        not order_errors,
        "All buses move forward on route" if not order_errors else f"Out of order: {', '.join(order_errors)}",
    )

    duration_errors = []
    for state in bus_states.values():
        for charge in state["charges"]:
            duration = charge["charge_end"] - charge["charge_start"]
            if abs(duration - scenario.physics.charge_duration_minutes) > 0.001:
                duration_errors.append(state["bus"].id)
    add(
        "Charging duration fixed",
        not duration_errors,
        f"Every charge is {scenario.physics.charge_duration_minutes} minutes"
        if not duration_errors else f"Bad duration for: {', '.join(duration_errors)}",
    )

    overlap_errors = []
    for station in scenario.stations:
        intervals = []
        for state in bus_states.values():
            for charge in state["charges"]:
                if charge["station"] == station.id:
                    intervals.append((charge["charge_start"], charge["charge_end"], state["bus"].id))
        for idx, interval in enumerate(sorted(intervals)):
            overlapping = [other for other in intervals if interval[0] < other[1] and other[0] < interval[1]]
            if len(overlapping) > station.chargers:
                overlap_errors.append(f"{station.id} around {interval[0]} min")
                break

    add(
        "Charger capacity respected",
        not overlap_errors,
        "No station exceeds configured charger count"
        if not overlap_errors else "; ".join(overlap_errors),
    )

    expected_charge_count = sum(len(state["charges"]) for state in bus_states.values())
    add(
        "Station output complete",
        len(station_rows) == expected_charge_count,
        f"{len(station_rows)} station rows for {expected_charge_count} charge events",
    )

    return checks
