from app.agents.base import BaseAgent
import json

class ClassificationAgent(BaseAgent):
    def process(self, project_data):
        """
        Classify project: determine tech stack, budget category, priority
        """
        project_id = project_data['id']
        description = project_data['description'] or ""

        self.log_action(project_id, "CLASSIFICATION_STARTED", input_data={"description": description})

        # Use AI to classify the project
        classification_prompt = f"""
        Analyze this freelance project description and classify it:

        Project Description: {description}

        Please provide:
        1. Primary technology stack (as JSON array)
        2. Budget category: LOW (<$1000), MEDIUM ($1000-$5000), HIGH (>$5000)
        3. Project complexity: MICRO, SMALL, MEDIUM, LARGE, RND
        4. Estimated timeline category: QUICK (1-2 weeks), STANDARD (1-3 months), LONG (>3 months)

        Respond in JSON format:
        {{
            "tech_stack": ["tech1", "tech2"],
            "budget_category": "MEDIUM",
            "complexity": "SMALL",
            "timeline": "STANDARD"
        }}
        """

        try:
            response = self.ai_client.generate_response(classification_prompt)
            # Parse JSON response
            classification = json.loads(response.strip())

            # Update project with classification results
            tech_stack = classification.get('tech_stack', [])
            complexity = classification.get('complexity', 'UNKNOWN')

            # Update tech_stack if not already set
            if not project_data['tech_stack']:
                self.update_project_field(project_id, 'tech_stack', tech_stack)

            # Update complexity
            self.update_project_field(project_id, 'complexity', complexity)

            # Add classification metadata
            output_data = {
                "tech_stack": tech_stack,
                "complexity": complexity,
                "next_state": "NEGOTIATION"
            }
            self.log_action(project_id, "CLASSIFICATION_COMPLETED", output_data=output_data)

            # Move to negotiation state
            return "NEGOTIATION"

        except Exception as e:
            self.log_action(project_id, "CLASSIFICATION_FAILED", error_message=str(e), success=False)
            # Stay in current state on error
            return None