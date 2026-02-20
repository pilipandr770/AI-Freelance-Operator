import time
import threading
from app.workflow.engine import WorkflowEngine
from background.mail_worker import MailWorker

class BackgroundScheduler:
    def __init__(self):
        self.workflow_engine = WorkflowEngine()
        self.mail_worker = MailWorker()
        self.threads = []

    def start_all(self):
        """Start all background processes"""
        print("Starting background scheduler...")

        # Start workflow engine
        workflow_thread = threading.Thread(target=self._run_workflow_loop, daemon=True)
        workflow_thread.start()
        self.threads.append(workflow_thread)

        # Start mail intake
        mail_thread = threading.Thread(target=self._run_mail_loop, daemon=True)
        mail_thread.start()
        self.threads.append(mail_thread)

        print("Background scheduler started with workflow and mail processing")

    def stop_all(self):
        """Stop all background processes"""
        print("Stopping background scheduler...")
        self.workflow_engine.stop()
        self.mail_worker.stop()
        # Close Selenium browser if it was used
        try:
            from app.freelancer_client import _shutdown_client
            _shutdown_client()
        except Exception:
            pass
        # Threads are daemon, they will stop with main process

    def _run_workflow_loop(self):
        """Run workflow engine in a loop"""
        self.workflow_engine.start()

    def _run_mail_loop(self):
        """Run mail worker in a loop"""
        self.mail_worker.start()