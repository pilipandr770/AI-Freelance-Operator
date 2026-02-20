import psycopg2, psycopg2.extras
conn = psycopg2.connect('postgresql://ittoken_db_user:Xm98VVSZv7cMJkopkdWRkgvZzC7Aly42@dpg-d0visga4d50c73ekmu4g-a.frankfurt-postgres.render.com/ittoken_db')
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Check if invoices table exists
cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'invoices')")
print('invoices table exists:', cur.fetchone()['exists'])

# Create invoices table
cur.execute("""
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    client_name VARCHAR(255),
    client_email VARCHAR(255),
    client_address TEXT,
    
    -- Line items stored as JSONB array
    line_items JSONB NOT NULL DEFAULT '[]',
    
    -- Amounts
    net_amount DECIMAL(10, 2) NOT NULL,
    vat_rate DECIMAL(5, 2) DEFAULT 0.00,
    vat_amount DECIMAL(10, 2) DEFAULT 0.00,
    gross_amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'EUR',
    
    -- Payment
    payment_terms TEXT,
    due_date DATE,
    is_paid BOOLEAN DEFAULT FALSE,
    paid_at TIMESTAMP,
    
    -- Invoice type
    invoice_type VARCHAR(50) DEFAULT 'full',  -- 'prepayment', 'full', 'final'
    
    -- PDF storage
    pdf_path TEXT,
    
    -- Metadata
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_invoices_project_id ON invoices(project_id);
CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices(invoice_number);
""")
conn.commit()
print('invoices table created')

# Add requirements_analysis column to projects (separate from technical_spec)
try:
    cur.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS requirements_analysis JSONB")
    conn.commit()
    print('requirements_analysis column added to projects')
except Exception as e:
    conn.rollback()
    print(f'requirements_analysis column: {e}')

# Add invoice_number sequence setting
try:
    cur.execute("""
        INSERT INTO system_settings (setting_key, setting_value, value_type, description)
        VALUES ('next_invoice_number', '1', 'integer', 'Next invoice sequential number')
        ON CONFLICT (setting_key) DO NOTHING
    """)
    conn.commit()
    print('next_invoice_number setting added')
except Exception as e:
    conn.rollback()
    print(f'invoice setting: {e}')

conn.close()
print('Done')
