# V41-PQ-001F5E Spike Environment Inventory

- Repository: `/Users/EYUSEFF/Documents/GitHub/EduTraderAI_v4_validation`
- Branch: `feature/edutrader-v4.1`
- Starting HEAD: `b33dfe34e0339cba305f26ea648d1407e3640af2`
- Python: 3.14.6
- SQLite library: 3.50.4
- `psql`: not available in PATH
- `postgres`: not available in PATH
- `pg_ctl`: not available in PATH
- Docker: not available in PATH
- PostgreSQL Python drivers: `psycopg=False`, `psycopg2=False`, `asyncpg=False`, `sqlalchemy=False`
- Repository dependency files: no PostgreSQL tooling dependency available for this spike
- Network/dependency requirement for PostgreSQL runtime: would be required, therefore not authorized in this slice
- Expected unrelated dirty file: `state/simulated_broker.json`, not touched by spike code

Conclusion: SQLite runtime evidence is available. PostgreSQL runtime evidence is unavailable; PostgreSQL is assessed statically.
