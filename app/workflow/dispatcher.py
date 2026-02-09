from app.agents.intake_agent import IntakeAgent
from app.agents.classification_agent import ClassificationAgent

class WorkflowDispatcher:
    def __init__(self):
        self.stage_agents = {
            'NEW': IntakeAgent,
            'ANALYZED': ClassificationAgent,
            # Add more mappings as needed
        }

    def get_agent_for_stage(self, current_state):
        """Get the appropriate agent class for a given state"""
        agent_class = self.stage_agents.get(current_state)
        if agent_class:
            return agent_class()
        return None

    def get_available_stages(self):
        """Return list of stages that have agents"""
        return list(self.stage_agents.keys())