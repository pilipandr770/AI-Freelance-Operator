"""
Workflow Engine — the core of the AI Freelance Operator.

Orchestrates the project lifecycle through state transitions:
  NEW → PARSED → ANALYZED → CLASSIFIED → ESTIMATION_READY → OFFER_SENT → NEGOTIATION → AGREED → CLOSED
                      ↘ REJECTED (at any scam/illegal check)

Each state has an assigned agent that processes projects in that state
and returns the next state.
"""
import time
import threading
import json
from app.database import Database
from app.agents.email_parser_agent import EmailParserAgent
from app.agents.scam_filter_agent import ScamFilterAgent
from app.agents.classification_agent import ClassificationAgent
from app.agents.estimation_agent import EstimationAgent
from app.agents.offer_generator_agent import OfferGeneratorAgent
from app.agents.dialogue_orchestrator_agent import DialogueOrchestratorAgent


# Terminal states — no further processing
TERMINAL_STATES = {'CLOSED', 'REJECTED'}

# States that require human action (no auto-processing)
MANUAL_STATES = {'AGREED', 'FUNDED', 'EXECUTION_READY'}


class WorkflowEngine:
    """
    Main workflow processor. Runs in a background thread,
    polls the database for projects in processable states,
    and runs the appropriate agent for each.
    """

    def __init__(self):
        # Map: current_state → agent instance
        self.agents = {
            'NEW':              EmailParserAgent(),
            'PARSED':           ScamFilterAgent(),
            'ANALYZED':         ClassificationAgent(),
            'CLASSIFIED':       EstimationAgent(),
            'ESTIMATION_READY': OfferGeneratorAgent(),
            'NEGOTIATION':      DialogueOrchestratorAgent(),
        }
        self.running = False
        self.process_interval = 15  # seconds between processing cycles
        self._lock = threading.Lock()

    def start(self):
        """Start the workflow processing loop in current thread"""
        self.running = True
        print(f"[WorkflowEngine] Started. Processing states: {list(self.agents.keys())}")
        print(f"[WorkflowEngine] Terminal states: {TERMINAL_STATES}")
        print(f"[WorkflowEngine] Manual states (no auto-processing): {MANUAL_STATES}")
        self._process_loop()

    def stop(self):
        """Stop the workflow processing"""
        self.running = False
        print("[WorkflowEngine] Stopped")

    def _process_loop(self):
        """Main processing loop"""
        while self.running:
            try:
                processed = self._process_pending_projects()
                if processed > 0:
                    print(f"[WorkflowEngine] Processed {processed} project(s)")
            except Exception as e:
                print(f"[WorkflowEngine] Error in processing loop: {e}")
            time.sleep(self.process_interval)

    def _process_pending_projects(self):
        """Find and process all projects in processable states"""
        processable_states = list(self.agents.keys())
        processed_count = 0

        try:
            with Database.get_cursor() as cursor:
                # Get projects in states we can process
                placeholders = ', '.join(['%s'] * len(processable_states))
                cursor.execute(f"""
                    SELECT id, current_state, client_email, title, description, 
                           tech_stack, budget_min, budget_max, complexity,
                           estimated_hours, quoted_price
                    FROM projects
                    WHERE current_state IN ({placeholders})
                    ORDER BY created_at ASC
                    LIMIT 20
                """, tuple(processable_states))

                projects = cursor.fetchall()

            # Process each project (outside the cursor context)
            for project in projects:
                if not self.running:
                    break
                
                with self._lock:
                    success = self._process_single_project(project)
                    if success:
                        processed_count += 1

        except Exception as e:
            print(f"[WorkflowEngine] Error fetching projects: {e}")

        return processed_count

    def _process_single_project(self, project):
        """Process a single project through its current agent"""
        project_id = project['id']
        current_state = project['current_state']
        agent = self.agents.get(current_state)

        if not agent:
            return False

        print(f"[WorkflowEngine] Processing project #{project_id} (state: {current_state}, agent: {agent.agent_name})")

        try:
            # Run the agent
            new_state = agent.process(dict(project))

            if new_state and new_state != current_state:
                # Update project state in DB
                with Database.get_cursor() as cursor:
                    cursor.execute("""
                        UPDATE projects SET current_state = %s, updated_at = NOW()
                        WHERE id = %s
                    """, (new_state, project_id))

                print(f"[WorkflowEngine] Project #{project_id}: {current_state} → {new_state}")
                return True
            else:
                # Agent returned None or same state — no transition
                return False

        except Exception as e:
            print(f"[WorkflowEngine] Error processing project #{project_id}: {e}")
            # Log the error
            try:
                from app.database import QueryHelper
                QueryHelper.log_agent_action(
                    agent_name=agent.agent_name,
                    action="PROCESS_ERROR",
                    project_id=project_id,
                    success=False,
                    error_message=str(e)
                )
            except Exception:
                pass
            return False

    def get_pipeline_info(self):
        """Return info about the workflow pipeline (for admin UI)"""
        return {
            'states': list(self.agents.keys()),
            'terminal_states': list(TERMINAL_STATES),
            'manual_states': list(MANUAL_STATES),
            'agents': {state: agent.agent_name for state, agent in self.agents.items()},
            'pipeline': [
                {'state': 'NEW', 'agent': 'email_parser_agent', 'description': 'Parse email, extract project details'},
                {'state': 'PARSED', 'agent': 'scam_filter_agent', 'description': 'Check for scam/fraud/illegal'},
                {'state': 'ANALYZED', 'agent': 'classification_agent', 'description': 'Classify complexity, tech stack'},
                {'state': 'CLASSIFIED', 'agent': 'estimation_agent', 'description': 'Estimate hours and cost'},
                {'state': 'ESTIMATION_READY', 'agent': 'offer_generator_agent', 'description': 'Generate commercial proposal'},
                {'state': 'OFFER_SENT', 'agent': None, 'description': 'Waiting for client response'},
                {'state': 'NEGOTIATION', 'agent': 'dialogue_orchestrator_agent', 'description': 'Handle client negotiation'},
                {'state': 'AGREED', 'agent': None, 'description': 'Client agreed, awaiting payment (manual)'},
                {'state': 'FUNDED', 'agent': None, 'description': 'Payment received, ready for execution (manual)'},
                {'state': 'EXECUTION_READY', 'agent': None, 'description': 'Project in execution (manual)'},
                {'state': 'CLOSED', 'agent': None, 'description': 'Project completed'},
                {'state': 'REJECTED', 'agent': None, 'description': 'Project rejected/filtered'},
            ]
        }