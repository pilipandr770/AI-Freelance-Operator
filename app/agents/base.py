from abc import ABC, abstractmethod
import json
import re
from app.ai_client import get_ai_client
from app.database import Database


class BaseAgent(ABC):
    """Base class for all AI agents in the workflow pipeline"""

    def __init__(self):
        self._ai_client = None

    @property
    def ai_client(self):
        """Lazy-load AI client to avoid import-time errors"""
        if self._ai_client is None:
            self._ai_client = get_ai_client()
        return self._ai_client

    @property
    def agent_name(self):
        """Return snake_case agent name for DB lookups"""
        name = self.__class__.__name__
        return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

    @abstractmethod
    def process(self, project_data):
        """
        Process a project and return the next state.

        Args:
            project_data (dict): Project info (id, current_state, description, etc.)

        Returns:
            str: Next state name, or None to stay in current state
        """
        pass

    def get_instructions(self):
        """Load agent instructions and system prompt from database"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    SELECT instruction_text, system_prompt 
                    FROM agent_instructions 
                    WHERE agent_name = %s AND is_active = TRUE
                """, (self.agent_name,))
                result = cursor.fetchone()
                if result:
                    return {
                        'instruction_text': result['instruction_text'],
                        'system_prompt': result['system_prompt']
                    }
        except Exception:
            pass
        return {'instruction_text': '', 'system_prompt': ''}

    def ai_call(self, prompt, system_prompt=None, expect_json=False):
        """Make an AI call. If system_prompt is None, loads from DB."""
        if system_prompt is None:
            instructions = self.get_instructions()
            system_prompt = instructions.get('system_prompt', '')

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        if expect_json:
            return self.ai_client.chat_completion(messages, response_format={"type": "json_object"})
        return self.ai_client.chat_completion(messages)

    def ai_json(self, prompt, system_prompt=None):
        """Make an AI call and return parsed JSON dict."""
        result = self.ai_call(prompt, system_prompt=system_prompt, expect_json=True)
        content = result.get('content', '')
        parsed = self.ai_client.parse_json_response(content)
        if parsed is None:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = {}
        parsed['_usage'] = result.get('usage', {})
        parsed['_cost'] = result.get('cost', 0)
        parsed['_execution_time_ms'] = result.get('execution_time_ms', 0)
        return parsed

    def log_action(self, project_id, action, input_data=None, output_data=None,
                   success=True, error_message=None, execution_time_ms=None,
                   tokens_used=None, cost=None):
        """Log agent action to database"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO agent_logs 
                    (agent_name, project_id, action, input_data, output_data, 
                     success, error_message, execution_time_ms, tokens_used, cost, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    self.agent_name, project_id, action,
                    json.dumps(input_data) if isinstance(input_data, (dict, list)) else input_data,
                    json.dumps(output_data) if isinstance(output_data, (dict, list)) else output_data,
                    success, error_message, execution_time_ms, tokens_used, cost
                ))
        except Exception as e:
            print(f"Failed to log agent action: {e}")

    def log_state_transition(self, project_id, from_state, to_state, reason=None, metadata=None):
        """Log a project state transition"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO project_states (project_id, from_state, to_state, changed_by, reason, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    project_id, from_state, to_state, self.agent_name, reason,
                    json.dumps(metadata) if metadata else None
                ))
        except Exception as e:
            print(f"Failed to log state transition: {e}")

    def update_project_field(self, project_id, field, value):
        """Update a specific field in the project"""
        allowed = [
            'title', 'description', 'category', 'complexity', 'tech_stack',
            'is_familiar_stack', 'budget_min', 'budget_max', 'estimated_hours',
            'quoted_price', 'final_price', 'current_state', 'is_scam', 'is_illegal',
            'scam_score', 'requirements_doc', 'technical_spec', 'rejection_reason',
            'client_id', 'client_email'
        ]
        if field not in allowed:
            raise ValueError(f"Field '{field}' is not allowed for update")
        with Database.get_cursor() as cursor:
            cursor.execute(f"UPDATE projects SET {field} = %s, updated_at = NOW() WHERE id = %s", (value, project_id))

    def update_project_fields(self, project_id, **fields):
        """Update multiple fields at once"""
        allowed = [
            'title', 'description', 'category', 'complexity', 'tech_stack',
            'is_familiar_stack', 'budget_min', 'budget_max', 'estimated_hours',
            'quoted_price', 'final_price', 'current_state', 'is_scam', 'is_illegal',
            'scam_score', 'requirements_doc', 'technical_spec', 'rejection_reason',
            'client_id', 'client_email'
        ]
        set_clauses = []
        values = []
        for field, value in fields.items():
            if field in allowed:
                set_clauses.append(f"{field} = %s")
                values.append(value)
        if not set_clauses:
            return
        set_clauses.append("updated_at = NOW()")
        values.append(project_id)
        with Database.get_cursor() as cursor:
            cursor.execute(f"UPDATE projects SET {', '.join(set_clauses)} WHERE id = %s", tuple(values))

    def get_project(self, project_id):
        """Get full project data from database"""
        with Database.get_cursor() as cursor:
            cursor.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
            return cursor.fetchone()