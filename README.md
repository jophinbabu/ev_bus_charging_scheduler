# Electric Bus Charging Scheduler

Streamlit app for the take-home bus charging scheduler assignment.

The app loads one of five scenario JSON files, chooses charging plans for every
bus, runs a discrete event simulation, and shows:

- the input buses,
- each bus's charging plan and final arrival,
- each station's charging order,
- validation checks for the hard constraints.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Project Structure

```text
app.py
requirements.txt
data/
  scenario_1_even_spacing.json
  scenario_2_bunched_start.json
  scenario_3_asymmetric_load.json
  scenario_4_operator_heavy.json
  scenario_5_worst_case_convergence.json
scheduler/
  engine.py
  loader.py
  models.py
  plan_generator.py
  rules.py
  validation.py
```

## Scheduler Method

The scheduler uses:

1. Candidate charging plan generation
2. Projected-cost plan selection
3. Discrete event simulation
4. Rule-based queue scoring
5. Hard-constraint validation

For each bus, `plan_generator.py` generates all charging station combinations
that satisfy the 240 km battery range. The engine then estimates the wait caused
by each plan using current projected station availability and picks the lowest
cost valid plan.

During simulation, buses arrive at charging stations, wait if all chargers are
busy, charge for exactly 25 minutes, and continue to the next planned station or
destination. When a charger becomes free and multiple buses are waiting,
`rules.py` computes urgency and the highest-urgency bus charges next.

## Change a Weight

Weights live in each scenario file:

```json
"weights": {
  "individual_wait": 1.0,
  "operator_delay": 2.0,
  "overall_delay": 1.0
}
```

Changing these values changes plan selection and queue priority without changing
the engine code.

## Add a New Rule

Add a rule class in `scheduler/rules.py`:

```python
class PriorityBusRule(Rule):
    name = "priority_bus"

    def score(self, context):
        return 100.0 if getattr(context.bus, "priority", False) else 0.0
```

Then register it in `get_active_rules()` and add the weight to scenario data.
The event loop does not need to change.

## Validation

`scheduler/validation.py` checks:

- every bus reaches its destination,
- every leg stays within battery range,
- route order is respected,
- charge duration is fixed,
- charger capacity is never exceeded,
- station output matches simulated charge events.

These checks are shown in the Streamlit app for every scenario.
