from dataclasses import dataclass
from typing import List
from .models import Bus, Weights

@dataclass
class ScoreContext:
    """
    A snapshot of the current simulation state for a specific bus.
    The engine creates this and passes it to the rules.
    """
    bus: Bus
    current_wait_time_minutes: float
    operator_avg_delay_minutes: float
    bus_total_accumulated_delay: float

class Rule:
    """Base interface for all scoring rules."""
    name = ""

    def score(self, context: ScoreContext) -> float:
        """Returns an unweighted urgency score. Higher = more urgent."""
        raise NotImplementedError

class IndividualWaitRule(Rule):
    """Prioritizes buses that have been waiting in the current queue the longest."""
    name = "individual_wait"

    def score(self, context: ScoreContext) -> float:
        return context.current_wait_time_minutes

class OperatorDelayRule(Rule):
    """Prioritizes buses belonging to an operator whose fleet is currently suffering delays."""
    name = "operator_delay"

    def score(self, context: ScoreContext) -> float:
        return context.operator_avg_delay_minutes

class OverallDelayRule(Rule):
    """Prioritizes buses that have already accumulated a lot of delay across their whole journey."""
    name = "overall_delay"

    def score(self, context: ScoreContext) -> float:
        return context.bus_total_accumulated_delay

# --- The Scoring Engine ---

def get_active_rules() -> List[Rule]:
    """Registry of all rules currently active in the system."""
    return [
        IndividualWaitRule(),
        OperatorDelayRule(),
        OverallDelayRule()
    ]

def evaluate_urgency(context: ScoreContext, weights: Weights) -> float:
    """
    Calculates the final urgency score for a bus waiting in a queue.
    Multiplies each rule's raw score by the weight defined in the scenario JSON.
    """
    total_score = 0.0
    
    # Convert the Weights dataclass to a dictionary for easy lookup
    weight_dict = {
        "individual_wait": weights.individual_wait,
        "operator_delay": weights.operator_delay,
        "overall_delay": weights.overall_delay
    }
    
    for rule in get_active_rules():
        # Get the configured weight, defaulting to 0 if not found
        weight = weight_dict.get(rule.name, 0.0)
        
        if weight > 0:
            # Add the weighted score to the total urgency
            total_score += (rule.score(context) * weight)
            
    return total_score
