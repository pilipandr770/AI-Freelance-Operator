from abc import ABC, abstractmethod
from app.ai_client import AIClient
from app.database import Database

class BaseAgent(ABC):
    def __init__(self):
        self.ai_client = AIClient()

    @abstractmethod
    def process(self, project_data):
        """
        Process a project and return the next stage

        Args:
            project_data (dict): Project information including id, stage, description, etc.

        Returns:
            str: Next stage name, or None to stay in current stage
        """
        pass

    def log_action(self, project_id, action, input_data=None, output_data=None, success=True, error_message=None, execution_time_ms=None, tokens_used=None, cost=None):
        """Log agent action to database"""
        with Database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agent_logs (agent_name, project_id, action, input_data, output_data, success, error_message, execution_time_ms, tokens_used, cost, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (self.__class__.__name__, project_id, action, input_data, output_data, success, error_message, execution_time_ms, tokens_used, cost))

    def update_project_field(self, project_id, field, value):
        """Update a specific field in the project"""
        with Database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE projects SET {field} = %s, updated_at = NOW()
                WHERE id = %s
            """, (value, project_id))