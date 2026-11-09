"""Chat integration: signed approve/reject links + approval cards for Mattermost / Slack / console."""
import hashlib, hmac, json, os, secrets, urllib.request

SECRET = os.getenv("AGENTGUARD_SECRET") or secrets.token_hex(16)
COLORS = {"high": "#d9534f", "medium": "#f0ad4e", "low": "#5cb85c"}


def provider():
    return os.getenv("CHAT_PROVIDER", "console").lower()


def sign(rid: str, action: str) -> str:
    return hmac.new(SECRET.encode(), f"{rid}:{action}".encode(), hashlib.sha256).hexdigest()[:20]


def verify(rid: str, action: str, token: str) -> bool:
    return hmac.compare_digest(sign(rid, action), token or "")


def link(rid: str, action: str) -> str:
    base = os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/{action}/{rid}?token={sign(rid, action)}"


def _post(payload: dict):
    url = os.getenv("CHAT_WEBHOOK_URL")
    if provider() == "console" or not url:
        return
    try:
        req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # chat outage must never crash the gateway
        print(f"[chat] webhook failed: {e}")


def send_approval_card(r: dict):
    why = "\n".join(f"• {x}" for x in r["reasons"])
    title = f"🛡️ AgentGuard: approval required ({r['risk'].upper()} risk)"
    if provider() == "console":
        print(f"\n{'=' * 60}\n{title}\nAgent: {r['agent']}   ID: {r['id']}\n$ {r['command']}\n{why}\n"
              f"Approve: {link(r['id'], 'approve')}\nReject:  {link(r['id'], 'reject')}\n{'=' * 60}\n")
    elif provider() == "slack":
        _post({"text": title, "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"```{r['command']}```"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Agent*\n{r['agent']}"},
                {"type": "mrkdwn", "text": f"*Request ID*\n{r['id']}"}]},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Why it was flagged*\n{why}"}},
            {"type": "actions", "elements": [
                {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Approve"}, "url": link(r["id"], "approve")},
                {"type": "button", "style": "danger", "text": {"type": "plain_text", "text": "Reject"}, "url": link(r["id"], "reject")}]}]})
    else:  # mattermost interactive message
        def act(a, name, style):
            return {"id": a, "name": name, "style": style,
                    "integration": {"url": link(r["id"], a), "context": {"action": a}}}
        _post({"attachments": [{
            "color": COLORS.get(r["risk"], "#999"), "title": title,
            "text": f"```\n{r['command']}\n```",
            "fields": [{"short": True, "title": "Agent", "value": r["agent"]},
                       {"short": True, "title": "Request ID", "value": r["id"]},
                       {"short": False, "title": "Why it was flagged", "value": why}],
            "actions": [act("approve", "Approve", "good"), act("reject", "Reject", "danger")]}]})


def send_text(text: str):
    print(f"[chat] {text}")
    _post({"text": text})


def format_result(r: dict, result: dict) -> str:
    out = (result["stdout"] or "").strip() or "(no stdout)"
    err = (result["stderr"] or "").strip()
    msg = f"✅ `{r['command']}` finished (exit {result['exit_code']})\n```\n{out}\n```"
    return msg + (f"\nstderr:\n```\n{err}\n```" if err else "")
