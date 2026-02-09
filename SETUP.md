# AI Freelance Operator - Setup Guide

## Prerequisites

- Python 3.9+
- PostgreSQL 14+
- OpenAI API key
- Gmail account with App Password
- Telegram Bot (optional)

## Installation

### 1. Clone and Setup Environment

```bash
cd ai_freelance_operator
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```bash
# OpenAI API Key (required)
OPENAI_API_KEY=sk-your-api-key-here

# Database credentials
DB_PASSWORD=your_postgres_password

# Gmail credentials
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_gmail_app_password

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_OWNER_ID=your_telegram_user_id
```

### 3. Setup Database

Create PostgreSQL database:

```sql
CREATE DATABASE ai_freelance_operator;
```

Initialize schema:

```bash
# Option 1: Using psql
psql -U postgres -d ai_freelance_operator -f schema.sql

# Option 2: Using API endpoint (after starting server)
curl -X POST http://localhost:5000/api/db/init
```

### 4. Run the Application

```bash
python run.py
```

The server will start at `http://localhost:5000`

## Getting API Keys

### OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create new secret key
3. Copy and add to `.env`

### Gmail App Password

1. Enable 2-factor authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate app password for "Mail"
4. Use this password in `.env` (not your regular Gmail password)

### Telegram Bot Token

1. Message @BotFather on Telegram
2. Send `/newbot` and follow instructions
3. Copy the token
4. Get your user ID from @userinfobot
5. Add both to `.env`

## Testing

Test database connection:

```bash
python -c "from app.database import Database; Database.test_connection()"
```

Test OpenAI connection:

```bash
python -c "from app.ai_client import get_ai_client; get_ai_client().test_connection()"
```

## API Endpoints

### Public API

- `GET /` - Home page
- `GET /health` - Health check
- `GET /api/status` - System status
- `GET /api/projects` - List all projects
- `GET /api/projects/<id>` - Get project details
- `GET /api/settings` - Get system settings
- `POST /api/settings` - Update settings
- `POST /api/db/init` - Initialize database

### Admin Panel

- `GET /admin` - Admin dashboard
- `GET /admin/agents` - AI agents management
- `GET /admin/agents/<id>` - Get agent details
- `POST /admin/agents` - Create new agent
- `PUT /admin/agents/<id>` - Update agent
- `POST /admin/agents/<id>/toggle` - Activate/deactivate agent
- `GET /admin/projects` - Projects management (coming soon)
- `GET /admin/clients` - Clients management (coming soon)
- `GET /admin/settings` - System settings UI
- `GET /admin/logs` - Agent activity logs

## Using Admin Panel

### First Time Setup

After starting the server, open the admin panel:

```
http://localhost:5000/admin
```

### Managing AI Agents

1. **Navigate to Agents:** Click "🤖 AI Agents" in sidebar
2. **View Agents:** See all configured agents with their status
3. **Edit Agent Instructions:**
   - Click "Edit" on any agent
   - Modify system prompt and instructions
   - Save changes (version will auto-increment)
4. **Add New Agent:**
   - Click "+ Add New Agent"
   - Fill in agent name, system prompt, and instructions
   - Mark as active
   - Save

### Configuring System Settings

1. **Navigate to Settings:** Click "⚙️ Settings" in sidebar
2. **Edit Values:** Click "Edit" next to any setting
3. **Common Settings:**
   - `hourly_rate` - Your base rate for projects
   - `auto_negotiation_enabled` - Enable/disable auto negotiation
   - `scam_filter_threshold` - Scam detection sensitivity (0-1)
   - `min_project_budget` - Minimum acceptable project size

### Monitoring Activity

1. **Navigate to Logs:** Click "📝 Logs" in sidebar
2. **Review:**
   - Which agents are running
   - API token usage
   - Execution times
   - Costs per request

For detailed admin panel documentation, see [ADMIN_GUIDE.md](ADMIN_GUIDE.md)

## Next Steps

1. ✅ Admin panel is ready
2. Configure AI agents through `/admin/agents`
3. Implement email ingestion worker
4. Create AI agent pipeline
5. Setup Telegram bot

## Troubleshooting

**Database connection error:**
- Check PostgreSQL is running: `pg_ctl status`
- Verify credentials in `.env`
- Ensure database exists: `psql -l`

**OpenAI API error:**
- Verify API key is correct
- Check API usage limits at https://platform.openai.com/usage
- Ensure you have credits available

**Gmail connection error:**
- Use App Password, not regular password
- Enable IMAP in Gmail settings
- Allow less secure apps if needed

## Security Notes

- Never commit `.env` file to git
- Keep API keys secure
- Use strong database passwords
- Consider using environment-specific configs for production
