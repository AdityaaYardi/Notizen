# ✅ Notizen

A minimalistic, Notion-style Kanban task board built with **Streamlit**. Dark mode by default, soft rounded cards, pill filters, animated emoji icons.

## Features

- **3 Kanban buckets**: Planned → Doing → Finished
- **3 views**: ⭐ All Tasks · 🧭 By Status (Kanban) · ✅ Checklist
- Add / edit / delete tasks, move them between columns, mark as finished
- Priority badges (Low / Medium / High), category tags, optional due dates
- Checklists inside tasks with progress bars (tasks auto-finish when all items are done)
- Filter by status, priority, tag, and search text
- Tasks persist in a local `tasks.json` file (board starts empty on first launch)
- Optional custom logo: drop a `logo.png` in the project root (or `assets/`)

## Run locally

Requires Python 3.10+.

```bash
git clone https://github.com/YOUR_USERNAME/notizen.git
cd notizen
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. A `tasks.json` file is created automatically on first launch.

## Project structure

```
notizen/
├── app.py                 # Full app: data layer, styling, views
├── requirements.txt
├── README.md
├── .streamlit/
│   └── config.toml        # Dark theme configuration
└── tasks.json             # Created automatically; stores your tasks
```

## Deploy to GitHub

```bash
cd notizen
git init
git add .
git commit -m "Initial commit: Notizen task board"
# Create an empty repo named 'notizen' on github.com first, then:
git remote add origin https://github.com/YOUR_USERNAME/notizen.git
git branch -M main
git push -u origin main
```

Tip: don't commit your personal `tasks.json` if you don't want your tasks public — add it to `.gitignore`.

## Hosting options (honest overview)

### Option 1: Streamlit Community Cloud (free, easiest)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **New app**, pick your repo, branch `main`, file `app.py`.
3. Deploy — you get a public `*.streamlit.app` URL in ~2 minutes.

**Realistic limitations:**
- Free apps **go to sleep after ~12 hours of inactivity**. The next visitor sees a "wake up" button and waits a few seconds. It is *not* guaranteed 24/7 uptime.
- The **filesystem is ephemeral**: `tasks.json` is reset whenever the app restarts or redeploys. Fine for demos; for real persistence connect an external store (e.g. a database, Google Sheets, or S3).

An uptime pinger (e.g. UptimeRobot hitting your URL every 5 minutes) can reduce sleeping, but Streamlit may still restart apps, and keeping a free app artificially awake is discouraged — don't rely on it.

### Option 2: Always-on paid hosting (Render / Railway / Fly.io / VPS)

For a truly always-on app with persistent disk:

- **Render / Railway**: connect the GitHub repo, set the start command to
  `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.
  Use a paid instance (free tiers also sleep) and attach a persistent volume for `tasks.json`.
- **Fly.io**: deploy with a Dockerfile + a mounted volume.
- **VPS** (Hetzner, DigitalOcean, etc.): run behind a reverse proxy and keep the process alive with `systemd`, e.g.:

  ```ini
  # /etc/systemd/system/notizen.service
  [Unit]
  Description=Notizen Streamlit app
  After=network.target

  [Service]
  WorkingDirectory=/opt/notizen
  ExecStart=/opt/notizen/.venv/bin/streamlit run app.py --server.port 8501
  Restart=always

  [Install]
  WantedBy=multi-user.target
  ```

**Rule of thumb:** free hosting = fine for demos and personal use with occasional wake-ups; paid hosting or a VPS = required for genuine 24/7 availability and durable data.

## Tech

Python 3.10+ · Streamlit · JSON file persistence · custom CSS (no other dependencies)
