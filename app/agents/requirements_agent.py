"""
Requirements Analysis Agent — evaluates clarity and completeness of project specifications.
Stage: CLASSIFIED → REQUIREMENTS_ANALYZED

This is the most intellectually demanding agent in the pipeline.
It performs deep analysis of technical requirements:
  - Evaluates specification clarity (0-10 score)
  - Identifies ambiguities, gaps, and hidden risks
  - Generates smart clarifying questions
  - Assesses feasibility with the available info
  - Produces a structured requirements summary for downstream agents

The output is sent to the owner via Telegram so they can ask
clarifying questions on the freelancer.com platform (or by email).
"""
import json
from app.agents.base import BaseAgent
from app.telegram_notifier import get_notifier


class RequirementsAnalysisAgent(BaseAgent):
    """
    Analyses whether the project brief is clear enough to estimate confidently.
    If clarity is low, generates questions the freelancer should ask before bidding.
    """

    # Below this score the agent flags the project for clarification
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

        self.log_action(project_id, "REQUIREMENTS_ANALYSIS_STARTED")

        prompt = self._build_prompt(
            title, description, tech_stack, complexity,
            budget_min, budget_max, requirements_doc
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

            # Build structured analysis doc
            analysis_doc = {
                'clarity_score': clarity_score,
                'clarifying_questions': questions,
                'requirement_gaps': gaps,
                'assumptions': assumptions,
                'feasibility_assessment': feasibility,
                'scope_summary': scope_summary,
                'risks': risks,
                'recommendations': recommendations,
            }

            # Store analysis in technical_spec field (JSON)
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

            # ── Telegram notification ──
            self._send_telegram_analysis(
                project_id, title, clarity_score,
                questions, gaps, feasibility, scope_summary, risks,
                source, requirements_doc,
            )

            self.log_state_transition(
                project_id, 'CLASSIFIED', 'REQUIREMENTS_ANALYZED',
                f"Clarity: {clarity_score}/10, questions: {len(questions)}, gaps: {len(gaps)}"
            )
            return "REQUIREMENTS_ANALYZED"

        except Exception as e:
            self.log_action(
                project_id, "REQUIREMENTS_ANALYSIS_FAILED",
                error_message=str(e), success=False,
            )
            # Fallback — still advance so pipeline doesn't stall
            fallback = {
                'clarity_score': 5,
                'clarifying_questions': [],
                'requirement_gaps': ['Analysis failed — review manually'],
                'feasibility_assessment': 'Unknown (analysis error)',
                'scope_summary': description[:500],
            }
            self.update_project_fields(
                project_id,
                technical_spec=json.dumps(fallback, ensure_ascii=False),
            )
            self.log_state_transition(
                project_id, 'CLASSIFIED', 'REQUIREMENTS_ANALYZED',
                'Requirements analysis failed — using fallback',
            )
            return "REQUIREMENTS_ANALYZED"

    # ─── Prompt ───────────────────────────────────────────────

    def _build_prompt(self, title, description, tech_stack, complexity,
                      budget_min, budget_max, requirements_doc):
        stack_str = ', '.join(tech_stack) if tech_stack else 'Not specified'
        budget_str = f"{budget_min or '?'} – {budget_max or '?'}"

        return f"""
You are an expert freelance project analyst. Your job is to evaluate the clarity
and completeness of a project brief BEFORE it is estimated and bid on.

─── PROJECT INFO ───
Title: {title}
Description:
{description}

Tech Stack: {stack_str}
Complexity: {complexity}
Budget range: {budget_str}
Additional info: {requirements_doc or '—'}

─── YOUR TASK ───
Perform a thorough requirements analysis. Return a JSON object with:

1. **clarity_score** (float 0-10):
   - 0-3: Very vague, almost impossible to estimate accurately
   - 4-5: Incomplete, significant gaps
   - 6-7: Workable but would benefit from clarification
   - 8-10: Clear and well-defined

2. **scope_summary** (string): A concise 2-4 sentence summary of what the project
   actually needs (in your own words, not just a copy of the description).

3. **requirement_gaps** (list of strings): Specific pieces of information that are
   MISSING from the brief. Examples:
   - "No mention of target platforms (web / mobile / desktop)"
   - "Database choice not specified"
   - "No acceptance criteria for search functionality"

4. **clarifying_questions** (list of strings): Smart, specific questions to ask the
   client to fill the gaps. Limit to the 5-8 MOST IMPORTANT questions.
   They should be practical and answerable, not generic.

5. **assumptions** (list of strings): Reasonable assumptions you can make if the
   client doesn't answer. Each assumption should be something a senior developer
   would consider a safe default.

6. **risks** (list of strings): Technical or project risks visible from the brief.
   Focus on implementation risks, not business risks.

7. **feasibility_assessment** (string): A short assessment — is this project
   feasible with the described stack and budget? Any red flags?

8. **recommendations** (string): Your recommendation for the freelancer —
   should they bid? Any concerns? What to highlight in the proposal?

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

    # ─── Telegram ─────────────────────────────────────────────

    def _send_telegram_analysis(self, project_id, title, clarity_score,
                                 questions, gaps, feasibility, scope_summary,
                                 risks, source, url):
        tg = get_notifier()

        # Clarity emoji
        if clarity_score >= 8:
            clarity_icon = '🟢'
        elif clarity_score >= 6:
            clarity_icon = '🟡'
        else:
            clarity_icon = '🔴'

        parts = [
            f"📋 <b>Анализ ТЗ — проект #{project_id}</b>\n",
            f"<b>Название:</b> {_esc(title)}",
            f"<b>Ясность ТЗ:</b> {clarity_icon} {clarity_score}/10",
        ]

        if scope_summary:
            parts.append(f"\n<b>Суть проекта:</b>\n<i>{_esc(scope_summary[:400])}</i>")

        if gaps:
            gaps_text = '\n'.join(f"  • {_esc(g)}" for g in gaps[:6])
            parts.append(f"\n<b>Пробелы в ТЗ:</b>\n{gaps_text}")

        if questions:
            q_text = '\n'.join(f"  {i+1}. {_esc(q)}" for i, q in enumerate(questions[:8]))
            parts.append(f"\n<b>Вопросы клиенту:</b>\n{q_text}")

        if risks:
            r_text = '\n'.join(f"  ⚠️ {_esc(r)}" for r in risks[:4])
            parts.append(f"\n<b>Риски:</b>\n{r_text}")

        if feasibility:
            parts.append(f"\n<b>Оценка:</b> {_esc(feasibility[:300])}")

        if source == 'freelancer.com' and url:
            parts.append(f"\n🔗 <a href=\"{url}\">Открыть на Freelancer</a>")

        text = '\n'.join(parts)
        tg.send(text[:4096])


# Re-use Telegram HTML escaping
def _esc(text: str) -> str:
    if not text:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))
