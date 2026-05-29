# MS Printhead Dashboard

A real-time **Printhead monitoring dashboard** for MS printers.
Built with Python + Flask, connecting directly to printers over the local network.

---

## Features

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Real-time printhead status for all machines |
| History | `/history` | Daily head installation history |
| Serial Search | `/serial` | Search head history by Serial Number |
| All Serials | `/serials` | Full serial list across all machines |

---

## Requirements

- Python 3.10+ ([Download](https://www.python.org/downloads/))
- Local network access to MS printers

---

## Installation

**1. Clone the repo**
```bash
git clone https://github.com/<your-username>/ms-printhead-dashboard.git
cd ms-printhead-dashboard
```

**2. Configure printer IPs**
```bash
copy machines.ini.example machines.ini
```
Edit `machines.ini` and set the IP address for each printer on your network.

**3. Run the installer (recommended)**
```bash
install.bat
```
The installer will automatically install Python packages, initialize the database, register a Windows Task Scheduler job, and create a Desktop shortcut.

**4. Or install manually**
```bash
pip install -r requirements.txt
python app.py
```

---

## Usage

Launch with `start.bat` or the Desktop shortcut, then open your browser at:

```
http://localhost:5000
```

---

## Project Structure

```
ms-printhead-dashboard/
├── app.py                  # Flask web application
├── save_snapshot.py        # Snapshot job (runs every 2 hours)
├── create_sample_db.py     # Generates mock database for demo
├── requirements.txt        # Python dependencies
├── machines.ini.example    # Config template (copy and set your IPs)
├── install.bat             # Automated installer
├── start.bat               # Launch the app
├── setup_task.bat          # Register Task Scheduler manually
├── templates/
│   ├── index.html          # Dashboard
│   ├── history.html        # History
│   ├── serial.html         # Serial Search
│   └── serials.html        # All Serials
├── test_unit.py            # Unit tests
├── test_snapshot.py        # Integration tests
└── .gitignore
```

> Files excluded from the repo (via `.gitignore`): `machines.ini`, `history.db`, `snapshot.log`

---

## Demo with Mock Data

To run the app without connecting to real printers:

```bash
python create_sample_db.py       # generates history_sample.db
copy history_sample.db history.db
python app.py
```

---

## Automatic Snapshots

`install.bat` registers a **Windows Task Scheduler** job that runs `save_snapshot.py` every 2 hours, saving printhead state to the SQLite database.

To register the task manually at any time:
```bash
setup_task.bat
```

---

## Tests

```bash
python test_unit.py -v       # Unit tests
python test_snapshot.py      # Integration tests (requires network access)
```

---

## Tech Stack

- **Backend:** Python, Flask
- **Database:** SQLite
- **Frontend:** Bootstrap 5, Bootstrap Icons
- **Scheduler:** Windows Task Scheduler
