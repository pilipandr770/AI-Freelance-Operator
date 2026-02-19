"""
Scam Filter Agent — analyzes project for fraud/scam/illegal indicators.
Stage: PARSED → ANALYZED (or REJECTED if scam)
"""
import json
from app.agents.base import BaseAgent
from app.database import Database


class ScamFilterAgent(BaseAgent):
    """
    Analyzes project for:
    - Scam indicators
    - Illegal activity requests  
    - Unrealistic promises
    - Suspicious patterns
    
    Outputs scam_score (0-1) and decision.
    """

    def process(self, project_data):
        project_id = project_data['id']
        description = project_data.get('description', '') or ''
        client_email = project_data.get('client_email', '')
        title = project_data.get('title', '')
        budget_min = project_data.get('budget_min')
        budget_max = project_data.get('budget_max')

        self.log_action(project_id, "SCAM_FILTER_STARTED")

        # Get threshold from settings
        scam_threshold = self._get_scam_threshold()

        prompt = f"""
Analyze this freelance project for scam and fraud indicators.

Project Title: {title}
Client Email: {client_email}
Description: {description}
Budget: {budget_min} - {budget_max}

Check for:
1. Unrealistic promises or too-good-to-be-true offers
2. Requests for illegal activities (hacking, malware, data theft, etc.)
3. Suspicious payment patterns (overpayment scams, advance fee fraud)
4. Cryptocurrency/gambling scams
5. Identity/document fraud requests
6. Poor grammar combined with unrealistically high budget
7. Requests for personal information
8. Urgency pressure tactics
9. No clear project scope
10. Known scam patterns

Return JSON:
{{
    "scam_score": 0.0 to 1.0,
    "is_scam": true/false,
    "is_illegal": true/false,
    "risk_factors": ["factor1", "factor2"],
    "analysis": "brief explanation",
    "recommendation": "ACCEPT" or "REJECT" or "REVIEW"
}}
"""

        try:
            result = self.ai_json(prompt)
            
            usage = result.pop('_usage', {})
            cost = result.pop('_cost', 0)
            exec_time = result.pop('_execution_time_ms', 0)

            scam_score = float(result.get('scam_score', 0))
            is_scam = result.get('is_scam', False)
            is_illegal = result.get('is_illegal', False)
            recommendation = result.get('recommendation', 'ACCEPT')

            # Update project
            self.update_project_fields(
                project_id,
                scam_score=scam_score,
                is_scam=is_scam,
                is_illegal=is_illegal
            )

            self.log_action(
                project_id, "SCAM_FILTER_COMPLETED",
                output_data=result,
                execution_time_ms=exec_time,
                tokens_used=usage.get('total_tokens'),
                cost=cost
            )

            # Decision: reject or continue
            if is_illegal or is_scam or scam_score >= scam_threshold:
                reason = result.get('analysis', 'Flagged as potential scam/illegal')
                self.update_project_field(project_id, 'rejection_reason', reason)
                self.log_state_transition(project_id, 'PARSED', 'REJECTED', f'Scam score: {scam_score}', result)
                
                # Blacklist client if illegal
                if is_illegal and client_email:
                    self._blacklist_client(client_email, reason)
                
                return "REJECTED"

            self.log_state_transition(project_id, 'PARSED', 'ANALYZED', f'Scam score: {scam_score}, passed filter')
            return "ANALYZED"

        except Exception as e:
            self.log_action(project_id, "SCAM_FILTER_FAILED", error_message=str(e), success=False)
            # On error, let it through but log
            self.log_state_transition(project_id, 'PARSED', 'ANALYZED', f'Scam filter error: {e}')
            return "ANALYZED"

    def _get_scam_threshold(self):
        """Get scam threshold from system settings"""
        try:
            from app.database import QueryHelper
            return QueryHelper.get_system_setting('scam_filter_threshold', 0.7)
        except Exception:
            return 0.7

    def _blacklist_client(self, email, reason):
        """Blacklist a client by email"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE clients SET is_blacklisted = TRUE, blacklist_reason = %s
                    WHERE email = %s
                """, (reason, email))
        except Exception as e:
            print(f"Error blacklisting client: {e}")
