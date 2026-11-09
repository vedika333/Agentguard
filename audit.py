"""SQLite audit log: every command, its risk, the human decision, and the result."""
import os, sqlite3, time, uuid, json

DB_PATH = os.getenv("AUDIT_DB", "agentguard.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY, agent TEXT, command TEXT NOT NULL,
            risk TEXT NOT NULL, reasons TEXT, status TEXT NOT NULL,
            created_at REAL, decided_at REAL, decided_by TEXT,
            exit_code INTEGER, stdout TEXT, stderr TEXT)""")


def create(command, agent, risk, reasons, status):
    rid = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute("INSERT INTO requests (id,agent,command,risk,reasons,status,created_at) VALUES (?,?,?,?,?,?,?)",
                  (rid, agent, command, risk, json.dumps(reasons), status, time.time()))
    return rid


def expire_stale(ttl):
    with _conn() as c:
        c.execute("UPDATE requests SET status='expired', decided_at=? WHERE status='pending' AND created_at<?",
                  (time.time(), time.time() - ttl))


def get(rid):
    with _conn() as c:
        row = c.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["reasons"] = json.loads(d["reasons"] or "[]")
    return d


def decide(rid, status, by):
    """Atomic pending -> approved/rejected. Returns False if already decided/expired (no double execution)."""
    with _conn() as c:
        cur = c.execute("UPDATE requests SET status=?, decided_by=?, decided_at=? WHERE id=? AND status='pending'",
                        (status, by, time.time(), rid))
        return cur.rowcount == 1


def record_result(rid, result):
    with _conn() as c:
        c.execute("UPDATE requests SET exit_code=?, stdout=?, stderr=? WHERE id=?",
                  (result["exit_code"], result["stdout"], result["stderr"], rid))


def recent(limit=50):
    with _conn() as c:
        rows = c.execute("SELECT id,agent,command,risk,status,decided_by,exit_code,created_at FROM requests "
                         "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def pending():
    with _conn() as c:
        rows = c.execute("SELECT id FROM requests WHERE status='pending' ORDER BY created_at DESC").fetchall()
    return [get(r["id"]) for r in rows]