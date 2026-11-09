"""Risk evaluation (regex rules) + sandboxed-ish command execution."""
import os, re, subprocess

# (pattern, reason). Matched against the WHOLE command string, so chained commands (a && rm -rf b) are caught.
HIGH = [
    (r"\brm\s+(-[a-z]*\s+)*-[a-z]*(rf|fr)[a-z]*\b|\brm\s+.*--recursive.*--force|\brm\s+.*--force.*--recursive", "Recursive forced delete (rm -rf)"),
    (r"\bdrop\s+(database|schema|table)\b", "Destructive SQL: DROP"),
    (r"\btruncate\s+table\b", "Destructive SQL: TRUNCATE"),
    (r"\bdelete\s+from\s+\w+\s*(;|$)", "DELETE without WHERE clause"),
    (r"\bterraform\s+(destroy|apply\s+.*-auto-approve)", "Terraform infrastructure destroy/auto-apply"),
    (r"\bgit\s+push\b.*(\s-f\b|--force\b)", "Force push rewrites remote history"),
    (r"(^|[;&|\s])sudo\b", "Privilege escalation (sudo)"),
    (r"\bmkfs(\.\w+)?\b|\bdd\s+.*\bof=/dev/", "Disk formatting / raw device write"),
    (r"\bchmod\s+(-R\s+)?777\s+/", "World-writable permissions on root path"),
    (r"(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b", "Pipe remote script into shell"),
    (r"\bkubectl\s+delete\b|\bdocker\s+system\s+prune", "Cluster/container mass deletion"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "Host shutdown/reboot"),
    (r":\(\)\s*\{.*:\|:.*\}", "Fork bomb"),
    (r"\beval\b|base64\s+(-d|--decode)[^|]*\|\s*(ba)?sh", "Obfuscated/dynamic execution"),
    (r">\s*/dev/sd[a-z]", "Overwrite block device"),
    # Windows (cmd / PowerShell)
    (r"\b(rmdir|rd)\b.*\s/s\b", "Recursive directory delete (rmdir /s)"),
    (r"\bdel\b.*\s/[sfq]\b", "Forced/recursive file delete (del /s /f /q)"),
    (r"\bremove-item\b.*-recurse|\bri\b.*-recurse", "Recursive delete (Remove-Item -Recurse)"),
    (r"\bformat\s+[a-z]:|\breg\s+delete\b|\bdiskpart\b", "Disk format / registry delete"),
    (r"\b(stop-computer|restart-computer)\b", "Host shutdown/restart"),
]
MEDIUM = [
    (r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f|push\b|rebase)", "Git history/working tree mutation"),
    (r"\brm\b", "File deletion"),
    (r"\b(mv|chmod|chown)\b", "File move / permission change"),
    (r"\b(pip3?|npm|yarn|apt(-get)?|brew)\s+(install|uninstall|remove)\b", "Package install/removal"),
    (r"\b(curl|wget|ssh|scp|nc)\b", "Network access"),
    (r"\b(kill|killall|pkill)\b", "Process termination"),
    (r"\bdocker\s+(rm|rmi|stop|kill)\b", "Container removal/stop"),
    (r"\bdelete\s+from\b|\bupdate\s+\w+\s+set\b", "SQL data modification"),
]


def evaluate_risk(command: str) -> dict:
    cmd = command.strip().lower()
    high = [why for pat, why in HIGH if re.search(pat, cmd)]
    if high:
        return {"level": "high", "reasons": high}
    med = [why for pat, why in MEDIUM if re.search(pat, cmd)]
    if med:
        return {"level": "medium", "reasons": med}
    return {"level": "low", "reasons": ["No risky patterns detected"]}


def execute(command: str) -> dict:
    timeout = int(os.getenv("EXEC_TIMEOUT_SECONDS", "30"))
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout,
                           cwd=os.getenv("EXEC_CWD") or None)
        return {"exit_code": p.returncode, "stdout": p.stdout[-3000:], "stderr": p.stderr[-3000:]}
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "stdout": "", "stderr": f"Timed out after {timeout}s"}
    except Exception as e:  # noqa
        return {"exit_code": 1, "stdout": "", "stderr": f"Execution error: {e}"}