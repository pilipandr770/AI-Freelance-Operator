from app.agents.base import BaseAgent

class IntakeAgent(BaseAgent):
    def process(self, project_data):
        """
        Process new project intake
        For now, just mark as ready for classification
        In future, could parse email content, extract requirements, etc.
        """
        project_id = project_data['id']

        # Log the intake processing
        self.log_action(project_id, "INTAKE_STARTED", input_data=project_data)

        # For now, just move to classification state
        # In a real implementation, this could:
        # - Parse the original email
        # - Extract key requirements
        # - Validate project details
        # - Set initial tech stack if possible

        self.log_action(project_id, "INTAKE_COMPLETED", output_data={"next_state": "ANALYZED"})

        # Return next state
        return "ANALYZED"