# Knowledge base (RAG)

Added on 6 November 2026. The code comes from the CyberQuest knowledge base
(`D:\Anish_Saru_Arica\CyberQuest_Django_code_v1.2_31Oct`, `apps/kb` and `cyberquest-rag`) and was changed for
this job agent.

## What it does

Each person uploads their own documents (CVs, job adverts, company notes, interview notes) and can then:

- **Ask a question** and get a short answer with the sources it came from, for example
  "What experience should I mention for a kitchen hand job?"
- **Interview practice**: likely interview questions with honest answer tips, written from their documents.

The AI is told to use only the uploaded text and never to invent employers, titles, dates or experience.

## Many CVs and new CVs for each job (added 6 Nov 2026)

- **Save all your CVs.** On *My documents*, choose **What is it? → My CV** (or *My cover letter*) and upload a
  PDF, Word (.docx), TXT or MD file. Each person can save as many as they like (kitchen CV, cleaning CV, IT CV ...).
- **One store.** A CV uploaded here is also saved in **My profile & CVs**, and a CV added or edited there is copied
  into the knowledge base by itself. Deleting it in one place deletes it in both. The button **🔄 Add my saved CVs**
  copies older CVs that are not in the knowledge base yet.
- **Make a CV for a job.** On *My documents*, choose a saved job or paste a job advert, then press
  **Make my CV + cover letter**. Or press **📚 Create from my knowledge base** on any job page.
  The service finds the best parts of *your own* CVs for that job (never shared tips, never another user's CVs),
  and DeepSeek writes a one-page NZ-style CV, a cover letter and an application email. If you saved a cover letter,
  it matches its tone.
- The result opens on the job page, where you can read and edit it, then download **CV (PDF / Word)** and
  **Cover letter (PDF / Word)**. Replace any `[ADD: ...]` notes with true information before sending.
- Nothing is sent to an employer automatically.

## Privacy: who sees what

| | User | Admin |
|---|:---:|:---:|
| Ask, interview practice, upload, list, delete **own** documents | ✔ | ✔ (in any user's space, written to the activity log) |
| See **another user's** documents | ✘ | ✔ (logged) |
| Upload / delete **shared** documents (visible to everyone) | ✘ | ✔ |
| Change the AI model settings, test connection | ✘ | ✔ |

- Every user has a private knowledge base inside the service (`c<user id>`). A question from one user can never
  find another user's text. This is checked again by the service itself.
- If the admin turns **AI off** for a user, that user cannot ask or make interview questions (uploading still
  works; it stays on the laptop).
- When a user is deleted, their documents are deleted too (if the service is running).
- Questions are limited to 60 per user per hour.

## Where it is in the app

Left menu: **📚 Knowledge base** (Ask page). The button **My documents & interview practice** opens the second page.
The admin also sees **AI model settings** on that page. **System health** shows whether the service is running.

## How it works

```
Browser -> Django website (kb app, /c/<id>/kb/...) -> Knowledge base service (FastAPI, knowledgebase-rag/)
                                                       -> finds the best pieces in its own Chroma store (data/rag/chroma)
                                                       -> DeepSeek (OpenAI-compatible API) writes the answer
```

| Path | What |
|---|---|
| `kb/` | Django app: pages, JSON proxy (`api.py`), the only code that calls the service (`services.py`) |
| `kb/static/kb/` | Page scripts (answers are shown as plain text, never as HTML) |
| `knowledgebase-rag/app/` | The service: `main.py` endpoints, `store.py` read/split/store/search, `llm.py` model call, `config.py` settings |
| `knowledgebase-rag/job_search_knowledge_base_NZ.md` | Shared starter tips, loaded automatically the first time |
| `data/rag/` | Documents (`chroma/`), AI model settings with the key (`model_config.json`), search model (`hf/`). Not in git. |
| `tests/test_kb.py` | Tests (the service is faked) |

## Settings (.env)

| Name | What it does |
|---|---|
| `RAG_SERVICE_KEY` | Shared secret between the website and the service. Copied from CyberQuest. |
| `RAG_BASE_URL` | Where the website finds the service. No Docker: `http://127.0.0.1:9010`. Docker sets `http://rag:9000` itself. |
| `RAG_LLM_BASE_URL`, `RAG_LLM_MODEL`, `RAG_LLM_API_KEY` | First-start AI model (DeepSeek). The DeepSeek key was copied from CyberQuest. |

After the first start, the AI model settings live in `data/rag/model_config.json`; the admin changes them on the
Knowledge base page (no restart needed). Never put real keys in the README or in git.

## Start and stop

- **Docker** (`docker-start.bat`): starts a third container, `rag`. The first build downloads the AI packages
  (10-20 minutes). Logs: `docker compose logs rag`.
- **No Docker** (`nodocker-start.bat`): the first run makes `knowledgebase-rag\.venv` (about 1 GB, 10-20 minutes),
  then starts the service in a small window called **JobSearchAI-kb** on port 9010. `nodocker-stop.bat` stops it.
  Check it: open `http://127.0.0.1:9010/health`, it must show `{"ok":true}`.

If the service is not running, the rest of the app still works; only the Knowledge base pages say
"The knowledge base service is not running right now."

## Problems

| Message | Fix |
|---|---|
| The knowledge base service is not running right now | Start it (see above). Check System health. |
| ...refused the connection. Ask the admin to check RAG_SERVICE_KEY | The key must be the same for the website and the service. Restart both after changing `.env`. |
| The AI model did not answer | Admin: Knowledge base > My documents > AI model settings > Test connection. Check the DeepSeek key and credit. |
| I couldn't find this in the knowledge base | Upload documents that contain the answer, or ask with words used in them. |
| No readable text found in the document | The PDF is a scan. Use a text PDF, `.txt` or `.md`. |
