import time
import threading
from app.database import Database
from app.agents.intake_agent import IntakeAgent
from app.agents.classification_agent import ClassificationAgent

class WorkflowEngine:
    def __init__(self):
        self.agents = {
            'NEW': IntakeAgent(),
            'ANALYZED': ClassificationAgent(),
            # Add more states and agents as needed
        }
        self.running = False

    def start(self):
        """Start the workflow processing loop"""
        self.running = True
        thread = threading.Thread(target=self._process_loop, daemon=True)
        thread.start()
        print("Workflow engine started")

    def stop(self):
        """Stop the workflow processing"""
        self.running = False

    def _process_loop(self):
        """Main processing loop that runs every 10-20 seconds"""
        while self.running:
            try:
                self._process_pending_projects()
            except Exception as e:
                print(f"Workflow engine error: {e}")
            time.sleep(15)  # Process every 15 seconds

    def _process_pending_projects(self):
        """Find projects that need processing and run appropriate agents"""
        with Database.get_connection() as conn:
            cursor = conn.cursor()

            # Get projects that are not completed
            cursor.execute("""
                SELECT id, current_state, client_email, description, tech_stack, budget_min, budget_max
                FROM projects
                WHERE current_state NOT IN ('CLOSED', 'REJECTED')
                ORDER BY created_at ASC
            """)

            projects = cursor.fetchall()

            for project in projects:
                project_id, current_state, client_email, description, tech_stack, budget_min, budget_max = project
                agent = self.agents.get(current_state)

                if agent:
                    print(f"Processing project {project_id} at stage {current_state}")
                    try:
                        new_state = agent.process({
                            'id': project_id,
                            'current_state': current_state,
                            'client_email': client_email,
                            'description': description,
                            'tech_stack': tech_stack,
                            'budget_min': budget_min,
                            'budget_max': budget_max
                        })

                        if new_state and new_state != current_state:
                            # Update project state
                            cursor.execute("""
                                UPDATE projects SET current_state = %s, updated_at = NOW()
                                WHERE id = %s
                            """, (new_state, project_id))
                            print(f"Project {project_id} moved to state {new_state}")

                    except Exception as e:
                        print(f"Error processing project {project_id}: {e}")
                        # Could add error handling, like marking as failed