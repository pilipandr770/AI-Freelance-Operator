"""AI Agents package for the workflow pipeline."""
from app.agents.base import BaseAgent
from app.agents.email_parser_agent import EmailParserAgent
from app.agents.scam_filter_agent import ScamFilterAgent
from app.agents.classification_agent import ClassificationAgent
from app.agents.estimation_agent import EstimationAgent
from app.agents.offer_generator_agent import OfferGeneratorAgent
from app.agents.dialogue_orchestrator_agent import DialogueOrchestratorAgent

__all__ = [
    'BaseAgent',
    'EmailParserAgent',
    'ScamFilterAgent', 
    'ClassificationAgent',
    'EstimationAgent',
    'OfferGeneratorAgent',
    'DialogueOrchestratorAgent',
]
