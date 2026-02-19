"""Cleanup junk projects created from newsletter/spam emails"""
from app.database import Database

with Database.get_cursor() as cur:
    # Show current projects
    cur.execute("SELECT id, title, current_state FROM projects ORDER BY id")
    projects = cur.fetchall()
    print(f"Total projects: {len(projects)}")
    for p in projects:
        title = p["title"][:70] if p["title"] else "NO TITLE"
        print(f"  #{p['id']}: [{p['current_state']}] {title}")
    
    # Count messages with NULL recipient
    cur.execute("SELECT COUNT(*) as cnt FROM project_messages WHERE recipient_email IS NULL AND direction = 'outbound'")
    null_count = cur.fetchone()["cnt"]
    print(f"\nOutbound messages with NULL recipient: {null_count}")
    
    # Count pending outbound
    cur.execute("SELECT COUNT(*) as cnt FROM project_messages WHERE direction = 'outbound' AND is_processed = FALSE")
    pending = cur.fetchone()["cnt"]
    print(f"Pending outbound messages: {pending}")

print("\n--- Cleaning up ---")

with Database.get_cursor() as cur:
    # Delete junk projects (id >= 4, created from spam emails)
    cur.execute("DELETE FROM agent_logs WHERE project_id >= 4")
    print(f"Deleted agent_logs for junk projects: {cur.rowcount}")
    
    cur.execute("DELETE FROM project_states WHERE project_id >= 4")
    print(f"Deleted project_states for junk projects: {cur.rowcount}")
    
    cur.execute("DELETE FROM project_messages WHERE project_id >= 4")
    print(f"Deleted project_messages for junk projects: {cur.rowcount}")
    
    cur.execute("DELETE FROM tasks WHERE project_id >= 4")
    print(f"Deleted tasks for junk projects: {cur.rowcount}")
    
    cur.execute("DELETE FROM projects WHERE id >= 4")
    print(f"Deleted junk projects: {cur.rowcount}")

    # Mark outbound messages with NULL recipient as processed (can't send anyway)
    cur.execute("UPDATE project_messages SET is_processed = TRUE WHERE recipient_email IS NULL AND direction = 'outbound'")
    print(f"Marked NULL-recipient outbound messages as processed: {cur.rowcount}")

print("\nDone! Database cleaned up.")
