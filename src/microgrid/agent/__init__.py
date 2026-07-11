"""Data agent (task 06): natural-language Q&A over the SQL layer.

An LLM plans read-only SQL against the PostgreSQL tables built in the SQL
task, via three tools (list_tables / get_schema / run_query), inside a
provider-agnostic tool-calling loop. Safety is layered: a pure-function SQL
validator (guard.py) plus a READ ONLY transaction with a statement timeout
(tools.py) — the model's SQL is never trusted, the database enforces the rule.
"""
