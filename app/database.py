"""
Database utilities for AI Freelance Operator
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from config import Config


class Database:
    """Database connection manager"""
    
    @staticmethod
    @contextmanager
    def get_connection():
        """Get a database connection context manager"""
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            dbname=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD
        )
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    @staticmethod
    @contextmanager
    def get_cursor(dict_cursor=True):
        """Get a database cursor context manager"""
        with Database.get_connection() as conn:
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
            finally:
                cursor.close()
    
    @staticmethod
    def init_schema():
        """Initialize database schema from schema.sql"""
        import os
        
        # schema.sql is in the project root, not in app/
        schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schema.sql')
        
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        with Database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(schema_sql)
            cursor.close()
        
        print("✓ Database schema initialized successfully")
    
    @staticmethod
    def test_connection():
        """Test database connection"""
        try:
            with Database.get_cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()
                print(f"✓ Database connected: {version['version']}")
                return True
        except Exception as e:
            print(f"✗ Database connection failed: {e}")
            return False


# Query helpers
class QueryHelper:
    """Helper class for common database queries"""
    
    @staticmethod
    def get_system_setting(key, default=None):
        """Get a system setting value"""
        with Database.get_cursor() as cursor:
            cursor.execute(
                "SELECT setting_value, value_type FROM system_settings WHERE setting_key = %s",
                (key,)
            )
            result = cursor.fetchone()
            
            if not result:
                return default
            
            value = result['setting_value']
            value_type = result['value_type']
            
            # Convert to appropriate type
            if value_type == 'integer':
                return int(value)
            elif value_type == 'float':
                return float(value)
            elif value_type == 'boolean':
                return value.lower() == 'true'
            elif value_type == 'json':
                import json
                return json.loads(value)
            else:
                return value
    
    @staticmethod
    def set_system_setting(key, value, value_type='string'):
        """Set a system setting value"""
        with Database.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO system_settings (setting_key, setting_value, value_type, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (setting_key) 
                DO UPDATE SET setting_value = EXCLUDED.setting_value, 
                             updated_at = CURRENT_TIMESTAMP
                """,
                (key, str(value), value_type)
            )
    
    @staticmethod
    def log_agent_action(agent_name, action, project_id=None, input_data=None, 
                        output_data=None, success=True, error_message=None,
                        execution_time_ms=None, tokens_used=None, cost=None):
        """Log an agent action"""
        import json
        
        with Database.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_logs 
                (agent_name, project_id, action, input_data, output_data, 
                 success, error_message, execution_time_ms, tokens_used, cost)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    agent_name, 
                    project_id, 
                    action,
                    json.dumps(input_data) if input_data else None,
                    json.dumps(output_data) if output_data else None,
                    success,
                    error_message,
                    execution_time_ms,
                    tokens_used,
                    cost
                )
            )
            return cursor.fetchone()['id']
