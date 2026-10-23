# JobSearchAIAgentByAnish1989

A multi-user AI job-search agent for Auckland, built with Django and Docker.
The admin gives each person access. Every person has a private space: their CVs, jobs,
applications and AI questions are never mixed with another person's.

## Features
- **Admin access control** - only the admin creates users, can disable a login, and sees an audit log.
- **Multiple CVs per user** - upload PDF / DOCX / TXT or paste text; edit any time.
- **Job search** - "Search jobs" button with a "what type of job?" box, plus automatic search every day at **8:00 AM Auckland time**.
  Public pages on SEEK, Student Job Search and Trade Me Jobs are read politely (robots.txt respected, no login/CAPTCHA bypass).
- **Add jobs by link or by pasting** the job description (use this for LinkedIn, Indeed and others that block automated reading).
- **AI match score** with reasons and a tip (Claude). Free keyword matching is used if no API key is set.
- **Tailored ATS-friendly NZ-style CV, cover letter and application email** - download as Word (.docx).
- **AI questions** - when the AI needs true information, it asks "Question for <name>: ..." instead of guessing.
- **Interview preparation** - likely questions, sample answers from the person's real background, and YouTube search links.
- **Dashboard** - jobs found today, AI suggested, applied today/total, interviews, follow-ups due, AI daily summary.
- **Application records** - status, applied date, follow-up reminder (7 days), interview date, notes.
- **Auto mode (off by default)** - only the person themselves can turn it on. It prepares applications automatically
  for strong matches; the final submission is always done by the person on the employer's website.

## Easy start (double-click)
| File | What it does |
|---|---|
| `start.bat` | Starts Docker and the app, checks the port is free, sets up `.env` and the admin login on first run, opens the dashboard |
| `stop.bat` | Stops the app (data is kept) |
| `search_now.bat` | Runs the job search now for every active user |
| `create_admin.bat` | Creates another admin login |
| `logs.bat` | Shows live logs (for problems) |
| `backup.bat` | Copies the `data` folder to `backups\data_<date>` |
| `run_tests.bat` | Runs the automated tests |

The app restarts by itself whenever Docker Desktop is running. To start everything when Windows starts,
turn on "Start Docker Desktop when you sign in" in Docker Desktop settings.

## Run it (Windows, Docker Desktop)
```powershell
cd D:\JobSearchAgent\JobSearchAIAgentByAnish1989
copy .env.example .env        # then open .env and set DJANGO_SECRET_KEY and ANTHROPIC_API_KEY
docker compose up -d --build
docker compose exec web python manage.py createsuperuser   # your admin login (one time)
```
Open **http://localhost:8010** (port set by `APP_PORT` in `.env`; 8000 is left free for the ERP) and log in. Click **Give access** to add a user (e.g. SaruTuitui).

Useful commands:
```powershell
docker compose logs -f scheduler                      # see the 8:00 AM schedule
docker compose exec web python manage.py run_daily_search   # run the search for everyone now
docker compose exec web python manage.py test tests   # run the tests
docker compose down                                   # stop
```
All data (database and uploads) is saved in the `data\` folder. Back up this folder.

## Claude API
Get a key at https://console.anthropic.com. API usage is pay-as-you-go and is separate from a Claude.ai
subscription. Each search scores at most 10 new jobs per person to keep costs small. Change the model with `CLAUDE_MODEL` in `.env`.

## Project structure
```
config/        Django settings and URLs
agent/
  models.py    Candidate, CVDocument, Job, Application, AIQuestion, AuditLog
  services.py  crawling, Claude prompts, scoring, DOCX export
  workflow.py  search -> save -> score -> prepare steps
  views.py     web pages (with per-user access checks)
  management/commands/run_scheduler.py     daily 8:00 AM loop
  management/commands/run_daily_search.py  one search run for all active users
docker/entrypoint.sh  starts web (gunicorn) or scheduler
tests/         automated tests
```

## Privacy and safety
- `.env` (API key) and `data/` (personal CVs) are excluded from git. Never commit them.
- Do not put passport, visa or IRD numbers or date of birth in CVs.
- Job pages are treated as untrusted text; the AI is told to ignore instructions inside them.
