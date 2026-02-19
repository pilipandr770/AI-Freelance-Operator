"""
Configuration module for AI Freelance Operator
Loads settings from environment variables
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration"""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    PORT = int(os.getenv('FLASK_PORT', '5000'))
    
    # Database Configuration
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/ai_freelance_operator')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', '5432'))
    DB_NAME = os.getenv('DB_NAME', 'ai_freelance_operator')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')
    OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.7'))
    OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '2000'))
    
    # Email Configuration (IMAP)
    MAIL_HOST = os.getenv('MAIL_HOST', 'imap.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', '993'))
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'True').lower() == 'true'
    MAIL_CHECK_INTERVAL = int(os.getenv('MAIL_CHECK_INTERVAL', '300'))  # seconds
    
    # SMTP Configuration (for sending emails)
    SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', MAIL_USERNAME)
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', MAIL_PASSWORD)
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'True').lower() == 'true'
    
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_OWNER_ID = os.getenv('TELEGRAM_OWNER_ID')
    
    # Freelancer.com Auto-Bidding (optional — requires Chrome)
    FREELANCER_LOGIN = os.getenv('FREELANCER_LOGIN', '')
    FREELANCER_PASSWORD = os.getenv('FREELANCER_PASSWORD', '')
    FREELANCER_HEADLESS = os.getenv('FREELANCER_HEADLESS', 'true')   # 'false' to see browser
    FREELANCER_DEFAULT_DAYS = int(os.getenv('FREELANCER_DEFAULT_DAYS', '7'))
    
    # System Settings (defaults, can be overridden in DB)
    HOURLY_RATE = float(os.getenv('HOURLY_RATE', '50.0'))
    AUTO_NEGOTIATION_ENABLED = os.getenv('AUTO_NEGOTIATION_ENABLED', 'True').lower() == 'true'
    AUTO_INVOICE_ENABLED = os.getenv('AUTO_INVOICE_ENABLED', 'True').lower() == 'true'
    PREPAYMENT_PERCENTAGE = int(os.getenv('PREPAYMENT_PERCENTAGE', '50'))
    
    # Agent Settings
    SCAM_FILTER_THRESHOLD = float(os.getenv('SCAM_FILTER_THRESHOLD', '0.7'))
    MIN_PROJECT_BUDGET = float(os.getenv('MIN_PROJECT_BUDGET', '100'))
    MAX_PROJECT_BUDGET = float(os.getenv('MAX_PROJECT_BUDGET', '50000'))
    
    @staticmethod
    def validate():
        """Validate required configuration"""
        errors = []
        
        if not Config.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is not set")
        
        if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
            errors.append("Email credentials (MAIL_USERNAME, MAIL_PASSWORD) are not set")
        
        if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_OWNER_ID:
            errors.append("Telegram credentials (TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID) are not set")
        
        if errors:
            print("⚠️  Configuration warnings:")
            for error in errors:
                print(f"   - {error}")
            print("Some features may not work correctly.\n")
        
        return len(errors) == 0
