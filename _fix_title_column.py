"""One-time fix: expand projects.title column to VARCHAR(500)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import Database

with Database.get_cursor() as cur:
    # Get the view definition first
    cur.execute("SELECT pg_get_viewdef('project_dashboard', true)")
    view_def = cur.fetchone()
    if view_def:
        view_sql = list(view_def.values())[0] if isinstance(view_def, dict) else view_def[0]
        print(f"View definition saved ({len(view_sql)} chars)")
    else:
        view_sql = None
        print("No project_dashboard view found")

    # Drop view, alter column, recreate view
    cur.execute("DROP VIEW IF EXISTS project_dashboard")
    print("Dropped project_dashboard view")

    cur.execute("ALTER TABLE projects ALTER COLUMN title TYPE VARCHAR(500)")
    print("OK: projects.title → VARCHAR(500)")

    if view_sql:
        cur.execute(f"CREATE VIEW project_dashboard AS {view_sql}")
        print("Recreated project_dashboard view")
