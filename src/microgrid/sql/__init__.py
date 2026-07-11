"""SQL layer: load project artifacts into PostgreSQL and query them back.

``extract`` holds pure (artifact -> DataFrame/rows) builders with no database
dependency; ``db`` holds the thin PostgreSQL access layer (env-only connection,
schema application, COPY-into-staging upsert). Orchestration lives in
``scripts/load_to_db.py``.
"""
