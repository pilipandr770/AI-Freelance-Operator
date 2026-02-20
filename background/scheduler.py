import time
import threading
from app.workflow.engine import WorkflowEngine
from background.mail_worker import MailWorker
from app.freelancer_inbox import get_freelancer_inbox

class BackgroundScheduler:
    def __init__(self):
        self.workflow_engine = WorkflowEngine()
        self.mail_worker = MailWorker()
        self.fl_inbox = get_freelancer_inbox()
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

        # Start freelancer.com inbox monitor
        fl_thread = threading.Thread(target=self._run_fl_inbox_loop, daemon=True)
        fl_thread.start()
        self.threads.append(fl_thread)

        print("Background scheduler started with workflow, mail, and FL inbox processing")

    def stop_all(self):
        """Stop all background processes"""
        print("Stopping background scheduler...")
        self.workflow_engine.stop()
        self.mail_worker.stop()
        self.fl_inbox.stop()
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

    def _run_fl_inbox_loop(self):
        """Run freelancer.com inbox monitor in a loop"""
        self.fl_inbox.start()