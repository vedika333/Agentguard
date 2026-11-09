"""Local approval dashboard UI (server-rendered, zero external assets, live-refreshing)."""
import html, time

e = html.escape

CSS = """
:root{--bg:#0b0f17;--panel:#121826;--panel2:#0f1522;--line:#1f2a3d;--txt:#e6edf7;--mut:#8a97ad;
--red:#ef4444;--amber:#f59e0b;--green:#22c55e;--blue:#3b82f6;--violet:#8b5cf6}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 500px at 10% -10%,#16213a 0,transparent 60%),var(--bg);
color:var(--txt);font:14px/1.5 -apple-system,Segoe UI,Inter,Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:26px}
.brand{display:flex;align-items:center;gap:12px}.brand h1{margin:0;font-size:22px;letter-spacing:.2px}
.brand p{margin:0;color:var(--mut);font-size:12.5px}
.logo{width:40px;height:40px;border-radius:11px;background:linear-gradient(135deg,var(--blue),var(--violet));display:grid;place-items:center}
.pill{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--panel);padding:6px 12px;border-radius:999px;color:var(--mut);font-size:12px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 0 0 rgba(34,197,94,.7);animation:p 1.8s infinite}
@keyframes p{70%{box-shadow:0 0 0 8px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:28px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.stat b{display:block;font-size:26px;line-height:1.1}.stat span{color:var(--mut);font-size:12px}
.stat.red b{color:var(--red)}.stat.green b{color:var(--green)}.stat.blue b{color:var(--blue)}.stat.amber b{color:var(--amber)}
h2{font-size:13px;letter-spacing:.9px;text-transform:uppercase;color:var(--mut);margin:26px 0 12px;display:flex;align-items:center;gap:8px}
.count{background:var(--red);color:#fff;border-radius:999px;font-size:11px;padding:1px 8px;letter-spacing:0}
.card{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--red);border-radius:12px;padding:16px 18px;margin-bottom:14px;
box-shadow:0 8px 30px rgba(0,0,0,.35)}.card.medium{border-left-color:var(--amber)}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.meta{color:var(--mut);font-size:12.5px}.meta code{background:var(--panel2);padding:1px 6px;border-radius:5px}
.term{background:#05080e;border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:12px 0;
font:13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;color:#d6e4ff;overflow:auto;white-space:pre-wrap;word-break:break-all}
.term:before{content:"$ ";color:var(--green)}
ul.why{margin:6px 0 14px;padding-left:18px;color:#fca5a5}ul.why li{margin:2px 0}
.btns{display:flex;gap:10px}
a.act{cursor:pointer;text-decoration:none;color:#fff;font-weight:600;padding:9px 22px;border-radius:8px;transition:.15s;border:1px solid transparent}
a.ok{background:var(--green);color:#052e14}a.ok:hover{filter:brightness(1.1);transform:translateY(-1px)}
a.no{background:transparent;border-color:var(--red);color:var(--red)}a.no:hover{background:var(--red);color:#fff}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11.5px;font-weight:600;letter-spacing:.3px}
.b-high{background:rgba(239,68,68,.15);color:#fca5a5}.b-medium{background:rgba(245,158,11,.15);color:#fcd34d}.b-low{background:rgba(34,197,94,.13);color:#86efac}
.s-approved{background:rgba(34,197,94,.15);color:#86efac}.s-auto_approved{background:rgba(59,130,246,.15);color:#93c5fd}
.s-rejected{background:rgba(239,68,68,.15);color:#fca5a5}.s-expired{background:rgba(138,151,173,.15);color:#b6c2d6}.s-pending{background:rgba(245,158,11,.15);color:#fcd34d}
.empty{border:1px dashed var(--line);border-radius:12px;padding:30px;text-align:center;color:var(--mut)}
.tbl{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:13px}th{color:var(--mut);font-weight:500;text-align:left;padding:10px 14px;background:var(--panel2);font-size:12px}
td{padding:10px 14px;border-top:1px solid var(--line);vertical-align:top}td code{font:12.5px ui-monospace,Consolas,monospace;color:#cfe0ff;word-break:break-all}
footer{margin-top:30px;color:var(--mut);font-size:12px;text-align:center}
@media(max-width:800px){.stats{grid-template-columns:repeat(2,1fr)}}
"""

JS = """
async function refresh(){try{const t=await (await fetch(location.href,{cache:'no-store'})).text();
const d=new DOMParser().parseFromString(t,'text/html');const n=d.getElementById('app');
if(n)document.getElementById('app').innerHTML=n.innerHTML;}catch(e){}}
setInterval(refresh,2500);
document.addEventListener('click',async ev=>{const a=ev.target.closest('a.act');if(!a)return;
ev.preventDefault();a.textContent='Working…';a.style.pointerEvents='none';
try{await fetch(a.href)}catch(e){}refresh();});
"""

LOGO = ("<svg width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' "
        "stroke-linejoin='round'><path d='M12 2l8 3v6c0 5-3.5 9.3-8 11-4.5-1.7-8-6-8-11V5z'/><path d='M9 12l2 2 4-4'/></svg>")


def ago(ts):
    s = max(0, int(time.time() - (ts or 0)))
    if s < 60: return f"{s}s ago"
    if s < 3600: return f"{s // 60}m ago"
    return f"{s // 3600}h ago"


def _badge(kind, text):
    return f"<span class='badge {kind}'>{e(text)}</span>"


def render(pending, rows, link, provider):
    n = lambda f: sum(1 for r in rows if f(r))
    stats = [("blue", len(rows), "Commands intercepted"),
             ("green", n(lambda r: r["status"] == "auto_approved"), "Auto-approved (safe)"),
             ("red", n(lambda r: r["risk"] == "high"), "High-risk caught"),
             ("green", n(lambda r: r["status"] == "approved"), "Approved by humans"),
             ("amber", n(lambda r: r["status"] in ("rejected", "expired")), "Rejected / expired")]
    tiles = "".join(f"<div class='stat {c}'><b>{v}</b><span>{e(t)}</span></div>" for c, v, t in stats)

    cards = "".join(
        f"""<div class='card {e(p['risk'])}'>
<div class='row'><div>{_badge('b-' + p['risk'], p['risk'].upper() + ' RISK')}
<span class='meta'>&nbsp; agent <b>{e(p['agent'] or '-')}</b> &middot; request <code>{e(p['id'])}</code> &middot; {ago(p['created_at'])}</span></div></div>
<div class='term'>{e(p['command'])}</div>
<ul class='why'>{''.join('<li>' + e(x) + '</li>' for x in p['reasons'])}</ul>
<div class='btns'><a class='act ok' href='{e(link(p['id'], 'approve'))}&by=dashboard'>Approve &amp; run</a>
<a class='act no' href='{e(link(p['id'], 'reject'))}&by=dashboard'>Reject</a></div></div>"""
        for p in pending) or "<div class='empty'>&#10003; No pending approvals &mdash; agents are waiting for nothing.</div>"

    trs = "".join(
        f"<tr><td class='meta'>{ago(r['created_at'])}</td><td>{_badge('s-' + r['status'], r['status'].replace('_', ' '))}</td>"
        f"<td>{_badge('b-' + r['risk'], r['risk'])}</td><td><code>{e(r['command'][:160])}</code></td>"
        f"<td>{e(r['agent'] or '-')}</td><td>{e(r['decided_by'] or '-')}</td>"
        f"<td>{'' if r['exit_code'] is None else r['exit_code']}</td></tr>" for r in rows[:15]) \
        or "<tr><td colspan='7' class='meta' style='padding:20px;text-align:center'>No commands yet</td></tr>"

    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>AgentGuard &middot; Approval Gateway</title><style>{CSS}</style></head><body><div class='wrap'>
<header><div class='brand'><div class='logo'>{LOGO}</div><div><h1>AgentGuard</h1>
<p>Human-in-the-loop approval gateway for AI agents</p></div></div>
<span class='pill'><span class='dot'></span>Live &middot; chat: {e(provider)}</span></header>
<div id='app'>
<div class='stats'>{tiles}</div>
<h2>Awaiting approval {f"<span class='count'>{len(pending)}</span>" if pending else ''}</h2>{cards}
<h2>Audit log</h2><div class='tbl'><table><tr><th>When</th><th>Status</th><th>Risk</th><th>Command</th><th>Agent</th><th>Decided by</th><th>Exit</th></tr>{trs}</table></div>
</div><footer>AgentGuard &middot; every decision is recorded in SQLite &middot; built for the Flip the Switch hackathon</footer>
</div><script>{JS}</script></body></html>"""


def result_page(msg, ok=True):
    color = "#22c55e" if ok else "#ef4444"
    return (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>AgentGuard</title><style>{CSS}</style></head><body><div class='wrap' style='max-width:520px;margin-top:12vh'>"
            f"<div class='card' style='border-left-color:{color};text-align:center'><div class='logo' style='margin:0 auto 14px'>{LOGO}</div>"
            f"<h2 style='justify-content:center;margin:0 0 8px'>AgentGuard</h2><p style='font-size:17px;margin:0'>{e(msg)}</p>"
            f"<p class='meta'>You can close this tab.</p></div></div></body></html>")