"""
Notizen — a minimalistic Notion-style Kanban task board built with Streamlit.

Run with:
    streamlit run app.py
"""

import json
import uuid
from datetime import date
from pathlib import Path

import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

DATA_FILE = Path(__file__).parent / "tasks.json"
# Custom app logo (optional): looked up in project root, then assets/
LOGO_CANDIDATES = [
    Path(__file__).parent / "logo.png",
    Path(__file__).parent / "assets" / "logo.png",
]

STATUSES = ["Planned", "Doing", "Finished"]
PRIORITIES = ["Low", "Medium", "High"]

STATUS_META = {
    "Planned":  {"emoji": "🗂️", "color": "#8b8b93", "bg": "rgba(139,139,147,.12)"},
    "Doing":    {"emoji": "🔵", "color": "#5b9bd5", "bg": "rgba(91,155,213,.12)"},
    "Finished": {"emoji": "🟢", "color": "#4dab77", "bg": "rgba(77,171,119,.12)"},
}

PRIORITY_META = {
    "Low":    {"color": "#7a9e7e", "bg": "rgba(122,158,126,.15)"},
    "Medium": {"color": "#c7a34a", "bg": "rgba(199,163,74,.15)"},
    "High":   {"color": "#d0716f", "bg": "rgba(208,113,111,.15)"},
}

ICON_CHOICES = ["📝", "📔", "🚩", "📄", "🎨", "🚀", "🔧", "💡", "📣", "🧪", "📊", "🌱"]

# ──────────────────────────────────────────────────────────────────────────────
# Data layer (JSON persistence)
# ──────────────────────────────────────────────────────────────────────────────


def load_tasks() -> list[dict]:
    """Load tasks from disk; the board starts empty on first launch."""
    if not DATA_FILE.exists():
        save_tasks([])
        return []
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_tasks(tasks: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")


def get_tasks() -> list[dict]:
    if "tasks" not in st.session_state:
        st.session_state.tasks = load_tasks()
    return st.session_state.tasks


def persist() -> None:
    save_tasks(st.session_state.tasks)


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
    st.session_state.tasks = [t for t in get_tasks() if t["id"] != task_id]
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

html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }

/* Hide default Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1180px; }

/* ── App title ─────────────────────────────────────────── */
.nz-title {
    font-size: 2.1rem; font-weight: 700; letter-spacing: -.02em;
    color: #ececec; margin-bottom: .1rem;
    display: flex; align-items: center; gap: .55rem;
}
.nz-title .logo { display:inline-block; animation: nz-float 3s ease-in-out infinite; }
.nz-title img.logo {
    width: 44px; height: 44px; object-fit: cover;
    border-radius: 10px; border: 1px solid #2d2d33;
    box-shadow: 0 2px 8px rgba(0,0,0,.35);
}
.nz-sub { color: #8b8b93; font-size: .92rem; margin-bottom: 1.4rem; }

/* ── Animated emoji ────────────────────────────────────── */
@keyframes nz-float { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-4px) } }
@keyframes nz-pop   { 0% { transform: scale(1) } 50% { transform: scale(1.25) rotate(-8deg) } 100% { transform: scale(1) } }
.nz-emoji { display:inline-block; transition: transform .25s ease; }
.nz-card:hover .nz-emoji { animation: nz-pop .5s ease; }

/* ── Kanban column ─────────────────────────────────────── */
.nz-col-head {
    display:flex; align-items:center; gap:.5rem;
    padding: .35rem .7rem; border-radius: 8px;
    font-weight: 600; font-size: .86rem; width: fit-content;
    margin-bottom: .7rem;
}
.nz-col-count { color:#8b8b93; font-weight:500; margin-left:.15rem; }

/* ── Task card ─────────────────────────────────────────── */
.nz-card {
    background: #202024;
    border: 1px solid #2d2d33;
    border-radius: 12px;
    padding: .85rem .95rem .7rem;
    margin-bottom: .6rem;
    box-shadow: 0 1px 2px rgba(0,0,0,.25);
    transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
    cursor: grab;
}
.nz-card:hover {
    transform: translateY(-2px);
    border-color: #3d3d45;
    box-shadow: 0 6px 18px rgba(0,0,0,.35);
}
.nz-card-title {
    font-weight: 600; font-size: .95rem; color: #ececec;
    margin-bottom: .55rem; display:flex; gap:.45rem; align-items:center;
    line-height: 1.3;
}
.nz-badges { display:flex; flex-wrap:wrap; gap:.35rem; margin-bottom:.3rem; }
.nz-badge {
    font-size: .72rem; font-weight: 600;
    padding: .13rem .55rem; border-radius: 999px;
    letter-spacing: .01em;
}
.nz-meta { color:#8b8b93; font-size:.75rem; display:flex; gap:.8rem; margin-top:.25rem; }
.nz-progress-wrap { background:#2d2d33; border-radius:99px; height:5px; margin-top:.5rem; overflow:hidden; }
.nz-progress-bar { background:#4dab77; height:100%; border-radius:99px; transition: width .3s ease; }

/* ── Streamlit widget restyling ────────────────────────── */
/* Pill-style radio nav */
div[role="radiogroup"] { gap: .3rem !important; }
div[role="radiogroup"] label {
    background: #202024 !important;
    border: 1px solid #2d2d33 !important;
    border-radius: 999px !important;
    padding: .28rem .95rem !important;
    transition: all .15s ease;
}
div[role="radiogroup"] label:hover { border-color:#4a4a52 !important; background:#26262b !important; }
div[role="radiogroup"] label:has(input:checked) {
    background: #33333a !important; border-color:#55555e !important;
}
div[role="radiogroup"] label > div:first-child { display: none !important; }  /* hide radio dot */
div[role="radiogroup"] p { font-size: .87rem !important; font-weight: 500; }

/* Buttons */
.stButton > button, [data-testid="stPopoverButton"] {
    background: transparent; border: 1px solid #2d2d33;
    border-radius: 8px; color: #b9b9c0;
    font-size: .8rem; padding: .18rem .6rem;
    transition: all .15s ease;
}
.stButton > button:hover, [data-testid="stPopoverButton"]:hover {
    border-color: #55555e; color: #ececec; background: #26262b;
}
.stButton > button[kind="primary"] {
    background: #3b82f6; border-color: #3b82f6; color: white; font-weight: 600;
}
.stButton > button[kind="primary"]:hover { background:#2f6fd6; }

/* Inputs */
.stTextInput input, .stDateInput input, .stTextArea textarea {
    border-radius: 8px !important;
}

/* Expanders (checklist view) */
details[data-testid="stExpander"] {
    background: #202024; border: 1px solid #2d2d33; border-radius: 12px;
}

hr { border-color:#2d2d33 !important; }
</style>
"""


def badge(text: str, color: str, bg: str, icon: str = "") -> str:
    return (
        f'<span class="nz-badge" style="color:{color};background:{bg};">'
        f'{icon}{" " if icon else ""}{text}</span>'
    )


def card_html(task: dict) -> str:
    """Render a task card as HTML."""
    p = PRIORITY_META[task["priority"]]
    s = STATUS_META[task["status"]]
    badges = badge(task["priority"], p["color"], p["bg"])
    if task.get("tag"):
        badges += badge(task["tag"], "#a58fd0", "rgba(165,143,208,.15)", "💬")

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
        f'<div class="nz-card">'
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
def new_task_dialog():
    title = st.text_input("Title", placeholder="e.g. Ship dark mode")
    c1, c2 = st.columns(2)
    icon = c1.selectbox("Icon", ICON_CHOICES)
    priority = c2.selectbox("Priority", PRIORITIES, index=1)
    c3, c4 = st.columns(2)
    tag = c3.text_input("Tag", placeholder="e.g. Feature request")
    status = c4.selectbox("Status", STATUSES)
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


def filter_bar(show_status: bool = True) -> list[dict]:
    """Render Notion-style filter controls and return the filtered task list."""
    tasks = get_tasks()
    cols = st.columns([2.2, 1.2, 1.2, 1.2] if show_status else [2.6, 1.4, 1.4])
    search = cols[0].text_input("Search", placeholder="🔍 Search tasks…",
                                label_visibility="collapsed")
    f_priority = cols[1].selectbox("Priority", ["All priorities"] + PRIORITIES,
                                   label_visibility="collapsed")
    f_tag = cols[2].selectbox("Tag", ["All tags"] + all_tags(),
                              label_visibility="collapsed")
    f_status = "All statuses"
    if show_status:
        f_status = cols[3].selectbox("Status", ["All statuses"] + STATUSES,
                                     label_visibility="collapsed")

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
        st.markdown('<p style="color:#8b8b93;">No tasks match your filters. 🌙</p>',
                    unsafe_allow_html=True)
        return
    cols = st.columns(3)
    for i, task in enumerate(tasks):
        with cols[i % 3]:
            st.markdown(card_html(task), unsafe_allow_html=True)
            card_actions(task, "all")


def view_kanban():
    tasks = filter_bar(show_status=False)
    cols = st.columns(3, gap="medium")
    for col, status in zip(cols, STATUSES):
        meta = STATUS_META[status]
        bucket = [t for t in tasks if t["status"] == status]
        with col:
            st.markdown(
                f'<div class="nz-col-head" style="color:{meta["color"]};background:{meta["bg"]};">'
                f'{meta["emoji"]} {status}'
                f'<span class="nz-col-count">{len(bucket)}</span></div>',
                unsafe_allow_html=True,
            )
            for task in bucket:
                st.markdown(card_html(task), unsafe_allow_html=True)
                card_actions(task, f"kb_{status}")
            if st.button("＋ New task", key=f"new_{status}", use_container_width=True):
                new_task_dialog()


def view_checklist():
    tasks = [t for t in get_tasks() if t.get("checklist")]
    if not tasks:
        st.markdown('<p style="color:#8b8b93;">No tasks have checklists yet. '
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
    page_icon, logo_html = logo()
    st.set_page_config(page_title="Notizen", page_icon=page_icon, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)

    st.markdown(f'<div class="nz-title">{logo_html}Notizen</div>'
                '<div class="nz-sub">Stay organized with tasks, your way.</div>',
                unsafe_allow_html=True)

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
