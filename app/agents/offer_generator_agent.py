"""
Offer Generator Agent — generates commercial proposal / offer document.
Stage: ESTIMATION_READY → OFFER_SENT
"""
import json
from app.agents.base import BaseAgent
from app.database import Database, QueryHelper
from app.telegram_notifier import get_notifier


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
        source = project.get('source', '')
        is_freelancer = (source == 'freelancer.com')
        freelancer_url = project.get('requirements_doc', '') if is_freelancer else ''

        # Get settings
        prepayment = self._get_prepayment_percentage()
        hourly_rate = self._get_hourly_rate()

        # Get tasks
        tasks = self._get_tasks(project_id)

        self.log_action(project_id, "OFFER_GENERATION_STARTED")

        if is_freelancer:
            prompt = self._freelancer_bid_prompt(
                title, description, tech_stack, estimated_hours,
                quoted_price, hourly_rate, complexity
            )
        else:
            prompt = self._email_proposal_prompt(
                title, description, tech_stack, estimated_hours,
                quoted_price, hourly_rate, prepayment, client_email, complexity, tasks
            )

        try:
            result = self.ai_json(prompt)

            usage = result.pop('_usage', {})
            cost = result.pop('_cost', 0)
            exec_time = result.pop('_execution_time_ms', 0)

            # Get proposal / bid text
            proposal_text = result.get('bid_text', '') or result.get('proposal_text', '')
            if proposal_text:
                self.update_project_field(project_id, 'technical_spec', proposal_text)

            if is_freelancer:
                # Try auto-submit via Selenium; fallback to Telegram
                self._submit_or_notify_bid(
                    project_id, title, quoted_price, freelancer_url, proposal_text
                )
                subject = f'Bid: {title}'
            else:
                # Store as outbound email for sending
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
            from config import Config
            stack_str = ', '.join(tech_stack[:3]) if tech_stack else 'relevant technologies'
            fallback_text = (
                f"Hello,\n\nI'm {Config.BUSINESS_OWNER} from {Config.BUSINESS_NAME}. "
                f"I'm interested in your project \"{title}\".\n"
                f"I have experience with {stack_str} and can complete this "
                f"in approximately {estimated_hours:.0f} hours for ${quoted_price:.0f}.\n"
                f"I'd love to discuss the details.\n\n"
                f"{Config.get_signature()}"
            )
            self.update_project_field(project_id, 'technical_spec', fallback_text)
            if is_freelancer:
                self._submit_or_notify_bid(
                    project_id, title, quoted_price, freelancer_url, fallback_text
                )
            else:
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

    def _submit_or_notify_bid(self, project_id, title, price, url, bid_text):
        """Send bid notification to Telegram for manual submission.
        
        NOTE: Selenium auto-submit disabled — freelancer.com requires
        paid verification to interact with projects.
        """
        from app.telegram_notifier import _esc
        tg = get_notifier()

        try:
            msg = (
                f"📋 <b>Бид готов — проект #{project_id}</b>\n\n"
                f"<b>{_esc(title)}</b>\n"
                f"💰 ${price:.0f}\n"
                f"🔗 <a href=\"{url}\">Открыть</a>\n\n"
                f"<code>{_esc(bid_text[:3000])}</code>"
            )
            tg.send(msg)
        except Exception as e:
            print(f"[OfferGenerator] Telegram bid notify error: {e}")

    def _get_identity(self):
        """Get business identity from config."""
        from config import Config
        return {
            'name': Config.BUSINESS_OWNER,
            'company': Config.BUSINESS_NAME,
            'website': Config.BUSINESS_WEBSITE,
            'email': Config.BUSINESS_EMAIL,
            'phone': Config.BUSINESS_PHONE,
            'address': Config.BUSINESS_ADDRESS,
            'vat': Config.BUSINESS_VAT,
            'signature': Config.get_signature(),
        }

    def _freelancer_bid_prompt(self, title, description, tech_stack, hours, price, hourly_rate, complexity):
        """Generate prompt for freelancer.com bid message."""
        me = self._get_identity()
        return f"""
Generate a concise and compelling bid message for a freelancer.com project.

ABOUT ME:
- Name: {me['name']}, company {me['company']}
- Based in Frankfurt am Main, Germany
- Website: {me['website']}

Project Title: {title}
Description: {description}
Required Skills: {', '.join(tech_stack) if tech_stack else 'Various'}
Complexity: {complexity or 'MEDIUM'}
My Estimation: {hours} hours, ${price}
My Hourly Rate: ${hourly_rate}/hour

Rules:
- 150-300 words, professional but friendly
- Write from MY perspective (I am {me['name']} from {me['company']})
- Show understanding of the project requirements
- Highlight relevant experience with the required tech stack
- Mention proposed timeline
- Include payment terms: {self._get_prepayment_percentage()}% upfront before work begins
- IMPORTANT: Include an invitation to continue detailed discussion via email: {me['email']}
  Example: "For detailed project discussion, feel free to reach me directly at {me['email']}"
- End with invitation to discuss
- Sign off with: {me['name']}, {me['company']} | {me['website']} | {me['email']}

Return JSON:
{{
    "bid_text": "the complete bid message ready to post on freelancer.com",
    "key_selling_points": ["point1", "point2"],
    "confidence": "HIGH or MEDIUM or LOW"
}}
"""

    def _email_proposal_prompt(self, title, description, tech_stack, hours,
                                 price, hourly_rate, prepayment, client_email,
                                 complexity, tasks):
        """Generate prompt for email commercial proposal."""
        me = self._get_identity()
        return f"""
Generate a professional commercial proposal for a freelance project.

ABOUT ME (the freelancer sending this proposal):
- Name: {me['name']}, company {me['company']}
- Address: {me['address']}
- Website: {me['website']}
- Email: {me['email']}
- Phone: {me['phone']}
- VAT ID: {me['vat']}

Project Title: {title}
Description: {description}
Complexity: {complexity}
Tech Stack: {', '.join(tech_stack) if tech_stack else 'To be determined'}
Estimated Hours: {hours}
Quoted Price: ${price}
Hourly Rate: ${hourly_rate}
Prepayment Required: {prepayment}%
Client Email: {client_email}

Task Breakdown:
{json.dumps(tasks, indent=2, default=str) if tasks else 'No detailed breakdown available'}

Generate a complete commercial proposal in plain text (not markdown). The proposal should be professional,
clear, and ready to send to the client via email.

IMPORTANT:
- Write from MY perspective (I am {me['name']} from {me['company']})
- End the proposal with this exact signature block:

{me['signature']}

Return JSON:
{{
    "subject": "email subject line for the proposal",
    "proposal_text": "full text of the proposal email including the signature at the end",
    "summary": {{
        "total_price": {price},
        "prepayment_amount": {price * prepayment / 100},
        "estimated_delivery_days": 14,
        "payment_terms": "50% upfront, 50% on delivery"
    }}
}}
"""
