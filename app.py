import streamlit as st
import pandas as pd
from scheduler.loader import load_scenario
from scheduler.engine import SimulationEngine
from scheduler.validation import validate_results

# --- Page Config ---
st.set_page_config(page_title="Bus Charging Scheduler", layout="wide")
st.title("Electric Bus Charging Scheduler")

# --- Scenario Selection ---
# Assume these files exist in a 'data' folder
scenario_files = {
    "Scenario 1: Even Spacing": "data/scenario_1_even_spacing.json",
    "Scenario 2: Bunched Start": "data/scenario_2_bunched_start.json",
    "Scenario 3: Asymmetric Load": "data/scenario_3_asymmetric_load.json",
    "Scenario 4: Operator Heavy": "data/scenario_4_operator_heavy.json",
    "Scenario 5: Worst Case Convergence": "data/scenario_5_worst_case_convergence.json",
}

selected_scenario = st.selectbox("Select Scenario", list(scenario_files.keys()))

# --- Load and Run ---
try:
    scenario = load_scenario(scenario_files[selected_scenario])
    
    # Run the DES Engine
    engine = SimulationEngine(scenario)
    results = engine.run()
    validation_rows = validate_results(scenario, results)
    
    # --- UI: Input Data ---
    st.header("1. Input Data")
    st.write(f"**Name:** {scenario.name} | **Rules Active:** Individual Wait ({scenario.weights.individual_wait}), Operator ({scenario.weights.operator_delay}), Overall ({scenario.weights.overall_delay})")
    
    # Format input buses for display
    buses_df = pd.DataFrame([{
        "Bus ID": b.id, 
        "Operator": b.operator, 
        "Direction": b.direction, 
        "Departure Time": b.departure_time
    } for b in scenario.buses])
    st.dataframe(buses_df, use_container_width=True)

    # --- UI: Per-Bus Timetable ---
    st.header("2. Per-Bus Timetable")
    if results["bus_timelines"]:
        bus_df = pd.DataFrame(results["bus_timelines"])
        st.dataframe(bus_df, use_container_width=True)
    else:
        st.warning("No valid routes calculated.")

    if results.get("unscheduled_buses"):
        st.error("Some buses could not be scheduled.")
        st.dataframe(pd.DataFrame(results["unscheduled_buses"]), use_container_width=True)

    # --- UI: Per-Station View ---
    st.header("3. Per-Station Charging Order")
    if results["station_timelines"]:
        station_df = pd.DataFrame(results["station_timelines"])
        
        # Create tabs for each station for cleaner viewing
        station_ids = [s.id for s in scenario.stations]
        tabs = st.tabs([f"Station {sid}" for sid in station_ids])
        
        for idx, sid in enumerate(station_ids):
            with tabs[idx]:
                st_data = station_df[station_df["Station"] == sid]
                st.dataframe(st_data, use_container_width=True)
    else:
        st.warning("No station activity recorded.")

    # --- UI: Validation ---
    st.header("4. Validation")
    validation_df = pd.DataFrame(validation_rows)
    st.dataframe(validation_df, use_container_width=True)

    if (validation_df["Status"] == "FAIL").any():
        st.error("One or more hard constraints failed.")
    else:
        st.success("All hard constraints passed.")

except FileNotFoundError:
    st.error(f"Could not find the JSON file for {selected_scenario}. Ensure it exists in the 'data' directory.")
