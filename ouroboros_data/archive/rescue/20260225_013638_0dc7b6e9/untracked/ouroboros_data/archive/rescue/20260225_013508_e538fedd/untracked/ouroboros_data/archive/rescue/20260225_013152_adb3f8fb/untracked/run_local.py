"""
Ouroboros — Local launcher (no Google Colab required).

Reads config from .env file. Stores state locally in ./ouroboros_data/.
Requires: OPENROUTER_API_KEY, TELEGRAM_BOT_TOKEN, TOTAL_BUDGET, GITHUB_TOKEN, GITHUB_USER, GITHUB_REPO

Usage:
    python run_local.py
"""

import logging
import os
import sys
import json
import time
import uuid
import pathlib
import subprocess
import datetime
import threading
import queue as _queue_mod
from typing import Any, Dict, List, Optional, Set, Tuple

# ----------------------------
# 0) Load .env
# ----------------------------
def load_dotenv(path=".env"):
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


from ouroboros.apply_patch import install as install_apply_patch
from ouroboros.llm import DEFAULT_LIGHT_MODEL
install_apply_patch()

# ----------------------------
# 1) Config (from env / .env)
# ----------------------------
def require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"\n❌ Missing required config: {name}")
        print(f"   Add it to your .env file: {name}=your_value_here\n")
        sys.exit(1)
    return val

OPENROUTER_API_KEY = require("OPENROUTER_API_KEY")
TELEGRAM_BOT_TOKEN = require("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN       = require("GITHUB_TOKEN")
GITHUB_USER        = require("GITHUB_USER")
GITHUB_REPO        = require("GITHUB_REPO")

try:
    TOTAL_BUDGET_LIMIT = float(require("TOTAL_BUDGET"))
except ValueError:
    print("❌ TOTAL_BUDGET must be a number (e.g. 5.00)")
    sys.exit(1)

OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

MAX_WORKERS      = int(os.environ.get("OUROBOROS_MAX_WORKERS", "2"))
MODEL_MAIN       = os.environ.get("OUROBOROS_MODEL",       "anthropic/claude-haiku-4-5")
MODEL_CODE       = os.environ.get("OUROBOROS_MODEL_CODE",  "anthropic/claude-haiku-4-5")
MODEL_LIGHT      = os.environ.get("OUROBOROS_MODEL_LIGHT", "anthropic/claude-haiku-4-5")

SOFT_TIMEOUT_SEC  = int(os.environ.get("OUROBOROS_SOFT_TIMEOUT_SEC", "600"))
HARD_TIMEOUT_SEC  = int(os.environ.get("OUROBOROS_HARD_TIMEOUT_SEC", "1800"))
DIAG_HEARTBEAT_SEC = int(os.environ.get("OUROBOROS_DIAG_HEARTBEAT_SEC", "60"))
DIAG_SLOW_CYCLE_SEC = int(os.environ.get("OUROBOROS_DIAG_SLOW_CYCLE_SEC", "20"))
BUDGET_REPORT_EVERY_MESSAGES = 10

# Push all config into env for modules that read from env
os.environ["OPENROUTER_API_KEY"]      = OPENROUTER_API_KEY
os.environ["OPENAI_API_KEY"]          = OPENAI_API_KEY
os.environ["ANTHROPIC_API_KEY"]       = ANTHROPIC_API_KEY
os.environ["GITHUB_USER"]             = GITHUB_USER
os.environ["GITHUB_REPO"]             = GITHUB_REPO
os.environ["OUROBOROS_MODEL"]         = MODEL_MAIN
os.environ["OUROBOROS_MODEL_CODE"]    = MODEL_CODE
os.environ["OUROBOROS_MODEL_LIGHT"]   = MODEL_LIGHT
os.environ["TELEGRAM_BOT_TOKEN"]      = TELEGRAM_BOT_TOKEN
os.environ["OUROBOROS_DIAG_HEARTBEAT_SEC"]  = str(DIAG_HEARTBEAT_SEC)
os.environ["OUROBOROS_DIAG_SLOW_CYCLE_SEC"] = str(DIAG_SLOW_CYCLE_SEC)

# ----------------------------
# 2) Local paths (replaces Google Drive)
# ----------------------------
BASE_DIR  = pathlib.Path(__file__).parent.resolve()
DRIVE_ROOT = BASE_DIR / "ouroboros_data"
REPO_DIR   = BASE_DIR  # We're already in the repo

for sub in ["state", "logs", "memory", "index", "locks", "archive"]:
    (DRIVE_ROOT / sub).mkdir(parents=True, exist_ok=True)

CHAT_LOG_PATH = DRIVE_ROOT / "logs" / "chat.jsonl"
if not CHAT_LOG_PATH.exists():
    CHAT_LOG_PATH.write_text("", encoding="utf-8")

# Clear stale mailbox from previous session
try:
    from ouroboros.owner_inject import get_pending_path
    _stale = get_pending_path(DRIVE_ROOT)
    if _stale.exists():
        _stale.unlink(missing_ok=True)
    _mailbox = DRIVE_ROOT / "memory" / "owner_mailbox"
    if _mailbox.exists():
        for _f in _mailbox.iterdir():
            _f.unlink(missing_ok=True)
except Exception:
    pass

# ----------------------------
# 3) Git constants
# ----------------------------
BRANCH_DEV    = "ouroboros"
BRANCH_STABLE = "ouroboros-stable"
REMOTE_URL    = f"https://{GITHUB_TOKEN}:x-oauth-basic@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

# ----------------------------
# 4) Initialize supervisor modules
# ----------------------------
from supervisor.state import (
    init as state_init, load_state, save_state, append_jsonl,
    update_budget_from_usage, status_text, rotate_chat_log_if_needed,
    init_state,
)
state_init(DRIVE_ROOT, TOTAL_BUDGET_LIMIT)
init_state()

from supervisor.telegram import (
    init as telegram_init, TelegramClient, send_with_budget, log_chat,
)
TG = TelegramClient(str(TELEGRAM_BOT_TOKEN))
telegram_init(
    drive_root=DRIVE_ROOT,
    total_budget_limit=TOTAL_BUDGET_LIMIT,
    budget_report_every=BUDGET_REPORT_EVERY_MESSAGES,
    tg_client=TG,
)

from supervisor.git_ops import (
    init as git_ops_init, ensure_repo_present, checkout_and_reset,
    sync_runtime_dependencies, import_test, safe_restart,
)
git_ops_init(
    repo_dir=REPO_DIR, drive_root=DRIVE_ROOT, remote_url=REMOTE_URL,
    branch_dev=BRANCH_DEV, branch_stable=BRANCH_STABLE,
)

from supervisor.queue import (
    enqueue_task, enforce_task_timeouts, enqueue_evolution_task_if_needed,
    persist_queue_snapshot, restore_pending_from_snapshot,
    cancel_task_by_id, queue_review_task, sort_pending,
)

from supervisor.workers import (
    init as workers_init, get_event_q, WORKERS, PENDING, RUNNING,
    spawn_workers, kill_workers, assign_tasks, ensure_workers_healthy,
    handle_chat_direct, _get_chat_agent, auto_resume_after_restart,
)
workers_init(
    repo_dir=REPO_DIR, drive_root=DRIVE_ROOT, max_workers=MAX_WORKERS,
    soft_timeout=SOFT_TIMEOUT_SEC, hard_timeout=HARD_TIMEOUT_SEC,
    total_budget_limit=TOTAL_BUDGET_LIMIT,
    branch_dev=BRANCH_DEV, branch_stable=BRANCH_STABLE,
)

from supervisor.events import dispatch_event

# ----------------------------
# 5) Bootstrap repo
# ----------------------------
ensure_repo_present()
ok, msg = safe_restart(reason="bootstrap", unsynced_policy="rescue_and_reset")
assert ok, f"Bootstrap failed: {msg}"

# ----------------------------
# 6) Start workers
# ----------------------------
kill_workers()
spawn_workers(MAX_WORKERS)
restored_pending = restore_pending_from_snapshot()
persist_queue_snapshot(reason="startup")
if restored_pending > 0:
    st_boot = load_state()
    if st_boot.get("owner_chat_id"):
        send_with_budget(int(st_boot["owner_chat_id"]),
                         f"♻️ Restored {restored_pending} pending tasks from last session.")

append_jsonl(DRIVE_ROOT / "logs" / "supervisor.jsonl", {
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "type": "launcher_start",
    "branch": load_state().get("current_branch"),
    "max_workers": MAX_WORKERS,
    "model_main": MODEL_MAIN,
    "model_code": MODEL_CODE,
    "budget_limit": TOTAL_BUDGET_LIMIT,
})

auto_resume_after_restart()

# ----------------------------
# 6.2) Watchdog thread
# ----------------------------
def reset_chat_agent():
    import supervisor.workers as _w
    _w._chat_agent = None

def _chat_watchdog_loop():
    soft_warned = False
    while True:
        time.sleep(30)
        try:
            agent = _get_chat_agent()
            if not agent._busy:
                soft_warned = False
                continue
            now = time.time()
            idle_sec = now - agent._last_progress_ts
            total_sec = now - agent._task_started_ts
            if idle_sec >= HARD_TIMEOUT_SEC:
                st = load_state()
                if st.get("owner_chat_id"):
                    send_with_budget(int(st["owner_chat_id"]),
                                     f"⚠️ Task stuck ({int(total_sec)}s). Restarting agent.")
                reset_chat_agent()
                soft_warned = False
            elif idle_sec >= SOFT_TIMEOUT_SEC and not soft_warned:
                soft_warned = True
                st = load_state()
                if st.get("owner_chat_id"):
                    send_with_budget(int(st["owner_chat_id"]),
                                     f"⏱️ Task running {int(total_sec)}s, last progress {int(idle_sec)}s ago.")
        except Exception:
            pass

threading.Thread(target=_chat_watchdog_loop, daemon=True).start()

# ----------------------------
# 6.3) Background consciousness
# ----------------------------
from ouroboros.consciousness import BackgroundConsciousness

def _get_owner_chat_id() -> Optional[int]:
    try:
        st = load_state()
        cid = st.get("owner_chat_id")
        return int(cid) if cid else None
    except Exception:
        return None

_consciousness = BackgroundConsciousness(
    drive_root=DRIVE_ROOT,
    repo_dir=REPO_DIR,
    event_queue=get_event_q(),
    owner_chat_id_fn=_get_owner_chat_id,
)

# ----------------------------
# 7) Startup message
# ----------------------------
print(f"""
╔══════════════════════════════════════════╗
║         OUROBOROS — LOCAL MODE           ║
╠══════════════════════════════════════════╣
║  Budget:  ${TOTAL_BUDGET_LIMIT:.2f}                          ║
║  Model:   {MODEL_MAIN[:38]}
║  Workers: {MAX_WORKERS}                                  ║
║  Data:    ./ouroboros_data/              ║
╚══════════════════════════════════════════╝

Open Telegram and message your bot to get started.
First message registers you as the owner.
Press Ctrl+C to stop.
""")

# ----------------------------
# 8) Main event loop
# ----------------------------
import types
_event_ctx = types.SimpleNamespace(
    DRIVE_ROOT=DRIVE_ROOT, REPO_DIR=REPO_DIR,
    BRANCH_DEV=BRANCH_DEV, BRANCH_STABLE=BRANCH_STABLE,
    TG=TG, WORKERS=WORKERS, PENDING=PENDING, RUNNING=RUNNING,
    MAX_WORKERS=MAX_WORKERS,
    send_with_budget=send_with_budget, load_state=load_state,
    save_state=save_state, update_budget_from_usage=update_budget_from_usage,
    append_jsonl=append_jsonl, enqueue_task=enqueue_task,
    cancel_task_by_id=cancel_task_by_id, queue_review_task=queue_review_task,
    persist_queue_snapshot=persist_queue_snapshot, safe_restart=safe_restart,
    kill_workers=kill_workers, spawn_workers=spawn_workers,
    sort_pending=sort_pending, consciousness=_consciousness,
)


def _safe_qsize(q):
    try:
        return int(q.qsize())
    except Exception:
        return -1


def _handle_supervisor_command(text: str, chat_id: int, tg_offset: int = 0):
    lowered = text.strip().lower()
    if lowered.startswith("/panic"):
        send_with_budget(chat_id, "🛑 PANIC: stopping everything.")
        kill_workers()
        raise SystemExit("PANIC")
    if lowered.startswith("/restart"):
        send_with_budget(chat_id, "♻️ Restarting.")
        ok, msg = safe_restart(reason="owner_restart", unsynced_policy="rescue_and_reset")
        if not ok:
            send_with_budget(chat_id, f"⚠️ Restart cancelled: {msg}")
            return True
        kill_workers()
        os.execv(sys.executable, [sys.executable, __file__])
    if lowered.startswith("/status"):
        status = status_text(WORKERS, PENDING, RUNNING, SOFT_TIMEOUT_SEC, HARD_TIMEOUT_SEC)
        send_with_budget(chat_id, status, force_budget=True)
        return "[Supervisor handled /status]\n"
    if lowered.startswith("/review"):
        queue_review_task(reason="owner:/review", force=True)
        return "[Supervisor handled /review — review queued]\n"
    if lowered.startswith("/evolve"):
        parts = lowered.split()
        action = parts[1] if len(parts) > 1 else "on"
        turn_on = action not in ("off", "stop", "0")
        st2 = load_state()
        st2["evolution_mode_enabled"] = bool(turn_on)
        save_state(st2)
        if not turn_on:
            PENDING[:] = [t for t in PENDING if str(t.get("type")) != "evolution"]
            sort_pending()
            persist_queue_snapshot(reason="evolve_off")
        state_str = "ON" if turn_on else "OFF"
        send_with_budget(chat_id, f"🧬 Evolution: {state_str}")
        return f"[Supervisor handled /evolve — {state_str}]\n"
    if lowered.startswith("/bg"):
        parts = lowered.split()
        action = parts[1] if len(parts) > 1 else "status"
        if action in ("start", "on", "1"):
            send_with_budget(chat_id, f"🧠 {_consciousness.start()}")
        elif action in ("stop", "off", "0"):
            send_with_budget(chat_id, f"🧠 {_consciousness.stop()}")
        else:
            bg_status = "running" if _consciousness.is_running else "stopped"
            send_with_budget(chat_id, f"🧠 Background consciousness: {bg_status}")
        return f"[Supervisor handled /bg {action}]\n"
    return ""


try:
    _consciousness.start()
    log.info("🧠 Background consciousness started")
except Exception as e:
    log.warning("consciousness start failed: %s", e)

offset = int(load_state().get("tg_offset") or 0)
_last_diag_heartbeat_ts = 0.0
_last_message_ts = time.time()
_ACTIVE_MODE_SEC = 300

while True:
    loop_started_ts = time.time()
    rotate_chat_log_if_needed(DRIVE_ROOT)
    ensure_workers_healthy()

    event_q = get_event_q()
    while True:
        try:
            evt = event_q.get_nowait()
        except _queue_mod.Empty:
            break
        dispatch_event(evt, _event_ctx)

    enforce_task_timeouts()
    enqueue_evolution_task_if_needed()
    assign_tasks()
    persist_queue_snapshot(reason="main_loop")

    _now = time.time()
    _active = (_now - _last_message_ts) < _ACTIVE_MODE_SEC
    _poll_timeout = 0 if _active else 10
    try:
        updates = TG.get_updates(offset=offset, timeout=_poll_timeout)
    except Exception as e:
        log.warning("Telegram poll error: %s", e)
        time.sleep(1.5)
        continue

    for upd in updates:
        offset = int(upd["update_id"]) + 1
        msg = upd.get("message") or upd.get("edited_message") or {}
        if not msg:
            continue

        chat_id = int(msg["chat"]["id"])
        from_user = msg.get("from") or {}
        user_id = int(from_user.get("id") or 0)
        text = str(msg.get("text") or "")
        caption = str(msg.get("caption") or "")
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        image_data = None
        if msg.get("photo"):
            best_photo = msg["photo"][-1]
            file_id = best_photo.get("file_id")
            if file_id:
                b64, mime = TG.download_file_base64(file_id)
                if b64:
                    image_data = (b64, mime, caption)

        st = load_state()
        if st.get("owner_id") is None:
            st["owner_id"] = user_id
            st["owner_chat_id"] = chat_id
            st["last_owner_message_at"] = now_iso
            save_state(st)
            log_chat("in", chat_id, user_id, text)
            send_with_budget(chat_id,
                "✅ Owner registered. Ouroboros online.\n\n"
                "I'm an autonomous AI agent focused on finding and executing revenue opportunities. "
                "I'll work independently and update you on progress.\n\n"
                "Commands: /status /evolve /bg /review /restart /panic"
            )
            _consciousness.inject_observation("Owner registered. Begin autonomous revenue research.")
            continue

        if user_id != int(st.get("owner_id")):
            continue

        log_chat("in", chat_id, user_id, text)
        st["last_owner_message_at"] = now_iso
        _last_message_ts = time.time()
        save_state(st)

        if text.strip().lower().startswith("/"):
            try:
                result = _handle_supervisor_command(text, chat_id, tg_offset=offset)
                if result is True:
                    continue
                elif result:
                    text = result + text
            except SystemExit:
                raise
            except Exception:
                log.warning("Supervisor command error", exc_info=True)

        if not text and not image_data:
            continue

        _consciousness.inject_observation(f"Owner message: {text[:100]}")
        agent = _get_chat_agent()

        if agent._busy:
            if image_data:
                send_with_budget(chat_id, "📎 Photo received, but busy. Resend when free.")
            elif text:
                agent.inject_message(text)
        else:
            _BATCH_WINDOW_SEC = 1.5
            _EARLY_EXIT_SEC = 0.15
            _batch_start = time.time()
            _batch_deadline = _batch_start + _BATCH_WINDOW_SEC
            _batched_texts = [text] if text else []
            _batched_image = image_data

            _batch_state = load_state()
            _batch_state_dirty = False
            while time.time() < _batch_deadline:
                time.sleep(0.1)
                try:
                    _extra_updates = TG.get_updates(offset=offset, timeout=0) or []
                except Exception:
                    _extra_updates = []
                if not _extra_updates and (time.time() - _batch_start) < _EARLY_EXIT_SEC:
                    break
                for _upd in _extra_updates:
                    offset = max(offset, int(_upd.get("update_id", offset - 1)) + 1)
                    _msg2 = _upd.get("message") or _upd.get("edited_message") or {}
                    _uid2 = (_msg2.get("from") or {}).get("id")
                    _cid2 = (_msg2.get("chat") or {}).get("id")
                    _txt2 = _msg2.get("text") or _msg2.get("caption") or ""
                    if _uid2 and _batch_state.get("owner_id") and _uid2 == int(_batch_state["owner_id"]):
                        log_chat("in", _cid2, _uid2, _txt2)
                        _batch_state["last_owner_message_at"] = now_iso
                        _batch_state_dirty = True
                        if _txt2.strip().lower().startswith("/"):
                            try:
                                _cmd_result = _handle_supervisor_command(_txt2, _cid2, tg_offset=offset)
                                if _cmd_result is True:
                                    continue
                                elif _cmd_result:
                                    _txt2 = _cmd_result + _txt2
                            except SystemExit:
                                raise
                            except Exception:
                                pass
                        if _txt2:
                            _batched_texts.append(_txt2)
                            _batch_deadline = max(_batch_deadline, time.time() + 0.3)

            if _batch_state_dirty:
                save_state(_batch_state)

            final_text = "\n\n".join(_batched_texts) if len(_batched_texts) > 1 else (_batched_texts[0] if _batched_texts else text)

            if agent._busy:
                if final_text:
                    agent.inject_message(final_text)
            else:
                _consciousness.pause()
                def _run_and_resume(cid, txt, img):
                    try:
                        handle_chat_direct(cid, txt, img)
                    finally:
                        _consciousness.resume()
                t = threading.Thread(target=_run_and_resume, args=(chat_id, final_text, _batched_image), daemon=True)
                try:
                    t.start()
                except Exception as te:
                    log.error("Failed to start chat thread: %s", te)
                    _consciousness.resume()

    st = load_state()
    st["tg_offset"] = offset
    save_state(st)

    loop_duration_sec = time.time() - loop_started_ts
    if DIAG_HEARTBEAT_SEC > 0 and (time.time() - _last_diag_heartbeat_ts) >= float(DIAG_HEARTBEAT_SEC):
        st = load_state()
        workers_alive = sum(1 for w in WORKERS.values() if w.proc.is_alive())
        append_jsonl(DRIVE_ROOT / "logs" / "supervisor.jsonl", {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "type": "heartbeat",
            "workers_alive": workers_alive,
            "pending": len(PENDING),
            "running": len(RUNNING),
            "spent_usd": st.get("spent_usd"),
        })
        _last_diag_heartbeat_ts = time.time()

    _loop_sleep = 0.1 if (_now - _last_message_ts) < _ACTIVE_MODE_SEC else 0.5
    time.sleep(_loop_sleep)
