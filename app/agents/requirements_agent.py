"""
Requirements Analysis Agent вЂ” evaluates clarity and completeness of project specifications.
Stage: CLASSIFIED в†’ REQUIREMENTS_ANALYZED  (clarity >= threshold)
       CLASSIFIED в†’ CLARIFICATION_NEEDED   (clarity < threshold, questions sent to client)

When a project is in CLARIFICATION_NEEDED and the client replies,
MailWorker moves it back to CLASSIFIED and this agent re-runs with new info.
After max_rounds clarification attempts the agent proceeds anyway.

The output is sent to the owner via Telegram so they can track progress.
"""
import json
from app.agents.base import BaseAgent
from app.database import Database
from app.telegram_notifier import get_notifier


# Max clarification rounds before we proceed regardless
MAX_CLARIFICATION_ROUNDS = 3


class RequirementsAnalysisAgent(BaseAgent):
    """
    Analyses whether the project brief is clear enough to estimate confidently.
    If clarity is low and rounds remain, sends questions and waits for reply.
    """

    CLARITY_THRESHOLD = 6

    def process(self, project_data):
        project_id = project_data['id']

        project = self.get_project(project_id)
        if not project:
            return None

        title = project.get('title', '')
        description = project.get('description', '') or ''
        tech_stack = project.get('tech_stack', [])
        complexity = project.get('complexity', 'MEDIUM')
        budget_min = project.get('budget_min')
        budget_max = project.get('budget_max')
        source = project.get('source', '')
        requirements_doc = project.get('requirements_doc', '') or ''
        client_email = project.get('client_email', '')
        technical_spec_raw = project.get('technical_spec', '') or ''

        # в”Ђв”Ђ Track clarification round в”Ђв”Ђ
        previous_analysis = {}
        clarification_round = 0
        try:
            if technical_spec_raw:
                previous_analysis = json.loads(technical_spec_raw)
                clarification_round = int(previous_analysis.get('clarification_round', 0))
        except (json.JSONDecodeError, TypeError):
            pass

        # Get conversation history (client replies after clarification questions)
        client_replies = self._get_client_replies(project_id)

        self.log_action(project_id, "REQUIREMENTS_ANALYSIS_STARTED",
                        input_data={'round': clarification_round + 1})

        prompt = self._build_prompt(
            title, description, tech_stack, complexity,
            budget_min, budget_max, requirements_doc,
            previous_analysis, client_replies, clarification_round
        )

        try:
            result = self.ai_json(prompt)

            usage = result.pop('_usage', {})
            cost = result.pop('_cost', 0)
            exec_time = result.pop('_execution_time_ms', 0)

            clarity_score = float(result.get('clarity_score', 5))
            questions = result.get('clarifying_questions', [])
            gaps = result.get('requirement_gaps', [])
            assumptions = result.get('assumptions', [])
            feasibility = result.get('feasibility_assessment', '')
            scope_summary = result.get('scope_summary', '')
            risks = result.get('risks', [])
            recommendations = result.get('recommendations', '')

            # Build structured analysis doc (preserving round counter)
            analysis_doc = {
                'clarity_score': clarity_score,
                'clarification_round': clarification_round + 1,
                'clarifying_questions': questions,
                'requirement_gaps': gaps,
                'assumptions': assumptions,
                'feasibility_assessment': feasibility,
                'scope_summary': scope_summary,
                'risks': risks,
                'recommendations': recommendations,
            }

            self.update_project_fields(
                project_id,
                technical_spec=json.dumps(analysis_doc, ensure_ascii=False),
            )

            self.log_action(
                project_id, "REQUIREMENTS_ANALYSIS_COMPLETED",
                output_data=result,
                execution_time_ms=exec_time,
                tokens_used=usage.get('total_tokens'),
                cost=cost,
            )

            # в”Ђв”Ђ Decision: clear enough or need clarification? в”Ђв”Ђ
            needs_clarification = (
                clarity_score < self.CLARITY_THRESHOLD
                and questions
                and clarification_round < MAX_CLARIFICATION_ROUNDS
            )

            if needs_clarification:
                # Send questions to client
                self._send_clarification_questions(
                    project_id, title, questions, source, client_email,
                    requirements_doc, clarification_round + 1
                )

                # Telegram notification
                self._send_telegram_analysis(
                    project_id, title, clarity_score,
                    questions, gaps, feasibility, scope_summary, risks,
                    source, requirements_doc,
                    waiting_for_client=True,
                    round_num=clarification_round + 1,
                )

                self.log_state_transition(
                    project_id, 'CLASSIFIED', 'CLARIFICATION_NEEDED',
                    f"Clarity {clarity_score}/10, round {clarification_round + 1}/{MAX_CLARIFICATION_ROUNDS} вЂ” waiting for client"
                )
                return "CLARIFICATION_NEEDED"

            else:
                # Clear enough (or max rounds reached) — proceed to estimation
                if clarity_score < self.CLARITY_THRESHOLD:
                    note = f"Clarity {clarity_score}/10 still low after {clarification_round + 1} rounds — proceeding with assumptions"
                else:
                    note = f"Clarity {clarity_score}/10 — requirements sufficient"

                # Send initial acknowledgment with payment terms (first round only)
                if clarification_round == 0:
                    self._send_initial_terms(
                        project_id, title, source, client_email, requirements_doc
                    )

                self._send_telegram_analysis(
                    project_id, title, clarity_score,
                    questions, gaps, feasibility, scope_summary, risks,
                    source, requirements_doc,
                    waiting_for_client=False,
                    round_num=clarification_round + 1,
                )

                self.log_state_transition(
                    project_id, 'CLASSIFIED', 'REQUIREMENTS_ANALYZED', note
                )
                return "REQUIREMENTS_ANALYZED"

        except Exception as e:
            self.log_action(
                project_id, "REQUIREMENTS_ANALYSIS_FAILED",
                error_message=str(e), success=False,
            )
            fallback = {
                'clarity_score': 5,
                'clarification_round': clarification_round + 1,
                'clarifying_questions': [],
                'requirement_gaps': ['Analysis failed вЂ” review manually'],
                'feasibility_assessment': 'Unknown (analysis error)',
                'scope_summary': description[:500],
            }
            self.update_project_fields(
                project_id,
                technical_spec=json.dumps(fallback, ensure_ascii=False),
            )
            self.log_state_transition(
                project_id, 'CLASSIFIED', 'REQUIREMENTS_ANALYZED',
                'Requirements analysis failed вЂ” using fallback',
            )
            return "REQUIREMENTS_ANALYZED"

    # в”Ђв”Ђв”Ђ Client replies в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

    def _get_client_replies(self, project_id):
        """Get all inbound messages (client replies) for context."""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    SELECT body, created_at
                    FROM project_messages
                    WHERE project_id = %s AND direction = 'inbound'
                    ORDER BY created_at ASC
                """, (project_id,))
                rows = cursor.fetchall()
                return [r['body'] for r in rows if r.get('body')]
        except Exception:
            return []

    # в”Ђв”Ђв”Ђ Send clarification questions в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

    # ─── Send initial terms (for clear specs, no questions needed) ────

    def _send_initial_terms(self, project_id, title, source, client_email, freelancer_url):
        """Send a brief acknowledgment with payment terms before estimation begins."""
        from config import Config

        hourly_rate = Config.HOURLY_RATE
        prepayment = Config.PREPAYMENT_PERCENTAGE

        message_body = (
            f"Hello,\n\n"
            f"Thank you for your project \"{title}\". "
            f"I have reviewed the requirements and they are clear enough to proceed.\n\n"
            f"Before I prepare a detailed estimate, I would like to confirm our standard terms:\n\n"
            f"- Hourly rate: ${hourly_rate}/hour\n"
            f"- Payment: {prepayment}% upfront before work begins, "
            f"{100 - prepayment}% upon delivery\n"
            f"- I will send you a detailed proposal with exact pricing and timeline shortly\n\n"
            f"If these terms work for you, no action is needed — "
            f"I will follow up with the full proposal.\n"
            f"If you have any questions about the terms, feel free to reply.\n\n"
            f"{Config.get_signature()}"
        )

        if source == 'freelancer.com':
            tg = get_notifier()
            copy_text = (
                f"Hi! Thank you for posting \"{title}\". I have reviewed the requirements "
                f"and I am ready to submit a detailed proposal.\n\n"
                f"Our terms: ${hourly_rate}/hour, {prepayment}% upfront before work "
                f"begins. I will send the full estimate shortly.\n\n"
                f"Looking forward to working with you!"
            )
            msg = (
                f"\U0001f4b0 <b>Условия отправлены — проект #{project_id}</b>\n"
                f"<b>{_esc(title)}</b>\n\n"
                f"<b>Текст для копирования заказчику:</b>\n"
                f"<code>{_esc(copy_text)}</code>"
            )
            if freelancer_url:
                msg += f"\n\n\U0001f517 <a href=\"{freelancer_url}\">Открыть на Freelancer</a>"
            tg.send(msg[:4096])

        elif client_email:
            try:
                from app.database import QueryHelper
                mail_username = QueryHelper.get_system_setting('mail_username', Config.BUSINESS_EMAIL)
                with Database.get_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO project_messages
                        (project_id, direction, sender_email, recipient_email, subject, body, is_processed)
                        VALUES (%s, 'outbound', %s, %s, %s, %s, FALSE)
                    """, (
                        project_id, mail_username, client_email,
                        f"Re: {title} — Terms and Next Steps",
                        message_body
                    ))
                print(f"[RequirementsAgent] Initial terms email queued for project #{project_id}")
            except Exception as e:
                print(f"[RequirementsAgent] Error queuing terms email: {e}")


    def _send_clarification_questions(self, project_id, title, questions,
                                       source, client_email, freelancer_url,
                                       round_num):
        """Send clarification questions to the client (email or Telegram)."""
        from config import Config

        q_text = '\n'.join(f"{i+1}. {q}" for i, q in enumerate(questions[:8]))
        hourly_rate = Config.HOURLY_RATE
        prepayment = Config.PREPAYMENT_PERCENTAGE

        terms_block = (
            f"Our standard terms:\n"
            f"- Hourly rate: ${hourly_rate}/hour\n"
            f"- Payment: {prepayment}% upfront before work begins, "
            f"{100 - prepayment}% upon delivery\n"
            f"- A detailed estimate with timeline will follow after we clarify the scope\n"
        )

        message_body = (
            f"Hello,\n\n"
            f"Thank you for your project \"{title}\". I'm very interested and would like "
            f"to provide you with an accurate estimate.\n\n"
            f"{terms_block}\n"
            f"Before I proceed, I have a few questions to clarify the scope:\n\n"
            f"{q_text}\n\n"
            f"Looking forward to your response.\n\n"
            f"{Config.get_signature()}"
        )

        if source == 'freelancer.com':
            # Freelancer projects: send via Telegram (no client email available)
            self._send_freelancer_clarification_tg(
                project_id, title, questions, freelancer_url, round_num
            )
        elif client_email:
            # Email projects: store as outbound message for sending
            try:
                from app.database import QueryHelper
                mail_username = QueryHelper.get_system_setting('mail_username', Config.BUSINESS_EMAIL)
                with Database.get_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO project_messages
                        (project_id, direction, sender_email, recipient_email, subject, body, is_processed)
                        VALUES (%s, 'outbound', %s, %s, %s, %s, FALSE)
                    """, (
                        project_id, mail_username, client_email,
                        f"Clarification questions: {title}",
                        message_body
                    ))
                print(f"[RequirementsAgent] Clarification email queued for project #{project_id}")
            except Exception as e:
                print(f"[RequirementsAgent] Error queuing clarification email: {e}")

    def _send_freelancer_clarification_tg(self, project_id, title, questions,
                                           freelancer_url, round_num):
        """Send clarification questions via Telegram for freelancer projects."""
        tg = get_notifier()
        q_text = '\n'.join(f"  {i+1}. {_esc(q)}" for i, q in enumerate(questions[:8]))

        msg = (
            f"вќ“ <b>Р’РѕРїСЂРѕСЃС‹ РґР»СЏ СѓС‚РѕС‡РЅРµРЅРёСЏ вЂ” РїСЂРѕРµРєС‚ #{project_id}</b>\n"
            f"<b>Р Р°СѓРЅРґ:</b> {round_num}/{MAX_CLARIFICATION_ROUNDS}\n\n"
            f"<b>{_esc(title)}</b>\n\n"
            f"<b>РћС‚РїСЂР°РІСЊС‚Рµ СЌС‚Рё РІРѕРїСЂРѕСЃС‹ Р·Р°РєР°Р·С‡РёРєСѓ:</b>\n{q_text}\n\n"
            f"<b>РўРµРєСЃС‚ РґР»СЏ РєРѕРїРёСЂРѕРІР°РЅРёСЏ:</b>\n"
            f"<code>{_esc(self._questions_copy_text(title, questions))}</code>"
        )
        if freelancer_url:
            msg += f"\n\nрџ”— <a href=\"{freelancer_url}\">РћС‚РєСЂС‹С‚СЊ РЅР° Freelancer</a>"

        tg.send(msg[:4096])

    def _questions_copy_text(self, title, questions):
        """Plain text version of questions for copy-pasting to freelancer chat."""
        from config import Config
        q_text = '\n'.join(f"{i+1}. {q}" for i, q in enumerate(questions[:8]))
        return (
            f"Hi! Thank you for posting \"{title}\". I'm very interested in this project.\n\n"
            f"Our terms: ${Config.HOURLY_RATE}/hour, {Config.PREPAYMENT_PERCENTAGE}% upfront "
            f"before work begins. A detailed estimate will follow once we agree on scope.\n\n"
            f"Before I submit my detailed proposal, I have a few questions:\n\n"
            f"{q_text}\n\n"
            f"Looking forward to your answers!"
        )

    # в”Ђв”Ђв”Ђ Prompt в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

    def _build_prompt(self, title, description, tech_stack, complexity,
                      budget_min, budget_max, requirements_doc,
                      previous_analysis, client_replies, round_num):
        stack_str = ', '.join(tech_stack) if tech_stack else 'Not specified'
        budget_str = f"{budget_min or '?'} вЂ“ {budget_max or '?'}"

        # Add previous analysis context if this is a re-analysis
        prev_context = ''
        if round_num > 0 and previous_analysis:
            prev_q = previous_analysis.get('clarifying_questions', [])
            prev_gaps = previous_analysis.get('requirement_gaps', [])
            prev_score = previous_analysis.get('clarity_score', '?')
            prev_context = f"""
в”Ђв”Ђв”Ђ PREVIOUS ANALYSIS (round {round_num}) в”Ђв”Ђв”Ђ
Previous clarity score: {prev_score}/10
Questions asked: {json.dumps(prev_q, ensure_ascii=False)}
Gaps identified: {json.dumps(prev_gaps, ensure_ascii=False)}
"""

        replies_context = ''
        if client_replies:
            replies_text = '\n---\n'.join(r[:500] for r in client_replies[-3:])
            replies_context = f"""
в”Ђв”Ђв”Ђ CLIENT REPLIES в”Ђв”Ђв”Ђ
{replies_text}
"""

        return f"""
You are an expert freelance project analyst. Your job is to evaluate the clarity
and completeness of a project brief BEFORE it is estimated and bid on.

This is analysis round {round_num + 1}.

в”Ђв”Ђв”Ђ PROJECT INFO в”Ђв”Ђв”Ђ
Title: {title}
Description:
{description}

Tech Stack: {stack_str}
Complexity: {complexity}
Budget range: {budget_str}
Additional info: {requirements_doc or 'вЂ”'}
{prev_context}{replies_context}
в”Ђв”Ђв”Ђ YOUR TASK в”Ђв”Ђв”Ђ
Perform a thorough requirements analysis. If client replies are provided above,
incorporate their answers into your assessment вЂ” the clarity score should IMPROVE
if the client answered well.

Return a JSON object with:

1. **clarity_score** (float 0-10):
   - 0-3: Very vague, almost impossible to estimate accurately
   - 4-5: Incomplete, significant gaps
   - 6-7: Workable but would benefit from clarification
   - 8-10: Clear and well-defined

2. **scope_summary** (string): A concise 2-4 sentence summary of what the project
   actually needs (in your own words, not just a copy of the description).

3. **requirement_gaps** (list of strings): Specific pieces of information that are
   STILL MISSING. Only list gaps that haven't been answered yet.

4. **clarifying_questions** (list of strings): Smart, specific questions to ask the
   client to fill the remaining gaps. Limit to 5-8 MOST IMPORTANT. Skip questions
   the client has already answered.

5. **assumptions** (list of strings): Reasonable assumptions you can make given
   available info. Include confirmed facts from client replies.

6. **risks** (list of strings): Technical or project risks visible from the brief.

7. **feasibility_assessment** (string): Is this project feasible with the described
   stack and budget?

8. **recommendations** (string): Should the freelancer bid? Any concerns?

Return ONLY valid JSON:
{{
    "clarity_score": 7.0,
    "scope_summary": "...",
    "requirement_gaps": ["...", "..."],
    "clarifying_questions": ["...", "..."],
    "assumptions": ["...", "..."],
    "risks": ["...", "..."],
    "feasibility_assessment": "...",
    "recommendations": "..."
}}
"""

    # в”Ђв”Ђв”Ђ Telegram в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

    def _send_telegram_analysis(self, project_id, title, clarity_score,
                                 questions, gaps, feasibility, scope_summary,
                                 risks, source, url,
                                 waiting_for_client=False, round_num=1):
        tg = get_notifier()

        if clarity_score >= 8:
            clarity_icon = 'рџџў'
        elif clarity_score >= 6:
            clarity_icon = 'рџџЎ'
        else:
            clarity_icon = 'рџ”ґ'

        status = "вЏі Р–РґС‘Рј РѕС‚РІРµС‚ РєР»РёРµРЅС‚Р°" if waiting_for_client else "вњ… РўР— РїСЂРёРЅСЏС‚Рѕ"

        parts = [
            f"рџ“‹ <b>РђРЅР°Р»РёР· РўР— вЂ” РїСЂРѕРµРєС‚ #{project_id}</b> (СЂР°СѓРЅРґ {round_num})\n",
            f"<b>РЎС‚Р°С‚СѓСЃ:</b> {status}",
            f"<b>РќР°Р·РІР°РЅРёРµ:</b> {_esc(title)}",
            f"<b>РЇСЃРЅРѕСЃС‚СЊ РўР—:</b> {clarity_icon} {clarity_score}/10",
        ]

        if scope_summary:
            parts.append(f"\n<b>РЎСѓС‚СЊ РїСЂРѕРµРєС‚Р°:</b>\n<i>{_esc(scope_summary[:400])}</i>")

        if gaps:
            gaps_text = '\n'.join(f"  вЂў {_esc(g)}" for g in gaps[:6])
            parts.append(f"\n<b>РџСЂРѕР±РµР»С‹ РІ РўР—:</b>\n{gaps_text}")

        if questions and waiting_for_client:
            q_text = '\n'.join(f"  {i+1}. {_esc(q)}" for i, q in enumerate(questions[:8]))
            parts.append(f"\n<b>Р’РѕРїСЂРѕСЃС‹ РєР»РёРµРЅС‚Сѓ:</b>\n{q_text}")

        if risks:
            r_text = '\n'.join(f"  вљ пёЏ {_esc(r)}" for r in risks[:4])
            parts.append(f"\n<b>Р РёСЃРєРё:</b>\n{r_text}")

        if feasibility:
            parts.append(f"\n<b>РћС†РµРЅРєР°:</b> {_esc(feasibility[:300])}")

        if source == 'freelancer.com' and url:
            parts.append(f"\nрџ”— <a href=\"{url}\">РћС‚РєСЂС‹С‚СЊ РЅР° Freelancer</a>")

        text = '\n'.join(parts)
        tg.send(text[:4096])


def _esc(text: str) -> str:
    if not text:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))
