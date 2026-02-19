"""
AI Freelance Operator - Main Entry Point
"""

from app import create_app
from config import Config
from app.database import Database
from app.ai_client import get_ai_client
from background.scheduler import BackgroundScheduler

# Validate configuration
print("=" * 60)
print("AI Freelance Operator - Starting Up")
print("=" * 60)

Config.validate()

# Test connections
print("\nTesting connections...")
Database.test_connection()

try:
    ai_client = get_ai_client()
    ai_client.test_connection()
except Exception as e:
    print(f"⚠️  OpenAI API: {e}")

print("\n" + "=" * 60)
print(f"Starting Flask server on {Config.HOST}:{Config.PORT}")
print("=" * 60 + "\n")

# Create and run Flask app
app = create_app()

# Start background processes only once (avoid duplicates in debug/reloader mode)
import os
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not Config.DEBUG:
    scheduler = BackgroundScheduler()
    scheduler.start_all()
else:
    scheduler = None

if __name__ == "__main__":
    try:
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=Config.DEBUG
        )
    finally:
        if scheduler:
            scheduler.stop_all()
