"""
Offer Generator Agent — generates commercial proposal / offer document.
Stage: ESTIMATION_READY → OFFER_SENT
"""
import json
from app.agents.base import BaseAgent
from app.database import Database, QueryHelper


class OfferGeneratorAgent(BaseAgent):
    """
    Generates a professional commercial proposal including:
    - Project scope
    - Deliverables
    - Timeline
    - Price breakdown
    - Payment terms
    - Next steps
    """

    def process(self, project_data):
        project_id = project_data['id']

        # Get full project data
        project = self.get_project(project_id)
        if not project:
            return None

        title = project.get('title', '')
        description = project.get('description', '')
        complexity = project.get('complexity', '')
        tech_stack = project.get('tech_stack', [])
        estimated_hours = project.get('estimated_hours', 0)
        quoted_price = project.get('quoted_price', 0)
        client_email = project.get('client_email', '')

        # Get settings
        prepayment = self._get_prepayment_percentage()
        hourly_rate = self._get_hourly_rate()

        # Get tasks
        tasks = self._get_tasks(project_id)

        self.log_action(project_id, "OFFER_GENERATION_STARTED")

        prompt = f"""
Generate a professional commercial proposal for a freelance project.

Project Title: {title}
Description: {description}
Complexity: {complexity}
Tech Stack: {', '.join(tech_stack) if tech_stack else 'To be determined'}
Estimated Hours: {estimated_hours}
Quoted Price: ${quoted_price}
Hourly Rate: ${hourly_rate}
Prepayment Required: {prepayment}%
Client Email: {client_email}

Task Breakdown:
{json.dumps(tasks, indent=2, default=str) if tasks else 'No detailed breakdown available'}

Generate a complete commercial proposal in plain text (not markdown). The proposal should be professional,
clear, and ready to send to the client via email.

Return JSON:
{{
    "subject": "email subject line for the proposal",
    "proposal_text": "full text of the proposal email",
    "summary": {{
        "total_price": {quoted_price},
        "prepayment_amount": {quoted_price * prepayment / 100},
        "estimated_delivery_days": 14,
        "payment_terms": "50% upfront, 50% on delivery"
    }}
}}
"""

        try:
            result = self.ai_json(prompt)

            usage = result.pop('_usage', {})
            cost = result.pop('_cost', 0)
            exec_time = result.pop('_execution_time_ms', 0)

            # Store the proposal as technical_spec (repurposing field for now)
            proposal_text = result.get('proposal_text', '')
            if proposal_text:
                self.update_project_field(project_id, 'technical_spec', proposal_text)

            # Store the offer as a project message (outbound, ready to send)
            subject = result.get('subject', f'Proposal: {title}')
            self._store_offer_message(project_id, client_email, subject, proposal_text)

            self.log_action(
                project_id, "OFFER_GENERATION_COMPLETED",
                output_data={"subject": subject, "summary": result.get('summary', {})},
                execution_time_ms=exec_time,
                tokens_used=usage.get('total_tokens'),
                cost=cost
            )

            self.log_state_transition(
                project_id, 'ESTIMATION_READY', 'OFFER_SENT',
                f"Offer generated: ${quoted_price}"
            )
            return "OFFER_SENT"

        except Exception as e:
            self.log_action(project_id, "OFFER_GENERATION_FAILED", error_message=str(e), success=False)
            # Fallback: generate a simple offer so pipeline doesn't get stuck
            fallback_text = (
                f"Hello,\n\nThank you for your project \"{title}\".\n"
                f"I can complete this for ${quoted_price:.0f} in approximately {estimated_hours:.0f} hours.\n"
                f"Please let me know if you'd like to proceed.\n\nBest regards"
            )
            self._store_offer_message(project_id, client_email, f'Proposal: {title}', fallback_text)
            self.log_state_transition(project_id, 'ESTIMATION_READY', 'OFFER_SENT',
                                      'Offer gen failed — using fallback proposal')
            return "OFFER_SENT"

    def _get_prepayment_percentage(self):
        try:
            return QueryHelper.get_system_setting('prepayment_percentage', 50)
        except Exception:
            return 50

    def _get_hourly_rate(self):
        try:
            return QueryHelper.get_system_setting('hourly_rate', 50.0)
        except Exception:
            return 50.0

    def _get_tasks(self, project_id):
        """Get task breakdown for project"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    SELECT title, description, estimated_hours, priority 
                    FROM tasks WHERE project_id = %s ORDER BY priority
                """, (project_id,))
                return cursor.fetchall()
        except Exception:
            return []

    def _store_offer_message(self, project_id, client_email, subject, body):
        """Store the generated offer as an outbound message"""
        try:
            mail_username = QueryHelper.get_system_setting('mail_username', '')
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO project_messages 
                    (project_id, direction, sender_email, recipient_email, subject, body, is_processed)
                    VALUES (%s, 'outbound', %s, %s, %s, %s, FALSE)
                """, (project_id, mail_username, client_email, subject, body))
        except Exception as e:
            print(f"Error storing offer message: {e}")
