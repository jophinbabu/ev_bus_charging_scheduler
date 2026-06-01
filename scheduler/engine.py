import heapq
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from .models import Bus, Scenario
from .plan_generator import generate_valid_plans, get_distance, get_route_sequence
from .rules import ScoreContext, evaluate_urgency


class SimulationEngine:
    """Discrete event simulation for the bus charging problem."""

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.time_now = 0.0
        self._event_counter = 0

        self.station_queues: Dict[str, List[Dict[str, Any]]] = {
            s.id: [] for s in scenario.stations
        }
        self.chargers_in_use: Dict[str, int] = {s.id: 0 for s in scenario.stations}
        self.station_capacities: Dict[str, int] = {s.id: s.chargers for s in scenario.stations}

        self.operator_wait_totals: Dict[str, float] = {op: 0.0 for op in scenario.operators}
        self.operator_bus_counts: Dict[str, int] = {op: 0 for op in scenario.operators}
        for bus in scenario.buses:
            self.operator_bus_counts[bus.operator] = self.operator_bus_counts.get(bus.operator, 0) + 1

        self.bus_state: Dict[str, Dict[str, Any]] = {}
        self.station_timelines: List[Dict[str, Any]] = []
        self.events: List[Tuple[float, int, str, Dict[str, Any]]] = []
        self.plan_by_bus: Dict[str, List[str]] = {}
        self.unscheduled_buses: List[Dict[str, str]] = []

    def time_to_minutes(self, hh_mm: str) -> float:
        h, m = map(int, hh_mm.split(":"))
        return h * 60.0 + m

    def minutes_to_time(self, mins: Optional[float]) -> str:
        if mins is None:
            return "-"
        h = int((mins // 60) % 24)
        m = int(round(mins % 60))
        if m == 60:
            h = (h + 1) % 24
            m = 0
        return f"{h:02d}:{m:02d}"

    def travel_minutes(self, bus: Bus, start_stop: str, end_stop: str) -> float:
        sequence = get_route_sequence(self.scenario.route, bus.direction)
        distance = get_distance(self.scenario.route, start_stop, end_stop, sequence)
        return (distance / self.scenario.physics.speed_kmph) * 60.0

    def schedule_event(self, time: float, event_type: str, payload: Dict[str, Any]) -> None:
        self._event_counter += 1
        heapq.heappush(self.events, (time, self._event_counter, event_type, payload))

    def run(self) -> Dict[str, Any]:
        self.plan_by_bus = self.choose_charging_plans()

        for bus in sorted(self.scenario.buses, key=lambda b: (self.time_to_minutes(b.departure_time), b.id)):
            plan = self.plan_by_bus.get(bus.id)
            if not plan:
                self.unscheduled_buses.append({
                    "Bus ID": bus.id,
                    "Reason": "No valid charging plan found",
                })
                continue

            departure_time = self.time_to_minutes(bus.departure_time)
            sequence = get_route_sequence(self.scenario.route, bus.direction)
            origin = sequence[0]
            destination = sequence[-1]

            self.bus_state[bus.id] = {
                "bus": bus,
                "departure_time": departure_time,
                "origin": origin,
                "destination": destination,
                "plan": plan,
                "charges": [],
                "total_wait": 0.0,
                "arrival_time": None,
            }

            first_station = plan[0]
            arrival_time = departure_time + self.travel_minutes(bus, origin, first_station)
            self.schedule_event(arrival_time, "ARRIVE_STATION", {
                "bus": bus,
                "station_id": first_station,
                "previous_stop": origin,
                "plan": plan,
                "plan_index": 0,
                "arrival_time": arrival_time,
            })

        while self.events:
            self.time_now, _, event_type, payload = heapq.heappop(self.events)
            if event_type == "ARRIVE_STATION":
                self.handle_station_arrival(payload)
            elif event_type == "CHARGE_END":
                self.handle_charge_end(payload)
            elif event_type == "ARRIVE_DESTINATION":
                self.handle_destination_arrival(payload)

        bus_timelines = [self.format_bus_row(state) for state in self.bus_state.values()]
        bus_timelines.sort(key=lambda row: (row["Departure Time"], row["Bus ID"]))
        self.station_timelines.sort(key=lambda row: (row["_sort_start"], row["Station"], row["Bus ID"]))
        for row in self.station_timelines:
            row.pop("_sort_start", None)

        return {
            "bus_timelines": bus_timelines,
            "station_timelines": self.station_timelines,
            "unscheduled_buses": self.unscheduled_buses,
            "plans": self.plan_by_bus,
            "bus_states": self.bus_state,
        }

    def choose_charging_plans(self) -> Dict[str, List[str]]:
        """Greedy projected-plan selection using station availability and weights."""
        station_available = {
            station.id: [0.0 for _ in range(station.chargers)]
            for station in self.scenario.stations
        }
        operator_wait_totals = {op: 0.0 for op in self.scenario.operators}
        network_wait_total = 0.0
        chosen: Dict[str, List[str]] = {}

        buses = sorted(self.scenario.buses, key=lambda b: (self.time_to_minutes(b.departure_time), b.id))
        for index, bus in enumerate(buses, start=1):
            valid_plans = generate_valid_plans(
                self.scenario.route,
                bus,
                self.scenario.physics,
                self.scenario.stations,
            )
            if not valid_plans:
                continue

            best_plan: Optional[List[str]] = None
            best_cost: Optional[float] = None
            best_available: Optional[Dict[str, List[float]]] = None
            best_wait = 0.0

            for plan in valid_plans:
                projected_available = deepcopy(station_available)
                projected_wait, _ = self.project_plan(bus, plan, projected_available)
                operator_count = max(1, self.operator_bus_counts.get(bus.operator, 1))
                projected_operator_avg = (
                    operator_wait_totals.get(bus.operator, 0.0) + projected_wait
                ) / operator_count
                projected_network_avg = (network_wait_total + projected_wait) / index

                cost = (
                    self.scenario.weights.individual_wait * projected_wait
                    + self.scenario.weights.operator_delay * projected_operator_avg
                    + self.scenario.weights.overall_delay * projected_network_avg
                    + 0.05 * len(plan)
                )

                tie_breaker = (len(plan), plan)
                best_tie = (len(best_plan), best_plan) if best_plan is not None else None
                if best_cost is None or cost < best_cost or (
                    cost == best_cost and best_tie is not None and tie_breaker < best_tie
                ):
                    best_plan = plan
                    best_cost = cost
                    best_available = projected_available
                    best_wait = projected_wait

            if best_plan is not None and best_available is not None:
                chosen[bus.id] = best_plan
                station_available = best_available
                operator_wait_totals[bus.operator] = operator_wait_totals.get(bus.operator, 0.0) + best_wait
                network_wait_total += best_wait

        return chosen

    def project_plan(
        self,
        bus: Bus,
        plan: List[str],
        station_available: Dict[str, List[float]],
    ) -> Tuple[float, float]:
        sequence = get_route_sequence(self.scenario.route, bus.direction)
        current_stop = sequence[0]
        current_time = self.time_to_minutes(bus.departure_time)
        total_wait = 0.0

        for station_id in plan:
            current_time += self.travel_minutes(bus, current_stop, station_id)
            charger_times = station_available[station_id]
            charger_idx = min(range(len(charger_times)), key=lambda idx: charger_times[idx])
            start_time = max(current_time, charger_times[charger_idx])
            total_wait += start_time - current_time
            end_time = start_time + self.scenario.physics.charge_duration_minutes
            charger_times[charger_idx] = end_time
            current_time = end_time
            current_stop = station_id

        current_time += self.travel_minutes(bus, current_stop, sequence[-1])
        return total_wait, current_time

    def handle_station_arrival(self, payload: Dict[str, Any]) -> None:
        station_id = payload["station_id"]
        if self.chargers_in_use[station_id] < self.station_capacities[station_id]:
            self.start_charging(payload)
        else:
            self.station_queues[station_id].append(payload)

    def start_charging(self, payload: Dict[str, Any]) -> None:
        station_id = payload["station_id"]
        bus = payload["bus"]
        arrival_time = payload["arrival_time"]
        wait_time = self.time_now - arrival_time
        charge_duration = self.scenario.physics.charge_duration_minutes
        end_time = self.time_now + charge_duration

        self.chargers_in_use[station_id] += 1
        self.operator_wait_totals[bus.operator] = self.operator_wait_totals.get(bus.operator, 0.0) + wait_time

        charge_record = {
            "station": station_id,
            "arrival_time": arrival_time,
            "charge_start": self.time_now,
            "charge_end": end_time,
            "wait_time": wait_time,
        }
        self.bus_state[bus.id]["charges"].append(charge_record)
        self.bus_state[bus.id]["total_wait"] += wait_time

        self.station_timelines.append({
            "Station": station_id,
            "Bus ID": bus.id,
            "Operator": bus.operator,
            "Queue Arrival": self.minutes_to_time(arrival_time),
            "Charge Start": self.minutes_to_time(self.time_now),
            "Charge End": self.minutes_to_time(end_time),
            "Wait Time (min)": round(wait_time, 1),
            "_sort_start": self.time_now,
        })

        payload["charge_end_time"] = end_time
        self.schedule_event(end_time, "CHARGE_END", payload)

    def handle_charge_end(self, payload: Dict[str, Any]) -> None:
        station_id = payload["station_id"]
        bus = payload["bus"]
        self.chargers_in_use[station_id] -= 1

        plan = payload["plan"]
        plan_index = payload["plan_index"]
        if plan_index + 1 < len(plan):
            next_station = plan[plan_index + 1]
            next_arrival = self.time_now + self.travel_minutes(bus, station_id, next_station)
            self.schedule_event(next_arrival, "ARRIVE_STATION", {
                "bus": bus,
                "station_id": next_station,
                "previous_stop": station_id,
                "plan": plan,
                "plan_index": plan_index + 1,
                "arrival_time": next_arrival,
            })
        else:
            destination = get_route_sequence(self.scenario.route, bus.direction)[-1]
            destination_arrival = self.time_now + self.travel_minutes(bus, station_id, destination)
            self.schedule_event(destination_arrival, "ARRIVE_DESTINATION", {
                "bus": bus,
                "arrival_time": destination_arrival,
            })

        self.start_next_waiting_bus(station_id)

    def start_next_waiting_bus(self, station_id: str) -> None:
        queue = self.station_queues[station_id]
        if not queue:
            return

        best_score = None
        best_candidate_idx = 0
        for i, queued_payload in enumerate(queue):
            bus = queued_payload["bus"]
            wait_time = self.time_now - queued_payload["arrival_time"]
            operator_count = max(1, self.operator_bus_counts.get(bus.operator, 1))
            operator_avg_wait = self.operator_wait_totals.get(bus.operator, 0.0) / operator_count
            bus_wait_so_far = self.bus_state[bus.id]["total_wait"]

            context = ScoreContext(
                bus=bus,
                current_wait_time_minutes=wait_time,
                operator_avg_delay_minutes=operator_avg_wait,
                bus_total_accumulated_delay=bus_wait_so_far,
            )
            score = evaluate_urgency(context, self.scenario.weights)
            tie_breaker = (-queued_payload["arrival_time"], bus.id)
            candidate = (score, tie_breaker)
            if best_score is None or candidate > best_score:
                best_score = candidate
                best_candidate_idx = i

        winner_payload = queue.pop(best_candidate_idx)
        self.start_charging(winner_payload)

    def handle_destination_arrival(self, payload: Dict[str, Any]) -> None:
        bus = payload["bus"]
        self.bus_state[bus.id]["arrival_time"] = payload["arrival_time"]

    def format_bus_row(self, state: Dict[str, Any]) -> Dict[str, Any]:
        bus: Bus = state["bus"]
        charges = state["charges"]
        charging_summary = " | ".join(
            f"{c['station']} arrive {self.minutes_to_time(c['arrival_time'])}, "
            f"wait {round(c['wait_time'], 1)} min, "
            f"charge {self.minutes_to_time(c['charge_start'])}-{self.minutes_to_time(c['charge_end'])}"
            for c in charges
        )
        direction = f"{state['origin']} -> {state['destination']}"

        return {
            "Bus ID": bus.id,
            "Operator": bus.operator,
            "Direction": direction,
            "Departure Time": self.minutes_to_time(state["departure_time"]),
            "Charging Plan": " -> ".join(state["plan"]),
            "Charging Timeline": charging_summary,
            "Final Arrival": self.minutes_to_time(state["arrival_time"]),
            "Total Wait (min)": round(state["total_wait"], 1),
        }
