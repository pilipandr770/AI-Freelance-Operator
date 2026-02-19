"""
Classification Agent — classifies project complexity, tech stack, budget category.
Stage: ANALYZED → CLASSIFIED
"""
import json
from app.agents.base import BaseAgent


class ClassificationAgent(BaseAgent):
    """
    Classifies projects by:
    - Complexity (MICRO, SMALL, MEDIUM, LARGE, RND)
    - Tech stack identification
    - Budget category
    - Timeline estimation
    """

    def process(self, project_data):
        project_id = project_data['id']
        description = project_data.get('description', '') or ''
        title = project_data.get('title', '')
        tech_stack = project_data.get('tech_stack', [])
        budget_min = project_data.get('budget_min')
        budget_max = project_data.get('budget_max')

        self.log_action(project_id, "CLASSIFICATION_STARTED")

        prompt = f"""
Analyze this freelance project and classify it.

Project Title: {title}
Description: {description}
Existing Tech Stack: {tech_stack or 'Not specified'}
Budget Range: {budget_min or '?'} - {budget_max or '?'}

Classify:
1. Complexity: MICRO (<4 hours), SMALL (4-20h), MEDIUM (20-80h), LARGE (80-200h), RND (needs research)
2. Technology stack needed (be specific)
3. Category of work
4. Is this tech stack common/familiar for a full-stack developer?

Return JSON:
{{
    "complexity": "SMALL",
    "tech_stack": ["Python", "Flask", "PostgreSQL"],
    "category": "web_development",
    "is_familiar_stack": true,
    "estimated_hours_min": 10,
    "estimated_hours_max": 20,
    "key_challenges": ["challenge1", "challenge2"],
    "classification_notes": "brief notes"
}}
"""

        try:
            result = self.ai_json(prompt)

            usage = result.pop('_usage', {})
            cost = result.pop('_cost', 0)
            exec_time = result.pop('_execution_time_ms', 0)

            # Update project fields
            updates = {}
            if result.get('complexity'):
                updates['complexity'] = result['complexity']
            if result.get('tech_stack'):
                updates['tech_stack'] = result['tech_stack']
            if result.get('category'):
                updates['category'] = result['category']
            if 'is_familiar_stack' in result:
                updates['is_familiar_stack'] = result['is_familiar_stack']
            if result.get('estimated_hours_min'):
                updates['estimated_hours'] = float(result.get('estimated_hours_max', result['estimated_hours_min']))

            if updates:
                self.update_project_fields(project_id, **updates)

            self.log_action(
                project_id, "CLASSIFICATION_COMPLETED",
                output_data=result,
                execution_time_ms=exec_time,
                tokens_used=usage.get('total_tokens'),
                cost=cost
            )

            self.log_state_transition(project_id, 'ANALYZED', 'CLASSIFIED',
                                      f"Complexity: {result.get('complexity', '?')}")
            return "CLASSIFIED"

        except Exception as e:
            self.log_action(project_id, "CLASSIFICATION_FAILED", error_message=str(e), success=False)
            # Fallback: set defaults so pipeline doesn't get stuck
            self.update_project_fields(project_id, complexity='MEDIUM', category='general')
            self.log_state_transition(project_id, 'ANALYZED', 'CLASSIFIED',
                                      'Classification failed — using defaults')
            return "CLASSIFIED"