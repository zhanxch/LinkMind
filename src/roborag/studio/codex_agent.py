"""Read native Codex login status without handling credentials."""
import os
import shutil
import subprocess


def login_status():
    executable = shutil.which(os.environ.get("LINKMIND_CODEX_BIN", "codex"))
    if not executable:
        return {"available": False, "logged_in": False, "label": "未安装 Codex CLI"}
    try:
        result = subprocess.run([executable, "login", "status"], capture_output=True, text=True, timeout=15)
        return {"available": True, "logged_in": result.returncode == 0,
                "label": "Codex 已登录" if result.returncode == 0 else "请先运行 codex login"}
    except subprocess.TimeoutExpired:
        return {"available": True, "logged_in": False, "label": "Codex 登录状态检查超时"}
