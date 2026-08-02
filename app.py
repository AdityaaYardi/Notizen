"""
Notizen — a minimalistic Notion-style Kanban task board built with Streamlit.

Run with:
    streamlit run app.py
"""

import base64
import json
import uuid
from datetime import date
from pathlib import Path

import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent

# Custom app logo (optional): looked up in project root, then assets/
LOGO_CANDIDATES = [
    ROOT / "logo.png",
    ROOT / "assets" / "logo.png",
]

# ──────────────────────────────────────────────────────────────────────────────
# Profiles
# ──────────────────────────────────────────────────────────────────────────────
#
# The app serves two completely independent boards, "K" and "F", switched with
# the pill toggle next to the title. They share the same app and the same GitHub
# repo/branch, but each stores its tasks and rough work in its own files, so
# neither board ever sees the other's data.
#
# "K" keeps the original filenames so existing data carries over untouched.

PROFILES = ["K", "F"]
DEFAULT_PROFILE = "K"

PROFILE_FILES = {
    "K": {"tasks": "tasks.json",   "rough": "rough_work.txt"},
    "F": {"tasks": "tasks_f.json", "rough": "rough_work_f.txt"},
}


def profile() -> str:
    """The board currently being viewed — "K" or "F"."""
    return st.session_state.get("profile", DEFAULT_PROFILE)


def sync_profile_from_url() -> None:
    """Seed the board from ?board=K|F on first load, so each board is linkable.

    Only on first load: after that the switch owns the value (and writes it back
    to the URL), otherwise a stale query param would fight every toggle.
    """
    if st.session_state.get("_profile_synced"):
        return
    try:
        board = str(st.query_params.get("board", "")).strip().upper()
    except Exception:
        board = ""
    if board not in PROFILES:
        board = DEFAULT_PROFILE
    st.session_state["profile"] = board
    st.session_state["_profile_synced"] = True


def switch_board() -> None:
    """Flip to the other board — a plain rerun, so the page never reloads."""
    other = "F" if profile() == "K" else "K"
    st.session_state["profile"] = other
    try:                       # keep the URL shareable; harmless if unsupported
        st.query_params["board"] = other
    except Exception:
        pass


def _files() -> dict:
    return PROFILE_FILES[profile()]


def data_file() -> Path:
    return ROOT / _files()["tasks"]


def rough_file() -> Path:
    return ROOT / _files()["rough"]


def _sk(name: str) -> str:
    """Session-state key namespaced by profile, so K and F never collide."""
    return f"{name}_{profile()}"

STATUSES = ["Planned", "Doing", "Finished"]
PRIORITIES = ["Low", "Medium", "High"]

# Semantic status colours, aligned with the iOS dark system palette declared
# as CSS tokens in the stylesheet below (--nz-accent / --nz-green / etc.).
STATUS_META = {
    "Planned":  {"emoji": "🗂️", "color": "#9a9aa3", "bg": "rgba(154,154,163,.12)"},
    "Doing":    {"emoji": "🔵", "color": "#0a84ff", "bg": "rgba(10,132,255,.14)"},
    "Finished": {"emoji": "🟢", "color": "#30d158", "bg": "rgba(48,209,88,.14)"},
}

PRIORITY_META = {
    "Low":    {"color": "#30d158", "bg": "rgba(48,209,88,.14)"},
    "Medium": {"color": "#ff9f0a", "bg": "rgba(255,159,10,.14)"},
    "High":   {"color": "#ff453a", "bg": "rgba(255,69,58,.14)"},
}

ICON_CHOICES = ["📝", "📔", "🚩", "📄", "🎨", "🚀", "🔧", "💡", "📣", "🧪", "📊", "🌱"]

# ──────────────────────────────────────────────────────────────────────────────
# Data layer (GitHub-backed JSON persistence, with local-file fallback)
# ──────────────────────────────────────────────────────────────────────────────
#
# If a [github] section exists in Streamlit secrets, tasks.json is read from /
# written to a GitHub repo via the Contents API, so notes survive app restarts
# and are shared across devices. Data lives on its own branch (default: "data")
# so that save-commits do NOT trigger a Streamlit Cloud redeploy.
#
# Without secrets, the app falls back to the local tasks.json file.

API = "https://api.github.com"


def gh_conf() -> dict | None:
    """Return GitHub storage config from st.secrets, or None if not set up."""
    try:
        gh = st.secrets["github"]
        return {
            "token": gh["token"],
            "repo": gh.get("repo", "AdityaaYardi/Notizen"),
            "branch": gh.get("branch", "data"),
            # K honours a custom `path` in secrets; F always uses its own file.
            "path": (gh.get("path", "tasks.json")
                     if profile() == DEFAULT_PROFILE else _files()["tasks"]),
        }
    except (KeyError, FileNotFoundError):
        return None


def _gh_headers(conf: dict) -> dict:
    return {
        "Authorization": f"Bearer {conf['token']}",
        "Accept": "application/vnd.github+json",
    }


def _gh_file_url(conf: dict) -> str:
    return f"{API}/repos/{conf['repo']}/contents/{conf['path']}"


def _gh_ensure_branch(conf: dict) -> None:
    """Create the data branch off the default branch if it doesn't exist yet."""
    h = _gh_headers(conf)
    r = requests.get(f"{API}/repos/{conf['repo']}/git/ref/heads/{conf['branch']}",
                     headers=h, timeout=10)
    if r.status_code == 200:
        return
    default = requests.get(f"{API}/repos/{conf['repo']}", headers=h,
                           timeout=10).json()["default_branch"]
    sha = requests.get(f"{API}/repos/{conf['repo']}/git/ref/heads/{default}",
                       headers=h, timeout=10).json()["object"]["sha"]
    requests.post(f"{API}/repos/{conf['repo']}/git/refs", headers=h, timeout=10,
                  json={"ref": f"refs/heads/{conf['branch']}", "sha": sha})


def _gh_load(conf: dict) -> list[dict]:
    r = requests.get(_gh_file_url(conf), headers=_gh_headers(conf),
                     params={"ref": conf["branch"]}, timeout=10)
    if r.status_code == 404:               # branch or file doesn't exist yet
        _gh_ensure_branch(conf)
        st.session_state[_sk("gh_sha")] = None
        return []
    r.raise_for_status()
    payload = r.json()
    st.session_state[_sk("gh_sha")] = payload["sha"]
    return json.loads(base64.b64decode(payload["content"]).decode("utf-8"))


def _gh_save(conf: dict, tasks: list[dict]) -> None:
    body = {
        "message": "Update tasks",
        "content": base64.b64encode(
            json.dumps(tasks, indent=2, ensure_ascii=False).encode("utf-8")
        ).decode("ascii"),
        "branch": conf["branch"],
    }
    if st.session_state.get(_sk("gh_sha")):
        body["sha"] = st.session_state[_sk("gh_sha")]

    r = requests.put(_gh_file_url(conf), headers=_gh_headers(conf),
                     json=body, timeout=10)
    if r.status_code in (409, 422):
        # Stale sha (file was edited elsewhere) — refetch sha and retry once.
        g = requests.get(_gh_file_url(conf), headers=_gh_headers(conf),
                         params={"ref": conf["branch"]}, timeout=10)
        if g.status_code == 200:
            body["sha"] = g.json()["sha"]
        else:
            _gh_ensure_branch(conf)
            body.pop("sha", None)
        r = requests.put(_gh_file_url(conf), headers=_gh_headers(conf),
                         json=body, timeout=10)
    r.raise_for_status()
    st.session_state[_sk("gh_sha")] = r.json()["content"]["sha"]


def load_tasks() -> list[dict]:
    """Load tasks from GitHub if configured, otherwise from the local file."""
    conf = gh_conf()
    if conf:
        try:
            tasks = _gh_load(conf)
            st.session_state.gh_error = None
            return tasks
        except Exception as exc:
            # Stored in session state so main() can show a persistent banner —
            # a transient st.error() here is wiped by the immediate rerun.
            st.session_state.gh_error = f"loading failed — {exc}"
    if not data_file().exists():
        return []
    try:
        return json.loads(data_file().read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_tasks(tasks: list[dict]) -> None:
    """Save tasks to GitHub if configured; always keep the local copy too."""
    conf = gh_conf()
    if conf:
        try:
            _gh_save(conf, tasks)
            st.session_state.gh_error = None
        except Exception as exc:
            st.session_state.gh_error = f"saving failed — {exc}"
    try:
        data_file().write_text(json.dumps(tasks, indent=2, ensure_ascii=False),
                               encoding="utf-8")
    except OSError:
        pass  # read-only filesystem (some cloud hosts) — GitHub copy is primary


def _rough_gh_conf() -> dict | None:
    """Same GitHub repo/branch as tasks, but a separate file for rough notes."""
    base = gh_conf()
    if not base:
        return None
    conf = dict(base)
    conf["path"] = _files()["rough"]
    return conf


def _gh_load_text(conf: dict, sha_key: str) -> str:
    r = requests.get(_gh_file_url(conf), headers=_gh_headers(conf),
                     params={"ref": conf["branch"]}, timeout=10)
    if r.status_code == 404:
        _gh_ensure_branch(conf)
        st.session_state[sha_key] = None
        return ""
    r.raise_for_status()
    payload = r.json()
    st.session_state[sha_key] = payload["sha"]
    return base64.b64decode(payload["content"]).decode("utf-8")


def _gh_save_text(conf: dict, text: str, sha_key: str, message: str) -> None:
    body = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "branch": conf["branch"],
    }
    if st.session_state.get(sha_key):
        body["sha"] = st.session_state[sha_key]

    r = requests.put(_gh_file_url(conf), headers=_gh_headers(conf),
                     json=body, timeout=10)
    if r.status_code in (409, 422):
        g = requests.get(_gh_file_url(conf), headers=_gh_headers(conf),
                         params={"ref": conf["branch"]}, timeout=10)
        if g.status_code == 200:
            body["sha"] = g.json()["sha"]
        else:
            _gh_ensure_branch(conf)
            body.pop("sha", None)
        r = requests.put(_gh_file_url(conf), headers=_gh_headers(conf),
                         json=body, timeout=10)
    r.raise_for_status()
    st.session_state[sha_key] = r.json()["content"]["sha"]


def load_rough_work() -> str:
    """Load the Rough Work notepad from GitHub if configured, else local file."""
    conf = _rough_gh_conf()
    if conf:
        try:
            text = _gh_load_text(conf, _sk("gh_rough_sha"))
            st.session_state.gh_error = None
            return text
        except Exception as exc:
            st.session_state.gh_error = f"loading failed — {exc}"
    if not rough_file().exists():
        return ""
    try:
        return rough_file().read_text(encoding="utf-8")
    except OSError:
        return ""


def save_rough_work(text: str) -> None:
    """Save the Rough Work notepad to GitHub if configured; always keep a local copy."""
    conf = _rough_gh_conf()
    if conf:
        try:
            _gh_save_text(conf, text, _sk("gh_rough_sha"),
                          f"Update rough work ({profile()})")
            st.session_state.gh_error = None
        except Exception as exc:
            st.session_state.gh_error = f"saving failed — {exc}"
    try:
        rough_file().write_text(text, encoding="utf-8")
    except OSError:
        pass  # read-only filesystem (some cloud hosts) — GitHub copy is primary


def get_tasks() -> list[dict]:
    key = _sk("tasks")
    if key not in st.session_state:
        st.session_state[key] = load_tasks()
    return st.session_state[key]


def persist() -> None:
    save_tasks(get_tasks())


def find_task(task_id: str) -> dict | None:
    return next((t for t in get_tasks() if t["id"] == task_id), None)


def all_tags() -> list[str]:
    return sorted({t["tag"] for t in get_tasks() if t.get("tag")})


# ──────────────────────────────────────────────────────────────────────────────
# Mutations
# ──────────────────────────────────────────────────────────────────────────────


def add_task(title, icon, priority, tag, status, due, checklist_raw):
    checklist = [
        {"text": line.strip(), "done": False}
        for line in (checklist_raw or "").splitlines()
        if line.strip()
    ]
    get_tasks().append(
        {
            "id": str(uuid.uuid4()),
            "title": title.strip(),
            "icon": icon,
            "priority": priority,
            "tag": tag.strip(),
            "status": status,
            "due": due.isoformat() if due else None,
            "checklist": checklist,
        }
    )
    persist()


def delete_task(task_id: str):
    st.session_state[_sk("tasks")] = [t for t in get_tasks() if t["id"] != task_id]
    persist()


def move_task(task_id: str, direction: int):
    task = find_task(task_id)
    if task:
        idx = STATUSES.index(task["status"]) + direction
        if 0 <= idx < len(STATUSES):
            task["status"] = STATUSES[idx]
            persist()


def set_status(task_id: str, status: str):
    task = find_task(task_id)
    if task:
        task["status"] = status
        persist()


# ──────────────────────────────────────────────────────────────────────────────
# Styling
# ──────────────────────────────────────────────────────────────────────────────

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── Design tokens ─────────────────────────────────────── */
:root {
    /* Surfaces — layered, hairline translucent borders (not solid grey) */
    --nz-bg:        #0f0f11;
    --nz-surface:   #1a1a1e;
    --nz-surface-2: #212127;
    --nz-border:    rgba(255,255,255,.09);
    --nz-border-hi: rgba(255,255,255,.18);

    /* Text */
    --nz-text:   #f2f2f4;
    --nz-text-2: #9a9aa3;

    /* Brand mark (the K/F switch) + one interactive accent,
       then semantic status colours only (iOS dark system palette). */
    --nz-brand:  #ff7a18;
    --nz-brand-2:#ff8f3d;
    --nz-accent: #0a84ff;
    --nz-green:  #30d158;
    --nz-orange: #ff9f0a;
    --nz-red:    #ff453a;
    --nz-purple: #bf5af2;

    /* Radius — one scale */
    --r-sm: 10px;  --r-md: 14px;  --r-lg: 18px;  --r-pill: 999px;

    /* Motion */
    --ease: cubic-bezier(.32,.72,0,1);
    --dur:  220ms;
}

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text',
                 'Inter', 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
}

/* Hide default Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1720px; }
[data-testid="stAppViewContainer"] { background: var(--nz-bg); }

/* ── App title ─────────────────────────────────────────── */
.nz-title {
    font-size: clamp(1.9rem, 4vw, 2.4rem);
    font-weight: 700; letter-spacing: -.03em;
    color: var(--nz-text); margin-bottom: .1rem;
    display: flex; align-items: center; gap: .55rem;
    white-space: nowrap;
    animation: nz-rise .5s var(--ease) both .06s;
}
.nz-title .logo {
    display: inline-block;
    animation: nz-stamp .6s var(--ease) both;
    transition: transform .3s var(--ease);
}
.nz-title .logo:hover { transform: scale(1.08) rotate(-4deg); }
.nz-title img.logo {
    width: 44px; height: 44px; object-fit: cover;
    border-radius: var(--r-md); border: 1px solid var(--nz-border);
    box-shadow: 0 2px 8px rgba(0,0,0,.35);
}
.nz-sub { color: var(--nz-text-2); font-size: .92rem; margin-bottom: 1.4rem; }

/* ── Profile switch (K / F) ────────────────────────────── */
/* An iOS-style switch: solid orange track, white knob holding the ACTIVE
   letter in orange — so only one letter is ever visible.
   It's a Streamlit button (a click is a rerun, NOT a page reload), reshaped:
   the button becomes the track and its label <p> becomes the knob. Absolutely
   positioning the label keeps it out of flow, so nothing can stretch the
   track. The container key carries the state, which moves the knob. */
.st-key-board_switch_K [data-testid="stButton"] button,
.st-key-board_switch_F [data-testid="stButton"] button,
.st-key-board_switch_K button,
.st-key-board_switch_F button {
    position: relative !important;
    display: block !important;
    box-sizing: border-box !important;
    width: 46px !important;
    min-width: 46px !important;
    max-width: 46px !important;
    height: 24px !important;
    min-height: 24px !important;
    max-height: 24px !important;
    padding: 0 !important;
    margin: 0 !important;
    background: var(--nz-brand) !important;
    border: none !important;
    border-radius: var(--r-pill) !important;
    box-shadow: none !important;
    outline: none !important;
    /* Sit the track on the title's baseline rather than on the bottom of the
       title's line box (which hangs below the letters by the descender). */
    margin-bottom: 0px !important;
}
.st-key-board_switch_K button:hover,
.st-key-board_switch_F button:hover { background: var(--nz-brand-2) !important; }
/* The switch is already pill-shaped; don't let the global button press-scale
   fight the knob transition. */
.st-key-board_switch_K button:active,
.st-key-board_switch_F button:active { transform: none !important; }
/* Inner wrappers must not impose any box of their own. */
.st-key-board_switch_K button > div,
.st-key-board_switch_F button > div { display: contents !important; }
/* The label text is the knob. */
.st-key-board_switch_K button p,
.st-key-board_switch_F button p {
    position: absolute !important;
    top: 3px !important;
    left: 3px !important;
    width: 18px !important;
    height: 18px !important;
    margin: 0 !important;
    padding: 0 !important;
    background: #ffffff !important;
    border-radius: 50% !important;
    color: var(--nz-brand) !important;
    font-size: .62rem !important;
    font-weight: 700 !important;
    line-height: 18px !important;
    text-align: center !important;
    letter-spacing: 0 !important;
    transition: left .22s cubic-bezier(.4,0,.2,1);
}
.st-key-board_switch_F button p { left: 25px !important; }

/* Header row: shrink both columns to their content so the switch sits right
   next to the title instead of a fifth of the way across the page.
   Frosted glass so content scrolls under it (Apple HIG translucency). */
.st-key-nz_header {
    position: sticky; top: 0; z-index: 100;
    padding: .6rem 0 .7rem;
    background: rgba(15,15,17,.72);
    backdrop-filter: saturate(180%) blur(20px);
    -webkit-backdrop-filter: saturate(180%) blur(20px);
    border-bottom: 1px solid var(--nz-border);
}
.st-key-nz_header [data-testid="stHorizontalBlock"] {
    align-items: flex-end !important;
    flex-wrap: nowrap !important;
    gap: .6rem !important;
}
.st-key-nz_header [data-testid="stColumn"],
.st-key-nz_header [data-testid="column"] {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 0 !important;
}

/* ── Motion ────────────────────────────────────────────── */
/* Entrance animations, not decorative loops. The logo "stamps" in once, the
   heading rises under it, and cards stagger in. Nothing runs forever. */
@keyframes nz-stamp {
    0%   { opacity: 0; transform: scale(.6) rotate(-14deg); filter: blur(6px); }
    60%  { opacity: 1; transform: scale(1.08) rotate(4deg);  filter: blur(0); }
    100% { opacity: 1; transform: scale(1) rotate(0);        filter: blur(0); }
}
@keyframes nz-rise {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes nz-pop { 0% { transform: scale(1) } 50% { transform: scale(1.25) rotate(-8deg) } 100% { transform: scale(1) } }
.nz-emoji { display:inline-block; transition: transform .25s var(--ease); }
.nz-card:hover .nz-emoji { animation: nz-pop .5s var(--ease); }

/* Honour the OS "reduce motion" setting — required by Apple HIG and WCAG. */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: .01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: .01ms !important;
        scroll-behavior: auto !important;
    }
}

/* ── Kanban column ─────────────────────────────────────── */
.nz-col-head {
    display:flex; align-items:center; gap:.5rem;
    padding: .35rem .8rem; border-radius: var(--r-pill);
    font-weight: 600; font-size: .86rem; width: fit-content;
    margin-bottom: .7rem;
}
.nz-col-count { color:var(--nz-text-2); font-weight:500; margin-left:.15rem; }

/* Rough Work heading — plain centered text, no pill/highlight background */
.nz-roughwork-head {
    text-align: center;
    font-weight: 600;
    font-size: .95rem;
    color: var(--nz-text-2);
    margin-bottom: .7rem;
}

/* ── Task card ─────────────────────────────────────────── */
.nz-card {
    background: var(--nz-surface);
    border: 1px solid var(--nz-border);
    border-radius: var(--r-lg);
    padding: .9rem 1rem .75rem;
    margin-bottom: .6rem;
    box-shadow: 0 1px 2px rgba(0,0,0,.25);
    /* Cards aren't draggable — don't promise a grab handle. */
    cursor: default;
    animation: nz-rise .35s var(--ease) both;
    transition: transform var(--dur) var(--ease),
                box-shadow var(--dur) var(--ease),
                border-color var(--dur) var(--ease);
}
.nz-card:hover {
    transform: translateY(-2px);
    border-color: var(--nz-border-hi);
    box-shadow: 0 6px 18px rgba(0,0,0,.35);
}
.nz-card-title {
    font-weight: 600; font-size: .95rem; color: var(--nz-text);
    letter-spacing: -.01em;
    margin-bottom: .55rem; display:flex; gap:.45rem; align-items:center;
    line-height: 1.3;
}
.nz-badges { display:flex; flex-wrap:wrap; gap:.35rem; margin-bottom:.3rem; }
.nz-badge {
    font-size: .72rem; font-weight: 600;
    padding: .13rem .55rem; border-radius: var(--r-pill);
    letter-spacing: .01em;
}
.nz-meta { color:var(--nz-text-2); font-size:.75rem; display:flex; gap:.8rem; margin-top:.25rem; }
.nz-progress-wrap { background:rgba(255,255,255,.12); border-radius:var(--r-pill); height:5px; margin-top:.5rem; overflow:hidden; }
.nz-progress-bar { background:var(--nz-green); height:100%; border-radius:var(--r-pill); transition: width .3s var(--ease); }

/* ── Streamlit widget restyling ────────────────────────── */
/* Pill-style radio nav */
div[role="radiogroup"] { gap: .3rem !important; }
div[role="radiogroup"] label {
    background: rgba(255,255,255,.06) !important;
    border: 1px solid var(--nz-border) !important;
    border-radius: var(--r-pill) !important;
    padding: .4rem 1.05rem !important;
    min-height: 38px !important;
    display: flex !important; align-items: center !important;
    cursor: pointer !important;
    transition: background var(--dur) var(--ease),
                border-color var(--dur) var(--ease),
                transform 120ms var(--ease);
}
div[role="radiogroup"] label:hover {
    border-color: var(--nz-border-hi) !important;
    background: rgba(255,255,255,.10) !important;
}
div[role="radiogroup"] label:active { transform: scale(.96); }
div[role="radiogroup"] label:has(input:checked) {
    background: rgba(255,255,255,.16) !important;
    border-color: var(--nz-border-hi) !important;
}
div[role="radiogroup"] label > div:first-child { display: none !important; }  /* hide radio dot */
div[role="radiogroup"] p { font-size: .87rem !important; font-weight: 500; }

/* Buttons — pill-shaped, 38px min height (touch target), iOS press-scale */
.stButton > button, [data-testid="stPopoverButton"] {
    background: rgba(255,255,255,.06);
    border: 1px solid var(--nz-border);
    border-radius: var(--r-pill);
    color: var(--nz-text-2);
    font-size: .84rem;
    font-weight: 590;
    min-height: 38px;
    padding: .5rem 1.05rem;
    cursor: pointer;
    transition: background var(--dur) var(--ease),
                border-color var(--dur) var(--ease),
                color var(--dur) var(--ease),
                transform 120ms var(--ease);
}
.stButton > button:hover, [data-testid="stPopoverButton"]:hover {
    border-color: var(--nz-border-hi); color: var(--nz-text);
    background: rgba(255,255,255,.10);
}
.stButton > button:active, [data-testid="stPopoverButton"]:active {
    transform: scale(.96);
}
.stButton > button[kind="primary"] {
    background: var(--nz-accent); border-color: transparent;
    color: #fff; font-weight: 600;
    box-shadow: 0 4px 14px rgba(10,132,255,.30);
}
.stButton > button[kind="primary"]:hover { background:#0071e3; }
.stButton > button:disabled, .stButton > button:disabled:hover {
    opacity: .38; cursor: not-allowed; transform: none;
    background: rgba(255,255,255,.04); border-color: var(--nz-border);
}

/* Inputs */
.stTextInput input, .stDateInput input, .stTextArea textarea,
[data-baseweb="select"] > div {
    border-radius: var(--r-md) !important;
}
.stTextInput input, .stDateInput input { min-height: 38px !important; }

/* ── Focus rings ───────────────────────────────────────── */
/* :focus-visible is the keyboard-only signal — it must always be visible.
   Only the mouse-click :focus ring is suppressed elsewhere in this sheet. */
.stButton > button:focus-visible,
[data-testid="stPopoverButton"]:focus-visible,
textarea:focus-visible,
input:focus-visible,
[data-baseweb="select"]:focus-visible,
div[role="radiogroup"] label:has(input:focus-visible),
summary:focus-visible {
    outline: 2px solid var(--nz-accent) !important;
    outline-offset: 2px !important;
}

/* Hide the floating "Press Enter to apply" hint — it overlaps typed text
   in every text input / textarea (dialogs, search, checklist items). */
[data-testid="InputInstructions"] { display: none !important; }

/* Expanders (checklist view) */
details[data-testid="stExpander"] {
    background: var(--nz-surface); border: 1px solid var(--nz-border);
    border-radius: var(--r-lg);
}

/* ── Rough Work notepad — ruled paper look ─────────────── */
/* Target the textarea directly by its accessible name (stable regardless of
   Streamlit's internal DOM/class-naming, unlike the container-key selectors
   below) — this is what actually paints the ruled-paper look and font. */
textarea[aria-label="Rough work"] {
    background-color: var(--nz-surface) !important;
    background-image: repeating-linear-gradient(
        to bottom, transparent, transparent 27px, rgba(255,255,255,.12) 28px
    ) !important;
    background-attachment: local !important;
    line-height: 28px !important;
    padding-top: 6px !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    color: var(--nz-text) !important;
    border: 1px solid var(--nz-border) !important;
    border-radius: var(--r-lg) !important;
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text',
                 'Inter', 'Segoe UI', sans-serif !important;
    font-size: 1rem !important;
    font-weight: 400 !important;
    text-align: left !important;
    resize: vertical;
    outline: none !important;
    box-shadow: none !important;
}
textarea[aria-label="Rough work"]::placeholder {
    color: #6b6b74;
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text',
                 'Inter', 'Segoe UI', sans-serif !important;
}

/* Kill the blue theme-accent focus ring — Streamlit/BaseWeb can paint it on
   the textarea itself OR on a parent wrapper div, so cover both.
   NOTE: :focus-visible is deliberately NOT suppressed here — it is the only
   cue a keyboard user gets. It is re-asserted in the focus-rings block above. */
textarea[aria-label="Rough work"]:focus,
textarea[aria-label="Rough work"]:focus-within {
    border-color: var(--nz-border-hi) !important;
    box-shadow: none !important;
}
div:has(> textarea[aria-label="Rough work"]),
div:has(textarea[aria-label="Rough work"]) {
    outline: none !important;
    box-shadow: none !important;
    border-color: var(--nz-border) !important;
}
div:has(> textarea[aria-label="Rough work"]:focus),
div:has(textarea[aria-label="Rough work"]:focus) {
    border-color: var(--nz-border-hi) !important;
    outline: none !important;
    box-shadow: none !important;
}

/* Belt-and-braces: also cover via the container(key=...) class, in case the
   ring lands somewhere the :has() rules above don't reach. Scoped to the
   wrapper divs only — the textarea keeps its keyboard focus ring. */
.st-key-roughwork_box,
.st-key-roughwork_box div,
.st-key-roughwork_box div:focus,
.st-key-roughwork_box div:focus-within {
    outline: none !important;
    box-shadow: none !important;
}
.st-key-roughwork_box textarea:focus-visible {
    outline: 2px solid var(--nz-accent) !important;
    outline-offset: 2px !important;
}

hr { border-color: var(--nz-border) !important; }
</style>
"""


def badge(text: str, color: str, bg: str, icon: str = "") -> str:
    return (
        f'<span class="nz-badge" style="color:{color};background:{bg};">'
        f'{icon}{" " if icon else ""}{text}</span>'
    )


def card_html(task: dict, i: int = 0) -> str:
    """Render a task card as HTML.

    `i` is the card's position in its column, used to stagger the entrance
    animation (35ms apart, capped so long columns don't crawl in).
    """
    p = PRIORITY_META[task["priority"]]
    s = STATUS_META[task["status"]]
    badges = badge(task["priority"], p["color"], p["bg"])
    if task.get("tag"):
        badges += badge(task["tag"], "var(--nz-purple)", "rgba(191,90,242,.14)", "💬")

    meta_bits = [f'{s["emoji"]} {task["status"]}']
    if task.get("due"):
        try:
            d = date.fromisoformat(task["due"])
            overdue = d < date.today() and task["status"] != "Finished"
            meta_bits.append(("⚠️ " if overdue else "📅 ") + d.strftime("%b %d"))
        except ValueError:
            pass

    checklist = task.get("checklist") or []
    progress_html = ""
    if checklist:
        done = sum(1 for c in checklist if c["done"])
        pct = int(done / len(checklist) * 100)
        meta_bits.append(f"☑️ {done}/{len(checklist)}")
        progress_html = (
            f'<div class="nz-progress-wrap">'
            f'<div class="nz-progress-bar" style="width:{pct}%"></div></div>'
        )

    meta = "".join(f"<span>{m}</span>" for m in meta_bits)
    return (
        f'<div class="nz-card" style="animation-delay:{min(i, 12) * 35}ms">'
        f'<div class="nz-card-title"><span class="nz-emoji">{task["icon"]}</span>{task["title"]}</div>'
        f'<div class="nz-badges">{badges}</div>'
        f'<div class="nz-meta">{meta}</div>'
        f"{progress_html}"
        f"</div>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Dialogs
# ──────────────────────────────────────────────────────────────────────────────


@st.dialog("✨ New task")
def new_task_dialog(default_status: str = STATUSES[0]):
    title = st.text_input("Title", placeholder="e.g. Ship dark mode")
    c1, c2 = st.columns(2)
    icon = c1.selectbox("Icon", ICON_CHOICES)
    priority = c2.selectbox("Priority", PRIORITIES, index=1)
    c3, c4 = st.columns(2)
    tag = c3.text_input("Tag", placeholder="e.g. Feature request")
    status = c4.selectbox("Status", STATUSES, index=STATUSES.index(default_status))
    use_due = st.checkbox("Set due date")
    due = st.date_input("Due date") if use_due else None
    checklist_raw = st.text_area("Checklist (one item per line)",
                                 placeholder="First step\nSecond step")
    if st.button("Add task", type="primary", use_container_width=True):
        if title.strip():
            add_task(title, icon, priority, tag, status, due, checklist_raw)
            st.rerun()
        else:
            st.warning("Please enter a title.")


@st.dialog("✏️ Edit task")
def edit_task_dialog(task_id: str):
    task = find_task(task_id)
    if not task:
        st.error("Task not found.")
        return

    task["title"] = st.text_input("Title", value=task["title"])
    c1, c2 = st.columns(2)
    task["icon"] = c1.selectbox(
        "Icon", ICON_CHOICES,
        index=ICON_CHOICES.index(task["icon"]) if task["icon"] in ICON_CHOICES else 0,
    )
    task["priority"] = c2.selectbox("Priority", PRIORITIES,
                                    index=PRIORITIES.index(task["priority"]))
    c3, c4 = st.columns(2)
    task["tag"] = c3.text_input("Tag", value=task.get("tag") or "")
    task["status"] = c4.selectbox("Status", STATUSES, index=STATUSES.index(task["status"]))

    current_due = date.fromisoformat(task["due"]) if task.get("due") else None
    use_due = st.checkbox("Set due date", value=current_due is not None)
    if use_due:
        task["due"] = st.date_input("Due date", value=current_due or date.today()).isoformat()
    else:
        task["due"] = None

    st.markdown("**Checklist**")
    checklist = task.setdefault("checklist", [])
    remove_idx = None
    for i, item in enumerate(checklist):
        cc1, cc2, cc3 = st.columns([0.08, 0.8, 0.12])
        item["done"] = cc1.checkbox("done", value=item["done"], key=f"edit_ck_{task_id}_{i}",
                                    label_visibility="collapsed")
        item["text"] = cc2.text_input("item", value=item["text"], key=f"edit_ci_{task_id}_{i}",
                                      label_visibility="collapsed")
        if cc3.button("✕", key=f"edit_cd_{task_id}_{i}"):
            remove_idx = i
    if remove_idx is not None:
        checklist.pop(remove_idx)
        persist()
        st.rerun()

    new_item = st.text_input("Add checklist item", placeholder="Type and press Enter…",
                             key=f"edit_new_{task_id}")
    if new_item.strip():
        checklist.append({"text": new_item.strip(), "done": False})
        persist()
        st.rerun()

    b1, b2 = st.columns(2)
    if b1.button("💾 Save", type="primary", use_container_width=True):
        persist()
        st.rerun()
    if b2.button("🗑 Delete task", use_container_width=True):
        delete_task(task_id)
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Card actions row
# ──────────────────────────────────────────────────────────────────────────────


def card_actions(task: dict, key_prefix: str):
    """Small action row rendered under each card: move / edit / finish / delete."""
    idx = STATUSES.index(task["status"])
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("◀", key=f"{key_prefix}_l_{task['id']}", help="Move left",
                 disabled=idx == 0, use_container_width=True):
        move_task(task["id"], -1)
        st.rerun()
    if c2.button("▶", key=f"{key_prefix}_r_{task['id']}", help="Move right",
                 disabled=idx == len(STATUSES) - 1, use_container_width=True):
        move_task(task["id"], +1)
        st.rerun()
    if c3.button("✏️", key=f"{key_prefix}_e_{task['id']}", help="Edit",
                 use_container_width=True):
        edit_task_dialog(task["id"])
    if task["status"] != "Finished":
        if c4.button("✅", key=f"{key_prefix}_d_{task['id']}", help="Mark finished",
                     use_container_width=True):
            set_status(task["id"], "Finished")
            st.rerun()
    else:
        if c4.button("🗑", key=f"{key_prefix}_x_{task['id']}", help="Delete",
                     use_container_width=True):
            delete_task(task["id"])
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Filters
# ──────────────────────────────────────────────────────────────────────────────


def filter_bar(show_status: bool = True, show_tag: bool = True) -> list[dict]:
    """Render Notion-style filter controls and return the filtered task list."""
    tasks = get_tasks()

    ratios = [2.2, 1.2]
    if show_tag:
        ratios.append(1.2)
    if show_status:
        ratios.append(1.2)
    cols = st.columns(ratios)

    i = 0
    search = cols[i].text_input("Search", placeholder="🔍 Search tasks…",
                                label_visibility="collapsed"); i += 1
    f_priority = cols[i].selectbox("Priority", ["All priorities"] + PRIORITIES,
                                   label_visibility="collapsed"); i += 1
    f_tag = "All tags"
    if show_tag:
        f_tag = cols[i].selectbox("Tag", ["All tags"] + all_tags(),
                                  label_visibility="collapsed"); i += 1
    f_status = "All statuses"
    if show_status:
        f_status = cols[i].selectbox("Status", ["All statuses"] + STATUSES,
                                     label_visibility="collapsed"); i += 1

    out = tasks
    if search:
        out = [t for t in out if search.lower() in t["title"].lower()]
    if f_priority != "All priorities":
        out = [t for t in out if t["priority"] == f_priority]
    if f_tag != "All tags":
        out = [t for t in out if t.get("tag") == f_tag]
    if f_status != "All statuses":
        out = [t for t in out if t["status"] == f_status]
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────────────────────────────────────


def view_all_tasks():
    tasks = filter_bar(show_status=True)
    if not tasks:
        st.markdown('<p style="color:var(--nz-text-2);">No tasks match your filters. 🌙</p>',
                    unsafe_allow_html=True)
        return
    cols = st.columns(3)
    for i, task in enumerate(tasks):
        with cols[i % 3]:
            st.markdown(card_html(task, i), unsafe_allow_html=True)
            card_actions(task, "all")


def render_rough_work_column():
    """Freeform scratchpad column — plain lined notes, not tied to any task."""
    st.markdown('<div class="nz-roughwork-head">🗒️ Rough Work</div>',
                unsafe_allow_html=True)
    key = _sk("rough_work_input")
    if key not in st.session_state:
        st.session_state[key] = load_rough_work()

    def _on_change():
        save_rough_work(st.session_state[key])

    with st.container(key="roughwork_box"):
        st.text_area(
            "Rough work",
            height=520,
            label_visibility="collapsed",
            key=key,
            placeholder="Jot something down…",
            on_change=_on_change,
        )


def view_kanban():
    tasks = filter_bar(show_status=False, show_tag=False)
    cols = st.columns([1, 1, 1, 2.8], gap="medium")
    for col, status in zip(cols[:3], STATUSES):
        meta = STATUS_META[status]
        bucket = [t for t in tasks if t["status"] == status]
        with col:
            st.markdown(
                f'<div class="nz-col-head" style="color:{meta["color"]};background:{meta["bg"]};">'
                f'{meta["emoji"]} {status}'
                f'<span class="nz-col-count">{len(bucket)}</span></div>',
                unsafe_allow_html=True,
            )
            for i, task in enumerate(bucket):
                st.markdown(card_html(task, i), unsafe_allow_html=True)
                card_actions(task, f"kb_{status}")
            if st.button("＋ New task", key=f"new_{status}", use_container_width=True):
                new_task_dialog(default_status=status)
    with cols[3]:
        render_rough_work_column()


def view_checklist():
    tasks = [t for t in get_tasks() if t.get("checklist")]
    if not tasks:
        st.markdown('<p style="color:var(--nz-text-2);">No tasks have checklists yet. '
                    'Add checklist items when creating or editing a task. ✍️</p>',
                    unsafe_allow_html=True)
        return
    for task in tasks:
        done = sum(1 for c in task["checklist"] if c["done"])
        total = len(task["checklist"])
        with st.expander(f'{task["icon"]} {task["title"]}  ·  {done}/{total} done',
                         expanded=True):
            changed = False
            for i, item in enumerate(task["checklist"]):
                new_val = st.checkbox(item["text"], value=item["done"],
                                      key=f'cl_{task["id"]}_{i}')
                if new_val != item["done"]:
                    item["done"] = new_val
                    changed = True
            if changed:
                # Auto-finish task when every checklist item is complete
                if all(c["done"] for c in task["checklist"]) and task["status"] != "Finished":
                    task["status"] = "Finished"
                    st.toast(f'🎉 "{task["title"]}" moved to Finished!')
                persist()
                st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def logo() -> tuple[str, str]:
    """Return (page_icon, title_logo_html). Uses logo.png if present,
    otherwise falls back to the ✅ emoji."""
    for path in LOGO_CANDIDATES:
        if path.exists():
            import base64
            b64 = base64.b64encode(path.read_bytes()).decode()
            return str(path), f'<img class="logo" src="data:image/png;base64,{b64}">'
    return "✅", '<span class="logo">✅</span>'


def main():
    sync_profile_from_url()
    page_icon, logo_html = logo()
    st.set_page_config(page_title=f"Notizen · {profile()}", page_icon=page_icon,
                       layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)

    here = profile()
    other = "F" if here == "K" else "K"
    with st.container(key="nz_header"):
        title_col, switch_col = st.columns([0.16, 0.84], gap="small",
                                           vertical_alignment="bottom")
        with title_col:
            st.markdown(f'<div class="nz-title">{logo_html}Notizen</div>',
                        unsafe_allow_html=True)
        with switch_col:
            with st.container(key=f"board_switch_{here}"):
                st.button(here, key="board_switch_btn", on_click=switch_board,
                          help=f"Switch to {other}'s board")

    sync_note = (
        '<span style="color:var(--nz-green);">☁️ Synced to GitHub</span>'
        if gh_conf() else
        '<span style="color:var(--nz-orange);">⚠️ Local only — notes are lost on restart '
        '(set up GitHub sync, see README)</span>'
    )
    st.markdown(
        f'<div class="nz-sub">Stay organized with tasks, your way. · '
        f'<span style="color:var(--nz-brand);font-weight:600;">{profile()}\'s board</span> '
        f'· {sync_note}</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("gh_error"):
        st.error(
            f"⚠️ GitHub sync {st.session_state.gh_error}\n\n"
            "Notes are NOT being persisted. Common fixes: check the token has "
            "no extra spaces, was granted *Contents: Read and write* on the "
            "Notizen repo, and that `repo` in secrets matches exactly. "
            "401 = bad token · 403 = missing permission · 404 = wrong repo name."
        )

    nav_col, btn_col = st.columns([5, 1])
    with nav_col:
        view = st.radio(
            "Navigation",
            ["⭐ All Tasks", "🧭 By Status", "✅ Checklist"],
            index=1,
            horizontal=True,
            label_visibility="collapsed",
        )
    with btn_col:
        if st.button("＋ New", type="primary", use_container_width=True):
            new_task_dialog()

    st.markdown("<hr style='margin:.4rem 0 1.1rem;'>", unsafe_allow_html=True)

    if view == "⭐ All Tasks":
        view_all_tasks()
    elif view == "🧭 By Status":
        view_kanban()
    else:
        view_checklist()


if __name__ == "__main__":
    main()
