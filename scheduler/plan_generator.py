from itertools import combinations
from typing import List
from .models import Route, Bus, Physics, Station

def get_route_sequence(route: Route, direction: str) -> List[str]:
    if direction == "Kochi_to_Bengaluru":
        return list(reversed(route.stops))
    return route.stops

def get_distance(route: Route, start_stop: str, end_stop: str, sequence: List[str]) -> float:
    if start_stop == end_stop:
        return 0.0
    
    start_idx = sequence.index(start_stop)
    end_idx = sequence.index(end_stop)
    
    total_distance = 0.0
    
    for i in range(start_idx, end_idx):
        current = sequence[i]
        next_stop = sequence[i+1]
        
        for seg in route.segments:
            if (seg.from_stop == current and seg.to_stop == next_stop) or \
               (seg.to_stop == current and seg.from_stop == next_stop):
                total_distance += seg.distance_km
                break
                
    return total_distance

def generate_valid_plans(route: Route, bus: Bus, physics: Physics, stations: List[Station]) -> List[List[str]]:

    sequence = get_route_sequence(route, bus.direction)
    origin = sequence[0]
    destination = sequence[-1]
    
    # Get just the IDs of the stations available along this route
    station_ids = [s.id for s in stations]
    available_stations = [s for s in sequence if s in station_ids]
    
    valid_plans = []
    
    # Generate every possible combination of stations (from 1 station up to all 4)
    for r in range(1, len(available_stations) + 1):
        for combo in combinations(available_stations, r):
            plan = list(combo)
            
            # Create the full journey path: Origin -> [Plan] -> Destination
            full_path = [origin] + plan + [destination]
            
            # Validate the distances between consecutive points in this journey
            is_valid = True
            for i in range(len(full_path) - 1):
                dist = get_distance(route, full_path[i], full_path[i+1], sequence)
                if dist > physics.battery_range_km:
                    is_valid = False
                    break  # Fails the physics test, discard this plan
            
            if is_valid:
                valid_plans.append(plan)
                
    return valid_plans