# Kraut Corner

A fan website for the YouTube channel **Kraut_the_Parrot** (geopolitics and history video essays), with a working sign-up form backed by a SQLite database.

Everything is in this one folder: frontend, backend and data. The only requirement is **Python 3.8 or newer**. There is nothing to `pip install` and no build step.

---

## Quick start

| System | Command |
|---|---|
| Windows | double-click `start.bat` |
| Mac / Linux | `./start.sh` (or `python3 server.py`) |

Then open **http://localhost:8000**. The terminal prints the site address and your private admin link. Stop the server with `Ctrl+C`.

---

## Project structure

```
kraut-corner/
├── server.py          Backend: serves the site and handles the sign-up API
├── public/
│   └── index.html     Frontend: the whole site (HTML + CSS + JS in one file)
├── data/              Created/used at runtime (kept in the zip as an empty folder)
│   ├── signups.db         SQLite database
│   ├── signups.csv        Spreadsheet copy, rewritten after every sign-up
│   ├── backups/           Database copy made on every server start (newest 20 kept)
│   └── admin_token.txt    Admin key (auto-created on first run)
├── start.bat          Windows launcher
├── start.sh           Mac/Linux launcher
└── README.md
```

---

## Frontend (`public/index.html`)

A single-page site with three pages and hash-based routing (no framework, no build tools).

| Route | Page | What it has |
|---|---|---|
| `#/` | Home | Hero with countryball characters, three feature cards about the channel, call-to-action band |
| `#/lab` | The Lab | Two-question "culture or institutions?" quiz with instant feedback, explanations and a score |
| `#/join` | Join | Sign-up form: name, email, reason (digest / suggest a topic / share a favourite video), optional message |

**The form**
- Validates name and email in the browser, with inline error messages and focus moved to the first error.
- Includes a hidden honeypot field (`website`). If a bot fills it in, the submission is silently dropped.
- Sends `POST /api/signup` with JSON `{name, email, kind, message}`, shows a "Sending…" state, then a success or error message.
- The endpoint is set by `FORM_ENDPOINT` near the top of the script (currently `/api/signup`, same origin as the server). The file still contains a fallback to the claude.ai built-in database that only runs if `FORM_ENDPOINT` is empty; it is unused here.

**Design**
- Style: bold and playful. Bright blue, sunny yellow and coral on pale blue, thick navy outlines, hard offset shadows. The countryballs are pure CSS (round shapes with eyes and invented flags, not real flags).
- Fonts: Bagel Fat One (headings) and Nunito (body), loaded from Google Fonts, so the first load needs internet. System fonts are the fallback.
- Colours are CSS variables on `:root`. A dark theme follows the visitor's system setting.
- Responsive layout, a sticky header that respects phone safe areas, visible keyboard focus outlines, `aria-live` regions for the quiz and form status, and the entrance animation is turned off for visitors who prefer reduced motion.

**Editing content**
- Page text lives in the `pages` object and the `card(...)` calls in the script.
- Quiz questions are the `QS` array (`q` question, `o` options, `a` index of the correct option, `e` explanation).
- Colours and sizes are in the `<style>` block at the top.

---

## Backend (`server.py`)

A small Python server using only the standard library (`http.server`, `sqlite3`).

**Endpoints**

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | none | The website |
| GET | `/healthz` | none | Health check (`{"ok": true}`) |
| POST | `/api/signup` | none | Save a sign-up |
| GET | `/admin?token=…` | token | HTML table of all sign-ups with a CSV link |
| GET | `/api/signups` | token | All sign-ups as JSON |
| GET | `/api/signups.csv` | token | Download the CSV |

The token is read from `Authorization: Bearer <token>` or a `?token=` query parameter.

**Sign-up rules**
- Name: required, trimmed, max 100 characters.
- Email: must look like a valid address, lowercased, max 254 characters.
- Kind: must be one of the three options in the form.
- Message: optional, max 500 characters.
- Request body is limited to 4 KB.
- Rate limit: 8 requests per minute per IP address.
- Signing up again with the same email **updates** the earlier entry rather than adding a duplicate.
- Responses: `201` saved, `400` malformed request, `422` invalid fields, `429` too many requests, `500` could not save.

**Reliability**
- SQLite runs in WAL mode with full synchronous writes, so a crash or power cut does not corrupt the data.
- Writes are serialized with a lock and a busy timeout.
- `signups.csv` is written to a temporary file and then swapped in atomically, so it is never half-written.
- A dated copy of the database goes into `data/backups/` every time the server starts.
- All values are inserted with parameterized queries, and the admin page escapes everything it prints.

**Configuration (optional environment variables)**

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8000` | Port to listen on (hosts like Render set this for you) |
| `DATA_DIR` | `./data` | Where the database, CSV, backups and token are stored |
| `ADMIN_TOKEN` | auto-generated | Admin key. If unset, one is created in `data/admin_token.txt` |

---

## Your data

- View it at `http://localhost:8000/admin?token=<contents of data/admin_token.txt>`.
- Open `data/signups.csv` in Excel or Google Sheets.
- Query it directly: `sqlite3 data/signups.db "select * from signups;"`.
- Move or share it by copying the whole `data/` folder. Start fresh by deleting its contents.

---

## Deploying on Render

1. Push this folder to a GitHub repo.
2. In Render, choose **New → Web Service** and select the repo.
3. Runtime **Python 3**, Build Command `echo ok`, Start Command `python server.py`.
4. Add the environment variable `ADMIN_TOKEN` set to a long random string.
5. Deploy, open the URL, submit a test sign-up, and check it at `/admin?token=YOUR_TOKEN`.

**Important:** Render's free tier has no persistent disk. Data in `data/` is lost on redeploy, restart or after the service sleeps from inactivity. To keep sign-ups, use a paid instance, add a Disk mounted at `/var/data`, and set `DATA_DIR=/var/data`. Otherwise, download the CSV from the admin page before anything restarts.

Any other host that runs `python server.py` and offers a persistent disk (Railway, Fly.io, a VPS) works the same way.

---

## Troubleshooting

- **`python` not found (Windows):** install Python from python.org and tick "Add Python to PATH". `start.bat` tries `py` first, then `python`.
- **Port already in use:** run with another port, for example `PORT=8080 python3 server.py` (Windows: `set PORT=8080` first).
- **Form says "Oops, that didn't go through":** the browser could not reach `/api/signup`. Make sure you opened the site through the server's address, not by double-clicking `index.html`.
- **401 on the admin page:** the token is wrong. Use the one in `data/admin_token.txt`, or the value of `ADMIN_TOKEN` if you set it.
- **Sign-ups vanished on Render:** the service restarted without a persistent disk (see the Render section).

---

*This is a fan project and is not affiliated with Kraut or his team.*
