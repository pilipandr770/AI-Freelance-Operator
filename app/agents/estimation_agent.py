"""
Estimation Agent — estimates hours, cost, and creates task breakdown.
Stage: REQUIREMENTS_ANALYZED → ESTIMATION_READY
"""
import json
from app.agents.base import BaseAgent
from app.database import Database, QueryHelper


class EstimationAgent(BaseAgent):
    """
    Based on classified project data:
    - Estimates hours per component
    - Calculates total cost
    - Creates task breakdown
    - Considers complexity and risk factors
    """

    def process(self, project_data):
        project_id = project_data['id']

        # Get full project data from DB
        project = self.get_project(project_id)
        if not project:
            return None

        title = project.get('title', '')
        description = project.get('description', '')
        complexity = project.get('complexity', 'MEDIUM')
        tech_stack = project.get('tech_stack', [])
        is_familiar = project.get('is_familiar_stack', True)
        technical_spec = project.get('technical_spec', '') or ''

        # Parse requirements analysis if available
        req_analysis = ''
        if technical_spec:
            try:
                spec = json.loads(technical_spec)
                parts = []
                if spec.get('scope_summary'):
                    parts.append(f"Scope: {spec['scope_summary']}")
                if spec.get('assumptions'):
                    parts.append(f"Assumptions: {', '.join(spec['assumptions'][:5])}")
                if spec.get('risks'):
                    parts.append(f"Risks: {', '.join(spec['risks'][:5])}")
                if spec.get('clarity_score'):
                    parts.append(f"Requirements clarity: {spec['clarity_score']}/10")
                req_analysis = '\n'.join(parts)
            except (json.JSONDecodeError, TypeError):
                req_analysis = technical_spec[:500]

        # Get hourly rate from settings
        hourly_rate = self._get_hourly_rate()

        self.log_action(project_id, "ESTIMATION_STARTED")

        req_section = f"\nRequirements Analysis:\n{req_analysis}\n" if req_analysis else ''

        prompt = f"""
You are estimating a freelance software project.

Project Title: {title}
Description: {description}
Complexity: {complexity}
Tech Stack: {tech_stack}
Is Familiar Stack: {is_familiar}
Hourly Rate: ${hourly_rate}/hour
{req_section}
Create a detailed estimation with task breakdown.
Take into account the requirements analysis above (especially risks and assumptions).

Return JSON:
{{
    "tasks": [
        {{
            "title": "Task name",
            "description": "What this task involves",
            "estimated_hours": 4.0,
            "priority": 1
        }}
    ],
    "total_hours": 20.0,
    "risk_buffer_hours": 4.0,
    "total_with_buffer": 24.0,
    "quoted_price": 1200.00,
    "price_breakdown": {{
        "development": 800.00,
        "testing": 200.00,
        "deployment": 100.00,
        "risk_buffer": 100.00
    }},
    "timeline_days": 10,
    "estimation_confidence": "HIGH",
    "notes": "any important notes about the estimation"
}}
"""

        try:
            result = self.ai_json(prompt)

            usage = result.pop('_usage', {})
            cost = result.pop('_cost', 0)
            exec_time = result.pop('_execution_time_ms', 0)

            # Update project
            total_hours = float(result.get('total_with_buffer', result.get('total_hours', 0)))
            quoted_price = float(result.get('quoted_price', total_hours * hourly_rate))

            self.update_project_fields(
                project_id,
                estimated_hours=total_hours,
                quoted_price=quoted_price
            )

            # Create tasks in database
            tasks = result.get('tasks', [])
            if tasks:
                self._create_tasks(project_id, tasks)

            self.log_action(
                project_id, "ESTIMATION_COMPLETED",
                output_data=result,
                execution_time_ms=exec_time,
                tokens_used=usage.get('total_tokens'),
                cost=cost
            )

            self.log_state_transition(
                project_id, 'REQUIREMENTS_ANALYZED', 'ESTIMATION_READY',
                f"Estimated {total_hours}h, ${quoted_price}"
            )
            return "ESTIMATION_READY"

        except Exception as e:
            self.log_action(project_id, "ESTIMATION_FAILED", error_message=str(e), success=False)
            # Fallback: use default estimation so pipeline doesn't get stuck
            default_hours = 20.0
            default_price = default_hours * self._get_hourly_rate()
            self.update_project_fields(project_id, estimated_hours=default_hours, quoted_price=default_price)
            self.log_state_transition(project_id, 'REQUIREMENTS_ANALYZED', 'ESTIMATION_READY',
                                      f'Estimation failed — defaults: {default_hours}h, ${default_price}')
            return "ESTIMATION_READY"

    def _get_hourly_rate(self):
        """Get hourly rate from system settings"""
        try:
            return QueryHelper.get_system_setting('hourly_rate', 50.0)
        except Exception:
            return 50.0

    def _create_tasks(self, project_id, tasks):
        """Insert task breakdown into database"""
        try:
            with Database.get_cursor() as cursor:
                for i, task in enumerate(tasks):
                    cursor.execute("""
                        INSERT INTO tasks (project_id, title, description, estimated_hours, priority, status)
                        VALUES (%s, %s, %s, %s, %s, 'pending')
                    """, (
                        project_id,
                        task.get('title', f'Task {i+1}'),
                        task.get('description', ''),
                        float(task.get('estimated_hours', 0)),
                        int(task.get('priority', i))
                    ))
        except Exception as e:
            print(f"Error creating tasks: {e}")
