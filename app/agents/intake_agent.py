"""
Intake Agent — first touch: validates project has minimum data to proceed.
Stage: (used as a quick pass-through or validation check)
This agent is now replaced by EmailParserAgent for the NEW state.
Kept for backward compatibility.
"""
from app.agents.base import BaseAgent


class IntakeAgent(BaseAgent):
    """Quick validation that a project has enough data to proceed."""

    def process(self, project_data):
        project_id = project_data['id']
        self.log_action(project_id, "INTAKE_CHECK")

        description = project_data.get('description', '') or ''
        title = project_data.get('title', '')

        # Minimal validation
        if not description and not title:
            self.log_action(project_id, "INTAKE_REJECTED", 
                          output_data={"reason": "No title or description"}, success=False)
            self.update_project_field(project_id, 'rejection_reason', 'Empty project — no title or description')
            return "REJECTED"

        self.log_action(project_id, "INTAKE_PASSED")
        return "PARSED"