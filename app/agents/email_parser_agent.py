"""
Email Parser Agent — parses raw email content into structured project data.
Stage: NEW → PARSED
"""
import json
from app.agents.base import BaseAgent


class EmailParserAgent(BaseAgent):
    """
    Takes raw email content from a new project and extracts:
    - Project title
    - Description (cleaned)
    - Budget hints
    - Deadline hints
    - Tech stack hints
    - Client info
    """

    def process(self, project_data):
        project_id = project_data['id']
        description = project_data.get('description', '') or ''
        client_email = project_data.get('client_email', '')

        self.log_action(project_id, "EMAIL_PARSE_STARTED")

        prompt = f"""
You are parsing a freelance project inquiry email. Extract structured information.

Raw email content:
---
{description}
---

Sender email: {client_email}

Extract and return JSON:
{{
    "title": "concise project title (max 100 chars)",
    "clean_description": "cleaned project description without email headers/signatures",
    "budget_min": null or number,
    "budget_max": null or number,
    "deadline_mentioned": null or "text about any deadline mentioned",
    "tech_stack_hints": ["technology1", "technology2"],
    "client_name": "extracted name or null",
    "client_company": "extracted company or null",
    "language": "en or detected language code",
    "has_attachments_mentioned": false
}}
"""

        try:
            result = self.ai_json(prompt)
            
            # Remove metadata keys
            usage = result.pop('_usage', {})
            cost = result.pop('_cost', 0)
            exec_time = result.pop('_execution_time_ms', 0)

            # Update project fields
            updates = {}
            if result.get('title'):
                updates['title'] = result['title'][:500]
            if result.get('clean_description'):
                updates['description'] = result['clean_description']
            if result.get('budget_min'):
                updates['budget_min'] = float(result['budget_min'])
            if result.get('budget_max'):
                updates['budget_max'] = float(result['budget_max'])
            if result.get('tech_stack_hints'):
                updates['tech_stack'] = result['tech_stack_hints']

            if updates:
                self.update_project_fields(project_id, **updates)

            # Try to link/create client
            if client_email:
                self._ensure_client(client_email, result.get('client_name'), result.get('client_company'))

            self.log_action(
                project_id, "EMAIL_PARSE_COMPLETED",
                output_data=result,
                execution_time_ms=exec_time,
                tokens_used=usage.get('total_tokens'),
                cost=cost
            )

            self.log_state_transition(project_id, 'NEW', 'PARSED', 'Email parsed successfully')
            return "PARSED"

        except Exception as e:
            self.log_action(project_id, "EMAIL_PARSE_FAILED", error_message=str(e), success=False)
            # Still move to PARSED so pipeline continues — don't block on parse failure
            self.log_state_transition(project_id, 'NEW', 'PARSED', f'Email parse failed: {e}')
            return "PARSED"

    def _ensure_client(self, email, name=None, company=None):
        """Create client if not exists, link to project"""
        from app.database import Database
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("SELECT id FROM clients WHERE email = %s", (email,))
                client = cursor.fetchone()
                if not client:
                    cursor.execute("""
                        INSERT INTO clients (email, name, company) 
                        VALUES (%s, %s, %s)
                        ON CONFLICT (email) DO UPDATE SET 
                            name = COALESCE(EXCLUDED.name, clients.name),
                            company = COALESCE(EXCLUDED.company, clients.company)
                        RETURNING id
                    """, (email, name, company))
                    client = cursor.fetchone()
                
                if client:
                    # Link project to client
                    cursor.execute("""
                        UPDATE projects SET client_id = %s 
                        WHERE client_email = %s AND client_id IS NULL
                    """, (client['id'], email))
        except Exception as e:
            print(f"Error ensuring client: {e}")
