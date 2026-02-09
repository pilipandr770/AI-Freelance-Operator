"""
Add test data to database
"""
from app.database import Database
import json

print("Creating test data...")

try:
    with Database.get_cursor() as cursor:
        # Create test client
        cursor.execute("""
            INSERT INTO clients (email, name, company, country, total_projects, successful_projects, total_paid, reputation_score)
            VALUES ('john.smith@techcorp.com', 'John Smith', 'TechCorp Inc.', 'USA', 2, 1, 3500.00, 0.85)
            RETURNING id
        """)
        client1_id = cursor.fetchone()['id']
        print(f"✓ Created client #1: John Smith (ID: {client1_id})")
        
        # Create another test client
        cursor.execute("""
            INSERT INTO clients (email, name, company, country, total_projects, reputation_score)
            VALUES ('sarah@devstudio.com', 'Sarah Johnson', 'Dev Studio', 'Canada', 1, 0.90)
            RETURNING id
        """)
        client2_id = cursor.fetchone()['id']
        print(f"✓ Created client #2: Sarah Johnson (ID: {client2_id})")
        
        # Create test projects
        cursor.execute("""
            INSERT INTO projects 
            (client_id, title, description, current_state, complexity, budget_min, budget_max, 
             quoted_price, estimated_hours, tech_stack, category)
            VALUES 
            (%s, 'Build E-commerce Website', 
             'Need a full-featured e-commerce platform with Stripe integration, product catalog, shopping cart, and admin dashboard',
             'NEGOTIATION', 'MEDIUM', 4000, 6000, 5000.00, 100, %s, 'Web Development'),
            (%s, 'Mobile App Development',
             'iOS and Android app for food delivery service with real-time tracking and payment processing',
             'ESTIMATION_READY', 'LARGE', 8000, 12000, 10000.00, 200, %s, 'Mobile Development'),
            (%s, 'API Integration',
             'Integrate third-party APIs for weather, maps, and payment services',
             'OFFER_SENT', 'SMALL', 1000, 2000, 1500.00, 30, %s, 'API Development')
        """, (
            client1_id, ['Python', 'Django', 'React', 'PostgreSQL', 'Stripe'],
            client1_id, ['React Native', 'Node.js', 'MongoDB', 'Firebase'],
            client2_id, ['Python', 'FastAPI', 'REST API']
        ))
        print(f"✓ Created 3 test projects")
        
        # Create some project messages
        cursor.execute("""
            INSERT INTO project_messages (project_id, direction, sender_email, recipient_email, subject, body)
            VALUES 
            (1, 'inbound', 'john.smith@techcorp.com', 'your@email.com', 
             'E-commerce Website Project', 'Hi, I need a website for my online store...'),
            (1, 'outbound', 'your@email.com', 'john.smith@techcorp.com',
             'Re: E-commerce Website Project', 'Thank you for reaching out. I can help with that...')
        """)
        print(f"✓ Created test messages")
        
    print("\n✅ All test data created successfully!")
    print("\nYou can now view:")
    print("  - Projects: http://localhost:5000/admin/projects")
    print("  - Clients: http://localhost:5000/admin/clients")
    
except Exception as e:
    print(f"❌ Error: {e}")
