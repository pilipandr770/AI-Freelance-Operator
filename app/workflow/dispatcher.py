"""
Workflow Dispatcher — maps project states to agents.
Used by the engine and also available for manual triggering from admin panel.
"""
from app.agents.email_parser_agent import EmailParserAgent
from app.agents.scam_filter_agent import ScamFilterAgent
from app.agents.classification_agent import ClassificationAgent
from app.agents.estimation_agent import EstimationAgent
from app.agents.offer_generator_agent import OfferGeneratorAgent
from app.agents.dialogue_orchestrator_agent import DialogueOrchestratorAgent


# Complete state machine definition
STATE_MACHINE = {
    'NEW':              {'agent': EmailParserAgent,           'next': 'PARSED'},
    'PARSED':           {'agent': ScamFilterAgent,            'next': 'ANALYZED'},
    'ANALYZED':         {'agent': ClassificationAgent,        'next': 'CLASSIFIED'},
    'CLASSIFIED':       {'agent': EstimationAgent,            'next': 'ESTIMATION_READY'},
    'ESTIMATION_READY': {'agent': OfferGeneratorAgent,        'next': 'OFFER_SENT'},
    'OFFER_SENT':       {'agent': None,                       'next': 'NEGOTIATION'},  # waits for client
    'NEGOTIATION':      {'agent': DialogueOrchestratorAgent,  'next': 'AGREED'},
    'AGREED':           {'agent': None,                       'next': 'FUNDED'},       # manual
    'FUNDED':           {'agent': None,                       'next': 'EXECUTION_READY'},
    'EXECUTION_READY':  {'agent': None,                       'next': 'CLOSED'},
    'CLOSED':           {'agent': None,                       'next': None},            # terminal
    'REJECTED':         {'agent': None,                       'next': None},            # terminal
}

ALL_STATES = list(STATE_MACHINE.keys())
TERMINAL_STATES = [s for s, v in STATE_MACHINE.items() if v['next'] is None]
AUTO_STATES = [s for s, v in STATE_MACHINE.items() if v['agent'] is not None]
MANUAL_STATES = [s for s, v in STATE_MACHINE.items() if v['agent'] is None and v['next'] is not None]


class WorkflowDispatcher:
    """Provides agent lookups and state machine info."""

    def get_agent_for_state(self, state):
        """Get an agent instance for a given state"""
        entry = STATE_MACHINE.get(state)
        if entry and entry['agent']:
            return entry['agent']()
        return None

    def get_next_state(self, state):
        """Get the expected next state"""
        entry = STATE_MACHINE.get(state)
        return entry['next'] if entry else None

    def get_available_states(self):
        """Return all defined states"""
        return ALL_STATES

    def get_auto_states(self):
        """Return states with automatic agent processing"""
        return AUTO_STATES

    def get_manual_states(self):
        """Return states requiring manual action"""
        return MANUAL_STATES

    def get_state_info(self):
        """Return full state machine info"""
        return STATE_MACHINE