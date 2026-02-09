-- AI Freelance Operator Database Schema
-- PostgreSQL Database Schema

-- Drop tables if they exist (for fresh setup)
DROP TABLE IF EXISTS agent_logs CASCADE;
DROP TABLE IF EXISTS project_messages CASCADE;
DROP TABLE IF EXISTS project_states CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS projects CASCADE;
DROP TABLE IF EXISTS clients CASCADE;
DROP TABLE IF EXISTS system_settings CASCADE;
DROP TABLE IF EXISTS agent_instructions CASCADE;

-- Clients table
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    company VARCHAR(255),
    country VARCHAR(100),
    timezone VARCHAR(50),
    total_projects INTEGER DEFAULT 0,
    successful_projects INTEGER DEFAULT 0,
    total_paid DECIMAL(10, 2) DEFAULT 0.0,
    reputation_score DECIMAL(3, 2) DEFAULT 0.0,
    is_blacklisted BOOLEAN DEFAULT FALSE,
    blacklist_reason TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Projects table
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    complexity VARCHAR(50), -- MICRO, SMALL, MEDIUM, LARGE, RND
    tech_stack TEXT[], -- Array of technologies
    is_familiar_stack BOOLEAN DEFAULT TRUE,
    budget_min DECIMAL(10, 2),
    budget_max DECIMAL(10, 2),
    estimated_hours DECIMAL(8, 2),
    quoted_price DECIMAL(10, 2),
    final_price DECIMAL(10, 2),
    current_state VARCHAR(50) DEFAULT 'NEW',
    -- States: NEW, ANALYZED, NEGOTIATION, REQUIREMENTS_COLLECTION, 
    -- ESTIMATION_READY, OFFER_SENT, AGREED, FUNDED, EXECUTION_READY, CLOSED
    is_scam BOOLEAN DEFAULT FALSE,
    is_illegal BOOLEAN DEFAULT FALSE,
    scam_score DECIMAL(3, 2) DEFAULT 0.0,
    requirements_doc TEXT,
    technical_spec TEXT,
    rejection_reason TEXT,
    source VARCHAR(100) DEFAULT 'email', -- email, telegram, manual
    source_message_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tasks table (sub-tasks within projects)
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    estimated_hours DECIMAL(8, 2),
    priority INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending', -- pending, in_progress, completed, blocked
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Project state transitions log
CREATE TABLE project_states (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    from_state VARCHAR(50),
    to_state VARCHAR(50) NOT NULL,
    changed_by VARCHAR(100), -- agent_name or 'owner' or 'system'
    reason TEXT,
    metadata JSONB, -- Additional state-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Project messages (email correspondence)
CREATE TABLE project_messages (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    direction VARCHAR(10) NOT NULL, -- inbound, outbound
    sender_email VARCHAR(255),
    recipient_email VARCHAR(255),
    subject VARCHAR(500),
    body TEXT,
    html_body TEXT,
    message_id VARCHAR(255), -- Email message ID
    in_reply_to VARCHAR(255), -- Reference to previous message
    is_processed BOOLEAN DEFAULT FALSE,
    metadata JSONB, -- Headers, attachments info, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent logs (for debugging and monitoring)
CREATE TABLE agent_logs (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    input_data JSONB,
    output_data JSONB,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    execution_time_ms INTEGER,
    tokens_used INTEGER,
    cost DECIMAL(10, 6),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- System settings (runtime configuration)
CREATE TABLE system_settings (
    id SERIAL PRIMARY KEY,
    setting_key VARCHAR(100) UNIQUE NOT NULL,
    setting_value TEXT NOT NULL,
    value_type VARCHAR(50), -- string, integer, float, boolean, json
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent instructions (editable prompts)
CREATE TABLE agent_instructions (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) UNIQUE NOT NULL,
    instruction_text TEXT NOT NULL,
    system_prompt TEXT,
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_clients_email ON clients(email);
CREATE INDEX idx_projects_client_id ON projects(client_id);
CREATE INDEX idx_projects_current_state ON projects(current_state);
CREATE INDEX idx_projects_created_at ON projects(created_at);
CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_project_states_project_id ON project_states(project_id);
CREATE INDEX idx_project_messages_project_id ON project_messages(project_id);
CREATE INDEX idx_project_messages_created_at ON project_messages(created_at);
CREATE INDEX idx_agent_logs_agent_name ON agent_logs(agent_name);
CREATE INDEX idx_agent_logs_created_at ON agent_logs(created_at);
CREATE INDEX idx_system_settings_key ON system_settings(setting_key);

-- Insert default system settings
INSERT INTO system_settings (setting_key, setting_value, value_type, description) VALUES
('hourly_rate', '50.0', 'float', 'Base hourly rate for project estimation'),
('auto_negotiation_enabled', 'true', 'boolean', 'Enable automatic negotiation with clients'),
('auto_invoice_enabled', 'true', 'boolean', 'Enable automatic invoice generation'),
('prepayment_percentage', '50', 'integer', 'Percentage of prepayment required'),
('max_negotiation_rounds', '5', 'integer', 'Maximum number of negotiation rounds before human escalation'),
('min_project_budget', '100', 'integer', 'Minimum acceptable project budget'),
('max_project_budget', '50000', 'integer', 'Maximum automatic project budget (requires human approval above)'),
('scam_filter_threshold', '0.7', 'float', 'Threshold for scam detection (0-1)');

-- Insert default agent instructions
INSERT INTO agent_instructions (agent_name, instruction_text, system_prompt) VALUES
('email_parser', 
 'Extract project details from email: title, description, budget, deadline, requirements. Identify client information.',
 'You are an expert email parser. Extract structured project information from freelance inquiry emails.'),

('scam_filter',
 'Analyze the project for scam indicators: unrealistic promises, suspicious payment terms, illegal activities, poor grammar with high budget.',
 'You are a scam detection specialist. Score projects from 0 (legitimate) to 1 (likely scam).'),

('classification_agent',
 'Classify project complexity: MICRO (<4h), SMALL (4-20h), MEDIUM (20-80h), LARGE (80-200h), RND (research needed).',
 'You are a project classification expert. Analyze project scope and assign appropriate complexity category.'),

('requirement_engineer',
 'Through conversation with client, gather complete technical requirements. Ask clarifying questions. Build structured specification.',
 'You are a requirements engineer. Your goal is to extract complete, unambiguous technical requirements from clients.'),

('estimation_agent',
 'Based on technical requirements, estimate hours needed for each component. Consider complexity, tech stack familiarity, and risks.',
 'You are an experienced project estimator. Provide realistic hour estimates broken down by task.'),

('dialogue_orchestrator',
 'Manage all client communication. Be professional, friendly, and clear. Handle negotiations, answer questions, and guide to agreement.',
 'You are a professional freelance business development manager. Communicate clearly and build trust with clients.'),

('offer_generator',
 'Generate professional commercial proposal including: scope, deliverables, timeline, price breakdown, payment terms, and next steps.',
 'You are a proposal writer. Create compelling, clear, and professional commercial offers.');

-- Create view for project dashboard
CREATE VIEW project_dashboard AS
SELECT 
    p.id,
    p.title,
    p.current_state,
    p.complexity,
    p.quoted_price,
    p.estimated_hours,
    c.name AS client_name,
    c.email AS client_email,
    c.reputation_score,
    p.created_at,
    p.updated_at,
    (SELECT COUNT(*) FROM project_messages pm WHERE pm.project_id = p.id) AS message_count,
    (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id) AS task_count
FROM projects p
LEFT JOIN clients c ON p.client_id = c.id
ORDER BY p.updated_at DESC;

-- Function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for automatic timestamp updates
CREATE TRIGGER update_clients_updated_at BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE clients IS 'Client information and reputation tracking';
COMMENT ON TABLE projects IS 'Main projects table with state machine tracking';
COMMENT ON TABLE tasks IS 'Sub-tasks within projects for granular tracking';
COMMENT ON TABLE project_states IS 'Audit log of all project state transitions';
COMMENT ON TABLE project_messages IS 'All email correspondence related to projects';
COMMENT ON TABLE agent_logs IS 'Logging of all AI agent actions for debugging and cost tracking';
COMMENT ON TABLE system_settings IS 'Runtime configurable system settings';
COMMENT ON TABLE agent_instructions IS 'Editable AI agent prompts and instructions';
