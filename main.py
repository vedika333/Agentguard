"""AgentGuard - human-in-the-loop approval gateway for CLI AI agents.

  python main.py                      -> start gateway server
  python main.py run "<command>"      -> CLI agent wrapper (intercepts, waits for approval, prints result)
  python main.py demo [--auto-approve]-> end-to-end self-test (server + safe + dangerous command)
"""
import argparse, html, json, os, sys, threading, time, urllib.request, urllib.error

# Windows consoles default to cp1252 and crash on emoji
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

# tiny .env loader (no extra dependency)
if os.path.exists(".env"):
    for line in open(".env"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import audit, dashboard as ui, chat_webhook as chat
from interceptor import evaluate_risk, execute

PORT = int(os.getenv("PORT", "8000"))
TTL = int(os.getenv("APPROVAL_TTL_SECONDS", "300"))
NEEDS_APPROVAL = {x.strip() for x in os.getenv("REQUIRE_APPROVAL_LEVELS", "high").split(",")}
APPROVERS = {x.strip().lower() for x in os.getenv("APPROVERS", "").split(",") if x.strip()}

app = FastAPI(title="AgentGuard")
audit.init()


class InterceptIn(BaseModel):
    command: str
    agent: str = "cli-agent"


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Local-only approval UI (page contains signed approve links, so never expose it remotely)."""
    if request.headers.get("x-forwarded-for") or (request.client and request.client.host not in ("127.0.0.1", "::1", "localhost")):
        raise HTTPException(403, "Dashboard is local-only. Use the chat card links instead.")
    audit.expire_stale(TTL)
    return HTMLResponse(ui.render(audit.pending(), audit.recent(200), chat.link, chat.provider()))


@app.get("/health")
def health():
    return {"ok": True, "provider": chat.provider()}


@app.post("/api/intercept")
def intercept(body: InterceptIn):
    cmd = body.command.strip()
    if not cmd:
        raise HTTPException(400, "empty command")
    risk = evaluate_risk(cmd)
    if risk["level"] not in NEEDS_APPROVAL:  # safe path: run now, still audited
        rid = audit.create(cmd, body.agent, risk["level"], risk["reasons"], "auto_approved")
        result = execute(cmd)
        audit.record_result(rid, result)
        if risk["level"] == "medium":
            chat.send_text(f"ℹ️ AgentGuard auto-ran MEDIUM-risk command from {body.agent}: `{cmd}`")
        return {"id": rid, "status": "auto_approved", "risk": risk, "result": result}
    rid = audit.create(cmd, body.agent, risk["level"], risk["reasons"], "pending")
    chat.send_approval_card(audit.get(rid))
    resp = {"id": rid, "status": "pending", "risk": risk}
    if chat.provider() == "console":  # dev convenience only
        resp["approve_url"] = chat.link(rid, "approve")
    return resp


@app.get("/api/status/{rid}")
def status(rid: str):
    audit.expire_stale(TTL)
    r = audit.get(rid)
    if not r:
        raise HTTPException(404, "unknown request")
    return {k: r[k] for k in ("id", "status", "risk", "reasons", "decided_by", "exit_code", "stdout", "stderr")}


@app.get("/api/audit")
def audit_log(limit: int = 50):
    return audit.recent(limit)


async def _decide(rid: str, action: str, request: Request):
    is_post = request.method == "POST"
    body = {}
    if is_post:
        try:
            body = await request.json()
        except Exception:
            body = {}
    token = request.query_params.get("token", "")
    user = body.get("user_name") or request.query_params.get("by") or "chat-user"

    def reply(msg, ok=True, color="#5cb85c"):
        if is_post:  # Mattermost interactive-message response
            data = {"ephemeral_text": msg}
            if ok:
                data["update"] = {"props": {"attachments": [{"color": color, "title": f"AgentGuard · {rid}", "text": msg}]}}
            return JSONResponse(data)
        return HTMLResponse(ui.result_page(msg, ok), status_code=200 if ok else 400)

    audit.expire_stale(TTL)
    r = audit.get(rid)
    if not r:
        return reply("Unknown request", ok=False)
    if not chat.verify(rid, action, token):
        return reply("Invalid or missing token", ok=False)
    if APPROVERS and user.lower() not in APPROVERS:
        return reply(f"{user} is not an authorised approver", ok=False)
    if not audit.decide(rid, "approved" if action == "approve" else "rejected", user):
        return reply(f"Already {audit.get(rid)['status']} - no action taken", ok=False)

    if action == "reject":
        chat.send_text(f"🛑 `{r['command']}` REJECTED by @{user}. Nothing was executed.")
        return reply(f"🛑 Rejected by @{user}", color="#d9534f")

    result = await run_in_threadpool(execute, r["command"])
    audit.record_result(rid, result)
    chat.send_text(f"✅ Approved by @{user}\n" + chat.format_result(r, result))
    return reply(f"✅ Approved by @{user} - executed (exit {result['exit_code']})")


@app.api_route("/api/approve/{rid}", methods=["GET", "POST"])
async def approve(rid: str, request: Request):
    return await _decide(rid, "approve", request)


@app.api_route("/api/reject/{rid}", methods=["GET", "POST"])
async def reject(rid: str, request: Request):
    return await _decide(rid, "reject", request)


# ---------------------------------------------------------------- CLI agent wrapper
def _http(method, url, payload=None):
    req = urllib.request.Request(url, json.dumps(payload).encode() if payload else None,
                                 {"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Gateway error {e.code}: {e.read().decode()}")


def guarded_run(command, agent="demo-agent", base=None, auto_approve=False, wait=TTL + 10):
    """Drop-in replacement for subprocess in an agent: nothing risky runs without a human."""
    base = base or f"http://127.0.0.1:{PORT}"
    print(f"\n🤖 [{agent}] proposes: $ {command}")
    res = _http("POST", f"{base}/api/intercept", {"command": command, "agent": agent})
    print(f"🔎 Risk: {res['risk']['level'].upper()} - {'; '.join(res['risk']['reasons'])}")
    if res["status"] == "auto_approved":
        r = res["result"]
        print(f"⚡ Auto-executed (exit {r['exit_code']}):\n{r['stdout']}{r['stderr']}")
        return r
    print(f"⏸️  HALTED - waiting for human approval in chat (request {res['id']})...")
    if auto_approve and res.get("approve_url"):
        threading.Timer(3, lambda: urllib.request.urlopen(res["approve_url"]).read()).start()
        print("   (--auto-approve: simulating a human click in 3s)")
    deadline = time.time() + wait
    while time.time() < deadline:
        s = _http("GET", f"{base}/api/status/{res['id']}")
        if s["status"] != "pending":
            break
        time.sleep(1.5)
    else:
        s = {"status": "timeout"}
    if s["status"] == "approved":
        print(f"✅ Approved by @{s['decided_by']} - output:\n{s['stdout']}{s['stderr']}")
        return s
    print(f"🛑 Command NOT executed: {s['status']}")
    return s


def _serve_background():
    import uvicorn
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(50):
        try:
            _http("GET", f"http://127.0.0.1:{PORT}/health")
            return
        except BaseException:
            time.sleep(0.2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    run_p = sub.add_parser("run"); run_p.add_argument("command"); run_p.add_argument("--auto-approve", action="store_true")
    demo_p = sub.add_parser("demo"); demo_p.add_argument("--auto-approve", action="store_true")
    a = ap.parse_args()

    if a.cmd == "run":
        sys.exit(0 if guarded_run(a.command, auto_approve=a.auto_approve).get("exit_code") == 0 else 1)
    elif a.cmd == "demo":
        _serve_background()
        win = sys.platform == "win32"
        guarded_run("echo hello from a safe command && dir" if win else "echo hello from a safe command && ls", auto_approve=a.auto_approve)
        guarded_run("mkdir agentguard_demo && rmdir /s /q agentguard_demo" if win else
                    "mkdir -p /tmp/agentguard_demo && rm -rf /tmp/agentguard_demo", auto_approve=a.auto_approve)
        print("\n📜 Audit log:"); [print("  ", row) for row in audit.recent(5)]
    else:
        import uvicorn
        print(f"🛡️  AgentGuard on :{PORT} | provider={chat.provider()} | approval needed for: {sorted(NEEDS_APPROVAL)}")
        uvicorn.run(app, host="0.0.0.0", port=PORT)