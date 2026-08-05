# SQLite durability spike

Executable with Python standard-library `sqlite3` only. The runner creates temporary databases under `build/spikes/execution_durability/` or an OS temporary directory, enables foreign keys, evaluates WAL, uses explicit transactions, and never touches production runtime paths.
