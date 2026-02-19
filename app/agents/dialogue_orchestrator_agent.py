"""
Dialogue Orchestrator Agent — manages all client communication.
Generates responses to client messages during negotiation.
Stage: NEGOTIATION (handles replies, stays in NEGOTIATION or moves to AGREED/REJECTED)
"""
import json
from app.agents.base import BaseAgent
from app.database import Database, QueryHelper
from app.telegram_notifier import get_notifier


class DialogueOrchestratorAgent(BaseAgent):
    """
    Manages client correspondence:
    - Responds to client questions
    - Handles negotiation
    - Guides towards agreement
    - Detects agreement or rejection signals
    """

    def process(self, project_data):
        """
        Check for unprocessed inbound messages and generate responses.
        """
        project_id = project_data['id']

        # Get unprocessed inbound messages
        messages = self._get_unprocessed_messages(project_id)
        if not messages:
            # No new messages to respond to — stay in current state
            return None

        # Get full project context
        project = self.get_project(project_id)
        if not project:
            return None

        # Get conversation history
        history = self._get_conversation_history(project_id)
        max_rounds = self._get_max_negotiation_rounds()

        self.log_action(project_id, "DIALOGUE_PROCESSING", 
                       input_data={"unprocessed_count": len(messages)})

        for message in messages:
            response_state = self._handle_message(project, message, history, max_rounds)
            self._mark_processed(message['id'])
            
            if response_state:
                return response_state

        return None  # Stay in current state

    def _handle_message(self, project, message, history, max_rounds):
        """Process a single inbound message and generate response"""
        project_id = project['id']
        title = project.get('title', '')
        quoted_price = project.get('quoted_price', 0)
        estimated_hours = project.get('estimated_hours', 0)

        # Build conversation context
        conv_text = ""
        for h in history[-10:]:  # Last 10 messages
            direction = "CLIENT" if h['direction'] == 'inbound' else "ME"
            conv_text += f"\n{direction}: {h['body'][:500]}\n"

        prompt = f"""
You are a professional freelance developer managing client communication.

Project: {title}
Quoted Price: ${quoted_price}
Estimated Hours: {estimated_hours}h
Negotiation Round: {len(history)} / {max_rounds} max

Conversation History:
{conv_text}

Latest Client Message:
{message.get('body', '')}

Analyze the client's message and decide:
1. If client AGREES to the offer → set decision = "AGREED"
2. If client wants to NEGOTIATE (price, scope, timeline) → set decision = "NEGOTIATE" and reply
3. If client REJECTS / is not interested → set decision = "REJECTED"
4. If client asks questions → set decision = "QUESTION" and answer
5. If max negotiation rounds reached → set decision = "ESCALATE"

Return JSON:
{{
    "decision": "NEGOTIATE",
    "reply_text": "your professional reply to the client",
    "reply_subject": "Re: {title}",
    "price_adjustment": null,
    "notes": "internal notes about this interaction"
}}
"""

        try:
            result = self.ai_json(prompt)

            usage = result.pop('_usage', {})
            cost = result.pop('_cost', 0)
            exec_time = result.pop('_execution_time_ms', 0)

            decision = result.get('decision', 'NEGOTIATE')
            reply_text = result.get('reply_text', '')

            # Store reply as outbound message
            if reply_text:
                self._store_reply(project_id, project.get('client_email', ''),
                                result.get('reply_subject', f'Re: {title}'), reply_text)

            # Handle price adjustment
            if result.get('price_adjustment') and decision == 'NEGOTIATE':
                try:
                    new_price = float(result['price_adjustment'])
                    self.update_project_field(project_id, 'quoted_price', new_price)
                except (ValueError, TypeError):
                    pass

            self.log_action(
                project_id, f"DIALOGUE_{decision}",
                output_data=result,
                execution_time_ms=exec_time,
                tokens_used=usage.get('total_tokens'),
                cost=cost
            )

            # State transitions
            if decision == 'AGREED':
                self.log_state_transition(project_id, 'NEGOTIATION', 'AGREED', 'Client agreed')
                return "AGREED"
            elif decision == 'REJECTED':
                self.update_project_field(project_id, 'rejection_reason', 'Client declined')
                self.log_state_transition(project_id, 'NEGOTIATION', 'REJECTED', 'Client declined')
                return "REJECTED"
            elif decision == 'ESCALATE':
                # Too many rounds — needs human intervention
                self.log_state_transition(project_id, 'NEGOTIATION', 'NEGOTIATION',
                                        'Max negotiation rounds reached — needs human review')
                get_notifier().notify_escalate(
                    project_id, title,
                    f'Достигнут лимит переговоров ({max_rounds} раундов). Нужно ваше решение.'
                )
                return None

            return None  # Stay in NEGOTIATION

        except Exception as e:
            self.log_action(project_id, "DIALOGUE_FAILED", error_message=str(e), success=False)
            return None

    def _get_unprocessed_messages(self, project_id):
        """Get unprocessed inbound messages"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    SELECT id, subject, body, sender_email, created_at 
                    FROM project_messages 
                    WHERE project_id = %s AND direction = 'inbound' AND is_processed = FALSE
                    ORDER BY created_at ASC
                """, (project_id,))
                return cursor.fetchall()
        except Exception:
            return []

    def _get_conversation_history(self, project_id):
        """Get full conversation history"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    SELECT direction, subject, body, created_at 
                    FROM project_messages 
                    WHERE project_id = %s
                    ORDER BY created_at ASC
                """, (project_id,))
                return cursor.fetchall()
        except Exception:
            return []

    def _get_max_negotiation_rounds(self):
        try:
            return QueryHelper.get_system_setting('max_negotiation_rounds', 5)
        except Exception:
            return 5

    def _mark_processed(self, message_id):
        """Mark a message as processed"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute(
                    "UPDATE project_messages SET is_processed = TRUE WHERE id = %s",
                    (message_id,)
                )
        except Exception as e:
            print(f"Error marking message processed: {e}")

    def _store_reply(self, project_id, client_email, subject, body):
        """Store an outbound reply message"""
        try:
            mail_username = QueryHelper.get_system_setting('mail_username', '')
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO project_messages 
                    (project_id, direction, sender_email, recipient_email, subject, body, is_processed)
                    VALUES (%s, 'outbound', %s, %s, %s, %s, FALSE)
                """, (project_id, mail_username, client_email, subject, body))
        except Exception as e:
            print(f"Error storing reply: {e}")
