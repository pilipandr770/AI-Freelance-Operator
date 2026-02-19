"""
Flask routes for AI Freelance Operator
"""

from flask import Blueprint, jsonify, request, render_template_string, render_template
from app.database import Database, QueryHelper
from app.ai_client import get_ai_client
from app.workflow.dispatcher import STATE_MACHINE, ALL_STATES, AUTO_STATES, MANUAL_STATES, TERMINAL_STATES
from config import Config
import json

main = Blueprint('main', __name__)


@main.route("/")
def index():
    """Home page"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Freelance Operator</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; }
            .status { background: #f0f0f0; padding: 15px; border-radius: 5px; margin: 20px 0; }
            .endpoint { margin: 10px 0; }
            .endpoint code { background: #e0e0e0; padding: 2px 6px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>🤖 AI Freelance Operator</h1>
        <p>Personal multi-agent freelance automation system</p>
        
        <div class="status">
            <h3>System Status</h3>
            <p>✓ Flask server running</p>
            <p>✓ Configuration loaded</p>
        </div>
        
        <h3>Links</h3>
        <div class="endpoint">🎛️ <a href="/admin">Admin Panel</a> - Manage agents, projects, and settings</div>
        
        <h3>API Endpoints</h3>
        <div class="endpoint">📊 <code>GET /health</code> - Health check</div>
        <div class="endpoint">📈 <code>GET /api/status</code> - System status</div>
        <div class="endpoint">📋 <code>GET /api/projects</code> - List projects</div>
        <div class="endpoint">📝 <code>GET /api/projects/&lt;id&gt;</code> - Get project details</div>
        <div class="endpoint">⚙️ <code>GET /api/settings</code> - Get system settings</div>
        <div class="endpoint">🔧 <code>POST /api/settings</code> - Update system settings</div>
        <div class="endpoint">🗄️ <code>POST /api/db/init</code> - Initialize database schema</div>
    </body>
    </html>
    """
    return render_template_string(html)


@main.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"})


@main.route("/api/status")
def status():
    """System status endpoint"""
    try:
        db_connected = Database.test_connection()
        
        ai_status = "unknown"
        try:
            ai_client = get_ai_client()
            ai_connected = ai_client.test_connection()
            ai_status = "connected" if ai_connected else "disconnected"
        except:
            ai_status = "not_configured"
        
        return jsonify({
            "status": "running",
            "database": "connected" if db_connected else "disconnected",
            "openai": ai_status,
            "config": {
                "model": Config.OPENAI_MODEL,
                "hourly_rate": Config.HOURLY_RATE,
                "auto_negotiation": Config.AUTO_NEGOTIATION_ENABLED,
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@main.route("/api/projects")
def list_projects():
    """List all projects"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, title, current_state, complexity, quoted_price, 
                       created_at, updated_at
                FROM projects
                ORDER BY updated_at DESC
                LIMIT 50
            """)
            projects = cursor.fetchall()
            
        return jsonify({
            "projects": projects,
            "count": len(projects)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/api/projects/<int:project_id>")
def get_project(project_id):
    """Get project details"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("""
                SELECT p.*, c.name as client_name, c.email as client_email
                FROM projects p
                LEFT JOIN clients c ON p.client_id = c.id
                WHERE p.id = %s
            """, (project_id,))
            project = cursor.fetchone()
            
            if not project:
                return jsonify({"error": "Project not found"}), 404
            
            # Get project messages
            cursor.execute("""
                SELECT id, direction, subject, created_at
                FROM project_messages
                WHERE project_id = %s
                ORDER BY created_at ASC
            """, (project_id,))
            messages = cursor.fetchall()
            
            project['messages'] = messages
            
        return jsonify(project)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/api/settings")
def get_settings():
    """Get system settings"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("SELECT * FROM system_settings ORDER BY setting_key")
            settings = cursor.fetchall()
            
        return jsonify({
            "settings": settings
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/api/settings", methods=["POST"])
def update_settings():
    """Update system settings"""
    try:
        data = request.get_json()
        
        if not data or 'key' not in data or 'value' not in data:
            return jsonify({"error": "Missing key or value"}), 400
        
        QueryHelper.set_system_setting(
            data['key'], 
            data['value'], 
            data.get('value_type', 'string')
        )
        
        return jsonify({"success": True, "message": "Setting updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/api/db/init", methods=["POST"])
def init_database():
    """Initialize database schema"""
    try:
        Database.init_schema()
        return jsonify({
            "success": True, 
            "message": "Database schema initialized successfully"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# ADMIN PANEL ROUTES
# ============================================================================

@main.route("/admin")
def admin_dashboard():
    """Admin dashboard"""
    try:
        with Database.get_cursor() as cursor:
            # Get stats
            cursor.execute("SELECT COUNT(*) as count FROM projects")
            total_projects = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM projects WHERE current_state NOT IN ('CLOSED')")
            active_projects = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM clients")
            total_clients = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM agent_instructions")
            agent_count = cursor.fetchone()['count']
            
            # Get recent projects
            cursor.execute("""
                SELECT id, title, current_state, complexity, created_at
                FROM projects
                ORDER BY created_at DESC
                LIMIT 5
            """)
            recent_projects = cursor.fetchall()
            
            # Get system settings
            hourly_rate = QueryHelper.get_system_setting('hourly_rate', 50.0)
            auto_negotiation = QueryHelper.get_system_setting('auto_negotiation_enabled', True)
        
        return render_template('dashboard.html',
            stats={
                'total_projects': total_projects,
                'active_projects': active_projects,
                'total_clients': total_clients,
                'agent_count': agent_count
            },
            recent_projects=recent_projects,
            settings={
                'hourly_rate': hourly_rate,
                'auto_negotiation': auto_negotiation
            }
        )
    except Exception as e:
        return f"Error loading dashboard: {str(e)}", 500


@main.route("/admin/agents")
def admin_agents():
    """Admin agents page"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, agent_name, is_active, version, updated_at
                FROM agent_instructions
                ORDER BY agent_name
            """)
            agents = cursor.fetchall()
        
        return render_template('agents.html', agents=agents)
    except Exception as e:
        return f"Error loading agents: {str(e)}", 500


@main.route("/admin/agents/<int:agent_id>")
def get_agent(agent_id):
    """Get agent by ID (API endpoint)"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, agent_name, instruction_text, system_prompt, version, is_active
                FROM agent_instructions
                WHERE id = %s
            """, (agent_id,))
            agent = cursor.fetchone()
            
            if not agent:
                return jsonify({"error": "Agent not found"}), 404
            
            return jsonify(agent)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/agents", methods=["POST"])
def create_agent():
    """Create new agent"""
    try:
        data = request.get_json()
        
        if not data or 'agent_name' not in data:
            return jsonify({"error": "agent_name is required"}), 400
        
        with Database.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO agent_instructions (agent_name, instruction_text, system_prompt, is_active)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (
                data['agent_name'],
                data.get('instruction_text', ''),
                data.get('system_prompt', ''),
                data.get('is_active', True)
            ))
            result = cursor.fetchone()
            
        return jsonify({"success": True, "message": "Agent created successfully", "id": result['id']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/agents/<int:agent_id>", methods=["PUT"])
def update_agent(agent_id):
    """Update agent"""
    try:
        data = request.get_json()
        
        with Database.get_cursor() as cursor:
            # Increment version
            cursor.execute("""
                UPDATE agent_instructions
                SET agent_name = %s,
                    instruction_text = %s,
                    system_prompt = %s,
                    is_active = %s,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                data.get('agent_name'),
                data.get('instruction_text'),
                data.get('system_prompt'),
                data.get('is_active', True),
                agent_id
            ))
            
            if cursor.rowcount == 0:
                return jsonify({"error": "Agent not found"}), 404
        
        return jsonify({"success": True, "message": "Agent updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/agents/<int:agent_id>/toggle", methods=["POST"])
def toggle_agent(agent_id):
    """Toggle agent active status"""
    try:
        data = request.get_json()
        is_active = data.get('is_active', False)
        
        with Database.get_cursor() as cursor:
            cursor.execute("""
                UPDATE agent_instructions
                SET is_active = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (is_active, agent_id))
            
            if cursor.rowcount == 0:
                return jsonify({"error": "Agent not found"}), 404
        
        status = "activated" if is_active else "deactivated"
        return jsonify({"success": True, "message": f"Agent {status} successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/projects")
def admin_projects():
    """Admin projects page"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("""
                SELECT p.*, c.email as client_email
                FROM projects p
                LEFT JOIN clients c ON p.client_id = c.id
                ORDER BY p.updated_at DESC
            """)
            projects = cursor.fetchall()
        
        return render_template('projects.html', projects=projects)
    except Exception as e:
        return f"Error loading projects: {str(e)}", 500


@main.route("/admin/projects/<int:project_id>/state", methods=["POST"])
def change_project_state(project_id):
    """Change project state"""
    try:
        data = request.get_json()
        new_state = data.get('state')
        
        if not new_state:
            return jsonify({"error": "State is required"}), 400
        
        with Database.get_cursor() as cursor:
            # Update project state
            cursor.execute("""
                UPDATE projects
                SET current_state = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (new_state, project_id))
            
            if cursor.rowcount == 0:
                return jsonify({"error": "Project not found"}), 404
            
            # Log state transition
            cursor.execute("""
                INSERT INTO project_states (project_id, to_state, changed_by, reason)
                VALUES (%s, %s, %s, %s)
            """, (project_id, new_state, 'admin', 'Manual state change'))
        
        return jsonify({"success": True, "message": "Project state updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/clients")
def admin_clients():
    """Admin clients page"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("SELECT * FROM clients ORDER BY created_at DESC")
            clients = cursor.fetchall()
        
        return render_template('clients.html', clients=clients)
    except Exception as e:
        return f"Error loading clients: {str(e)}", 500


@main.route("/admin/clients/<int:client_id>")
def get_client(client_id):
    """Get client details"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
            client = cursor.fetchone()
            
            if not client:
                return jsonify({"error": "Client not found"}), 404
            
            # Get client's projects
            cursor.execute("""
                SELECT id, title, current_state, quoted_price
                FROM projects
                WHERE client_id = %s
                ORDER BY created_at DESC
            """, (client_id,))
            projects = cursor.fetchall()
            
            client['projects'] = projects
        
        return jsonify(client)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/clients/<int:client_id>/blacklist", methods=["POST"])
def blacklist_client(client_id):
    """Blacklist or unblacklist a client"""
    try:
        data = request.get_json()
        blacklist = data.get('blacklist', True)
        reason = data.get('reason', '')
        
        with Database.get_cursor() as cursor:
            cursor.execute("""
                UPDATE clients
                SET is_blacklisted = %s,
                    blacklist_reason = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (blacklist, reason if blacklist else None, client_id))
            
            if cursor.rowcount == 0:
                return jsonify({"error": "Client not found"}), 404
        
        action = "blacklisted" if blacklist else "unblacklisted"
        return jsonify({"success": True, "message": f"Client {action} successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/settings")
def admin_settings():
    """Admin settings page"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("SELECT * FROM system_settings ORDER BY setting_key")
            settings = cursor.fetchall()
        
        html = """
        {% extends "base.html" %}
        {% block title %}Settings{% endblock %}
        {% block content %}
        <h2>System Settings</h2>
        
        <div id="alertContainer"></div>
        
        <div class="card">
            <table class="table">
                <thead>
                    <tr>
                        <th>Setting Key</th>
                        <th>Value</th>
                        <th>Type</th>
                        <th>Description</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for setting in settings %}
                    <tr>
                        <td><strong>{{ setting.setting_key }}</strong></td>
                        <td id="value-{{ setting.id }}">{{ setting.setting_value }}</td>
                        <td>{{ setting.value_type }}</td>
                        <td>{{ setting.description or 'N/A' }}</td>
                        <td>
                            <button class="btn btn-secondary" style="padding: 0.25rem 0.75rem;" 
                                    onclick="editSetting('{{ setting.setting_key }}', '{{ setting.setting_value }}', '{{ setting.value_type }}')">
                                Edit
                            </button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endblock %}
        
        {% block extra_scripts %}
        <script>
        function showAlert(message, type) {
            const alert = document.createElement('div');
            alert.className = 'alert alert-' + type;
            alert.textContent = message;
            document.getElementById('alertContainer').appendChild(alert);
            setTimeout(() => alert.remove(), 5000);
        }
        
        function editSetting(key, value, type) {
            const newValue = prompt('Enter new value for ' + key + ':', value);
            if (newValue === null) return;
            
            fetch('/api/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({key: key, value: newValue, value_type: type})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert('Setting updated successfully', 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showAlert(data.error, 'error');
                }
            })
            .catch(error => showAlert('Error: ' + error, 'error'));
        }
        </script>
        {% endblock %}
        """
        
        return render_template_string(html, settings=settings)
    except Exception as e:
        return f"Error loading settings: {str(e)}", 500


@main.route("/admin/logs")
def admin_logs():
    """Admin logs page"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, agent_name, action, success, execution_time_ms, tokens_used, cost, created_at
                FROM agent_logs
                ORDER BY created_at DESC
                LIMIT 100
            """)
            logs = cursor.fetchall()
        
        html = """
        {% extends "base.html" %}
        {% block title %}Agent Logs{% endblock %}
        {% block content %}
        <h2>Agent Activity Logs</h2>
        
        <div class="card">
            <table class="table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Agent</th>
                        <th>Action</th>
                        <th>Status</th>
                        <th>Time (ms)</th>
                        <th>Tokens</th>
                        <th>Cost</th>
                    </tr>
                </thead>
                <tbody>
                    {% for log in logs %}
                    <tr>
                        <td>{{ log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else 'N/A' }}</td>
                        <td>{{ log.agent_name }}</td>
                        <td>{{ log.action }}</td>
                        <td>
                            {% if log.success %}
                            <span class="badge badge-active">Success</span>
                            {% else %}
                            <span class="badge badge-inactive">Failed</span>
                            {% endif %}
                        </td>
                        <td>{{ log.execution_time_ms or '-' }}</td>
                        <td>{{ log.tokens_used or '-' }}</td>
                        <td>${{ '%.4f'|format(log.cost) if log.cost else '-' }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="7" style="text-align: center; color: #7f8c8d;">No logs yet</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endblock %}
        """
        
        return render_template_string(html, logs=logs)
    except Exception as e:
        return f"Error loading logs: {str(e)}", 500


# ============================================================================
# EMAIL CONFIGURATION ROUTES
# ============================================================================

@main.route("/admin/email")
def admin_email_config():
    """Email configuration page"""
    try:
        current_email = QueryHelper.get_system_setting('mail_username', '')
        check_interval = QueryHelper.get_system_setting('mail_check_interval', 300)
        
        return render_template('email_config.html', 
                             current_email=current_email,
                             check_interval=check_interval)
    except Exception as e:
        return f"Error loading email config: {str(e)}", 500


@main.route("/admin/email/config", methods=["POST"])
def save_email_config():
    """Save email IMAP configuration"""
    try:
        data = request.get_json()
        
        mail_username = data.get('mail_username')
        mail_password = data.get('mail_password')
        check_interval = data.get('check_interval', 300)
        
        if not mail_username:
            return jsonify({"error": "Email is required"}), 400
        
        if mail_password and len(mail_password) != 16:
            return jsonify({"error": "App Password must be exactly 16 characters"}), 400
        
        # Save to system settings
        QueryHelper.set_system_setting('mail_username', mail_username, 'string')
        
        if mail_password:
            QueryHelper.set_system_setting('mail_password', mail_password, 'string')
        
        QueryHelper.set_system_setting('mail_check_interval', str(check_interval), 'integer')
        
        return jsonify({"success": True, "message": "Email configuration saved successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/email/smtp", methods=["POST"])
def save_smtp_config():
    """Save SMTP configuration"""
    try:
        data = request.get_json()
        
        smtp_username = data.get('smtp_username')
        smtp_password = data.get('smtp_password')
        
        if smtp_username:
            QueryHelper.set_system_setting('smtp_username', smtp_username, 'string')
        
        if smtp_password:
            QueryHelper.set_system_setting('smtp_password', smtp_password, 'string')
        
        return jsonify({"success": True, "message": "SMTP configuration saved successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/email/test", methods=["POST"])
def test_email_connection():
    """Test email IMAP connection"""
    try:
        import imapclient
        import ssl
        
        mail_username = QueryHelper.get_system_setting('mail_username')
        mail_password = QueryHelper.get_system_setting('mail_password')
        
        if not mail_username or not mail_password:
            return jsonify({"error": "Email credentials not configured"}), 400
        
        # Try to connect
        context = ssl.create_default_context()
        server = imapclient.IMAPClient('imap.gmail.com', ssl=True, ssl_context=context)
        server.login(mail_username, mail_password)
        server.logout()
        
        return jsonify({"success": True, "message": "Connection successful"})
    except Exception as e:
        return jsonify({"error": f"Connection failed: {str(e)}"}), 500


@main.route("/admin/email/status")
def email_status():
    """Get email configuration status"""
    try:
        mail_username = QueryHelper.get_system_setting('mail_username')
        mail_password = QueryHelper.get_system_setting('mail_password')
        
        configured = bool(mail_username and mail_password)
        
        return jsonify({
            "configured": configured,
            "email": mail_username if configured else None
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/email/disconnect", methods=["POST"])
def disconnect_email():
    """Disconnect current email — clears IMAP & SMTP credentials."""
    try:
        # Clear all email-related settings
        for key in ['mail_username', 'mail_password', 'smtp_username', 'smtp_password']:
            QueryHelper.set_system_setting(key, '', 'string')

        return jsonify({"success": True, "message": "Email disconnected. System will stop checking mail."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# WORKFLOW PIPELINE ROUTES
# ============================================================================

@main.route("/api/workflow/pipeline")
def get_workflow_pipeline():
    """Get workflow pipeline info"""
    from app.workflow.engine import WorkflowEngine
    engine = WorkflowEngine()
    return jsonify(engine.get_pipeline_info())


@main.route("/api/workflow/stats")
def get_workflow_stats():
    """Get project counts by state"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("""
                SELECT current_state, COUNT(*) as count
                FROM projects
                GROUP BY current_state
                ORDER BY count DESC
            """)
            state_counts = {row['current_state']: row['count'] for row in cursor.fetchall()}
            
            cursor.execute("SELECT COUNT(*) as total FROM projects")
            total = cursor.fetchone()['total']
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM projects 
                WHERE current_state NOT IN ('CLOSED', 'REJECTED')
            """)
            active = cursor.fetchone()['count']
        
        return jsonify({
            "total_projects": total,
            "active_projects": active,
            "by_state": state_counts,
            "all_states": ALL_STATES,
            "auto_states": AUTO_STATES,
            "manual_states": MANUAL_STATES,
            "terminal_states": TERMINAL_STATES
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/workflow")
def admin_workflow():
    """Workflow pipeline visualization page"""
    try:
        with Database.get_cursor() as cursor:
            # State counts
            cursor.execute("""
                SELECT current_state, COUNT(*) as count
                FROM projects
                GROUP BY current_state
            """)
            state_counts = {row['current_state']: row['count'] for row in cursor.fetchall()}
            
            # Recent state transitions
            cursor.execute("""
                SELECT ps.*, p.title as project_title
                FROM project_states ps
                LEFT JOIN projects p ON ps.project_id = p.id  
                ORDER BY ps.created_at DESC
                LIMIT 50
            """)
            transitions = cursor.fetchall()
            
            # Recent agent logs
            cursor.execute("""
                SELECT al.*, p.title as project_title
                FROM agent_logs al
                LEFT JOIN projects p ON al.project_id = p.id
                ORDER BY al.created_at DESC
                LIMIT 30
            """)
            logs = cursor.fetchall()

        return render_template('workflow.html',
            state_counts=state_counts,
            transitions=transitions,
            logs=logs,
            all_states=ALL_STATES,
            auto_states=AUTO_STATES,
            manual_states=MANUAL_STATES,
            terminal_states=TERMINAL_STATES,
            state_machine=STATE_MACHINE
        )
    except Exception as e:
        return f"Error loading workflow: {str(e)}", 500


@main.route("/api/projects/<int:project_id>/reprocess", methods=["POST"])
def reprocess_project(project_id):
    """Manually re-trigger agent processing for a project"""
    try:
        data = request.get_json() or {}
        target_state = data.get('target_state')
        
        with Database.get_cursor() as cursor:
            cursor.execute("SELECT id, current_state FROM projects WHERE id = %s", (project_id,))
            project = cursor.fetchone()
            
            if not project:
                return jsonify({"error": "Project not found"}), 404
            
            if target_state:
                # Move to specified state
                cursor.execute("""
                    UPDATE projects SET current_state = %s, updated_at = NOW() WHERE id = %s
                """, (target_state, project_id))
                cursor.execute("""
                    INSERT INTO project_states (project_id, from_state, to_state, changed_by, reason)
                    VALUES (%s, %s, %s, 'admin', 'Manual state change')
                """, (project_id, project['current_state'], target_state))
        
        return jsonify({"success": True, "message": f"Project state set to {target_state or project['current_state']}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/api/projects/<int:project_id>/messages")
def get_project_messages(project_id):
    """Get all messages for a project"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, direction, sender_email, recipient_email, subject, body, 
                       is_processed, created_at
                FROM project_messages
                WHERE project_id = %s
                ORDER BY created_at ASC
            """, (project_id,))
            messages = cursor.fetchall()
        
        return jsonify({"messages": messages, "count": len(messages)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/api/projects/<int:project_id>/tasks")
def get_project_tasks(project_id):
    """Get all tasks for a project"""
    try:
        with Database.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, title, description, estimated_hours, priority, status
                FROM tasks
                WHERE project_id = %s
                ORDER BY priority ASC
            """, (project_id,))
            tasks = cursor.fetchall()
        
        return jsonify({"tasks": tasks, "count": len(tasks)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route("/admin/email/test-smtp", methods=["POST"])
def test_smtp_connection():
    """Test SMTP connection"""
    try:
        from app.email_sender import get_email_sender
        sender = get_email_sender()
        success, message = sender.test_connection()
        
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
