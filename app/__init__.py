"""
AI Freelance Operator Flask Application
"""

from flask import Flask
from config import Config


def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(Config)
    
    # Register blueprints
    from .routes import main
    app.register_blueprint(main)
    
    return app
