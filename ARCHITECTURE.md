# Architecture

## Approach

The scheduler is built as a data-driven discrete event simulation.

This fits the problem because all important decisions happen at events:

- a bus reaches a charging station,
- a charger becomes free,
- a bus finishes charging,
- a bus reaches its destination.

The engine jumps between these events instead of simulating every minute.

## Data Model

Each scenario JSON file describes the world:

- physical constants,
- route stops,
- segment distances,
- station charger counts,
- operators,
- buses,
- scheduling weights.

The code does not hardcode the number of buses, stations, operators, or
chargers. The assignment's route is just the current data.

## Scheduling Flow

1. `loader.py` reads a scenario JSON file into dataclasses.
2. `plan_generator.py` creates all range-valid charging plans for each bus.
3. `engine.py` greedily selects one plan per bus using projected charger
   availability and weighted soft costs.
4. `engine.py` runs the discrete event simulation.
5. `rules.py` ranks queued buses when a charger becomes free.
6. `validation.py` checks hard constraints.
7. `app.py` renders the input, bus timeline, station timeline, and validation.

## Plan Selection

For a candidate plan, the engine estimates:

- total wait for that bus,
- projected operator average wait,
- projected network average wait,
- a small penalty for extra charging stops.

The plan with the lowest projected cost is selected.

```text
cost =
    individual_wait_weight * projected_bus_wait
  + operator_delay_weight  * projected_operator_average_wait
  + overall_delay_weight   * projected_network_average_wait
  + small_extra_stop_penalty
```

This is not a mathematical global optimum. It is a practical heuristic that is
fast, explainable, and easy to extend.

## Queue Scoring

When multiple buses are waiting for the same charger, the engine builds a
`ScoreContext` and asks each active rule for a score.

```text
urgency =
    individual_wait_weight * current_queue_wait
  + operator_delay_weight  * operator_average_wait
  + overall_delay_weight   * bus_accumulated_wait
```

The highest urgency bus charges next. Ties are deterministic.

## Future Changes Anticipated

### Add a New Station

Add the stop to `route.stops`, add the new route segments, and add the stop to
`stations` if it has chargers. Plan generation reads the route dynamically.

### Change Segment Distance

Edit the matching segment in the scenario JSON. Travel time and range validation
both use segment distances from data.

### Add More Chargers

Change the station's `chargers` value. The engine tracks station capacity from
data and validation uses the same value.

### Add More Operators

Add the operator name to `operators` and assign buses to it. Operator wait
tracking is initialized from the scenario.

### Add More Buses

Append bus records to the scenario. The event queue and output tables are based
on the loaded bus list.

### Change Battery Range or Charge Time

Edit `physics.battery_range_km` or `physics.charge_duration_minutes`. Plan
generation and simulation read those values from data.

### Add a New Soft Rule

Create a new rule class in `rules.py`, register it in `get_active_rules()`, and
add a scenario weight. The engine does not need new queue logic.

### Add a New Hard Rule

Add a validation check in `validation.py`. If the rule affects feasibility,
also add it to `plan_generator.py` or the plan selection cost.

## Assumptions

- Buses leave endpoints fully charged.
- Endpoints are not scheduled charging stations.
- Every charge fills the battery to full.
- Travel speed is constant across the route.
- Buses only charge at stations in their selected plan.
- Time may pass midnight; displayed times wrap to `HH:MM`.
- The scheduler aims for defensible operational behavior, not guaranteed global
  optimality.
