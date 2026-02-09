# AI Freelance Operator - Project Structure

```
ai_freelance_operator/
│
├── app/                           # Main application package
│   ├── __init__.py               # Flask app factory
│   ├── routes.py                 # All routes (API + Admin Panel)
│   ├── ai_client.py              # OpenAI API client wrapper
│   ├── database.py               # Database utilities and queries
│   │
│   └── templates/                # HTML templates for admin panel
│       ├── base.html             # Base template with navigation
│       ├── dashboard.html        # Admin dashboard
│       └── agents.html           # AI agents management page
│
├── config.py                      # Configuration loader from .env
├── schema.sql                     # PostgreSQL database schema
├── requirements.txt               # Python dependencies
├── run.py                         # Application entry point
├── start.bat                      # Quick start script for Windows
│
├── .env                          # Environment variables (gitignored)
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
│
├── README.md                     # Project overview (Ukrainian)
├── SETUP.md                      # Installation and setup guide
└── ADMIN_GUIDE.md                # Admin panel user guide
```

## File Descriptions

### Core Application

**`run.py`**
- Entry point for the application
- Tests database and OpenAI connections on startup
- Starts Flask development server

**`config.py`**
- Loads configuration from environment variables
- Validates required settings (OpenAI API key, DB credentials, etc.)
- Provides Config class for app-wide settings

**`app/__init__.py`**
- Flask application factory
- Registers blueprints (routes)
- Initializes app configuration

### Routes & API

**`app/routes.py`**
- **Public API endpoints:**
  - Health check, status, projects list
- **Admin Panel routes:**
  - Dashboard with statistics
  - AI agents CRUD operations
  - System settings management
  - Activity logs viewer
- **API endpoints for admin:**
  - `/admin/agents` - List, create, update, toggle agents
  - `/api/settings` - Get/update system settings

### Database

**`schema.sql`**
- Complete PostgreSQL schema
- Tables:
  - `clients` - Client information
  - `projects` - Projects with state machine
  - `tasks` - Sub-tasks within projects
  - `project_states` - State transition audit log
  - `project_messages` - Email correspondence
  - `agent_logs` - AI agent activity logs
  - `system_settings` - Runtime configuration
  - `agent_instructions` - AI agent prompts (editable)
- Pre-populated with default agents and settings

**`app/database.py`**
- Database connection manager
- Context managers for connections and cursors
- QueryHelper class for common queries
- Agent logging utilities

### AI Integration

**`app/ai_client.py`**
- OpenAI API wrapper
- Chat completions with configurable parameters
- Token usage and cost tracking
- JSON response parsing
- Connection testing

### Admin Panel Templates

**`app/templates/base.html`**
- Base layout for all admin pages
- Navigation sidebar
- Consistent styling
- Responsive design

**`app/templates/dashboard.html`**
- System overview
- Project statistics
- Recent activity
- System status

**`app/templates/agents.html`**
- List all AI agents
- Add/edit agent instructions
- Activate/deactivate agents
- Version tracking
- Interactive modal forms

### Configuration & Documentation

**`.env.example`** → **`.env`**
- Database credentials
- OpenAI API key
- Email (Gmail) settings
- Telegram bot credentials
- System defaults (hourly rate, thresholds)

**`README.md`**
- Project overview in Ukrainian
- System architecture
- Features and workflows
- Technology stack

**`SETUP.md`**
- Step-by-step installation guide
- Environment configuration
- Database setup
- Testing connections
- Troubleshooting

**`ADMIN_GUIDE.md`**
- Complete admin panel documentation
- Agent management guide
- API examples
- Best practices for writing prompts

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Request                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼───────┐
                    │  Flask App   │
                    │  (run.py)    │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              │                         │
       ┌──────▼──────┐          ┌──────▼──────┐
       │  Public API │          │ Admin Panel │
       │  Endpoints  │          │   Routes    │
       └──────┬──────┘          └──────┬──────┘
              │                        │
              └────────────┬───────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
       ┌──────▼──────┐          ┌──────▼──────┐
       │  Database   │          │ AI Client   │
       │ (PostgreSQL)│          │  (OpenAI)   │
       └─────────────┘          └─────────────┘
```

## Database Schema Overview

```
clients
  └── projects (1:N)
       ├── tasks (1:N)
       ├── project_states (1:N) - audit log
       └── project_messages (1:N) - email threads

agent_instructions (editable prompts for AI agents)
  └── used by → agent_logs (activity tracking)

system_settings (runtime configuration)
```

## Next Development Steps

1. **Email Worker** - Create `app/workers/email_worker.py`
   - IMAP connection to Gmail
   - Email parsing and storage
   - Trigger intake pipeline

2. **AI Agent Pipeline** - Create `app/agents/`
   - Base agent class
   - Individual agent implementations
   - State machine orchestration

3. **Telegram Bot** - Create `app/telegram_bot.py`
   - Owner notifications
   - Command handlers
   - Status updates

4. **Workflow Engine** - Create `app/workflow.py`
   - State transitions
   - Agent orchestration
   - Error handling

## Key Design Principles

✅ **State-Driven Architecture** - All agents work through database state  
✅ **Runtime Configurable** - Settings and prompts editable without deployment  
✅ **Agent Isolation** - Each agent has single responsibility  
✅ **Audit Trail** - All actions logged for debugging and cost tracking  
✅ **Version Control** - Agent instructions versioned automatically  

## Technology Choices

- **Flask** - Lightweight, easy to extend
- **PostgreSQL** - Robust, supports JSON, great for audit logs
- **OpenAI API** - Best-in-class LLMs for agent intelligence
- **Pure HTML/CSS/JS** - No build step, works out of box
- **IMAP/SMTP** - Direct Gmail integration without OAuth complexity
