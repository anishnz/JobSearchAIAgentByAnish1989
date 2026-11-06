# How to use the Knowledge base and the local AI (Ollama)

Written 6 November 2026. Simple steps for Anish (admin) and every user.

## 1. What is what

| Part | What it does | Costs money? |
|---|---|---|
| **Knowledge base** | Keeps each person's own CVs, cover letters, job adverts and notes. It finds the best parts for a question or a job. | No (it runs on this laptop) |
| **Local AI (Ollama)** | An AI model that runs on this laptop. It reads CVs, scores jobs and writes CVs, cover letters and interview practice. | No, and your data stays on the laptop |
| **DeepSeek** | A cloud AI. The knowledge base used it first (from CyberQuest). | Yes, a little (uses the DeepSeek key) |
| **Claude** | A cloud AI for each user who adds their own Claude API key. | Yes (pay as you go) |

You can use the local AI for everything, so nothing costs money.

## 2. Start the app

1. Make sure **Ollama** is running on the laptop (its icon is in the system tray, near the clock).
   If not, open the Ollama app from the Start menu.
2. Double-click **nodocker-start.bat** (or **docker-start.bat** if you use Docker).
   The first start sets up the knowledge base and can take 10-20 minutes. Later starts are quick.
3. The website opens at `http://localhost:8010`. Log in.

## 3. Admin: choose the local AI model (one time)

**For the whole app (CV reading, job scores, CV writing, interview practice):**

1. Left menu → **🛠️ System settings**.
2. In the card **💻 Local AI (Ollama on this laptop)**, the list shows the models installed in Ollama.
3. Choose a model and press **Save model**.
4. Press **Test local AI**. You should see "Local AI works. ... replied: OK".
5. Press **Use local AI for all users** (each user can still change it in their own Settings).

**For the knowledge base answers:**

1. Left menu → **📚 Knowledge base** → **My documents & interview practice**.
2. At the bottom, card **AI model settings** → **Quick choice**.
3. Choose your Ollama model and press **Use this local model**. (Press **☁️ Use DeepSeek (cloud)** to go back.)
4. Press **Test connection**. You should see "Connection works. The model replied: pong".

**Which model?** A bigger model (for example 7B or 8B) writes better CVs but is slower. A small model
(1B-3B) is fast but makes more mistakes. A model around 7B-8B is a good balance on a laptop.
Not sure which models you have? In a terminal type `ollama list`. To add one: `ollama pull llama3.1:8b`.

**System health** (left menu → 🩺 System health) shows "Local AI (Ollama)" and "Knowledge base service".
Both should be green.

## 4. Every user: choose your AI

1. Left menu → **⚙️ Settings**.
2. Under **🤖 AI**, choose **Local AI on this laptop (Ollama, free)** (or Claude if you have your own key).
3. Press **Save settings**, then **Test my AI**.

## 5. Save all your CVs in the knowledge base

1. Left menu → **📚 Knowledge base** → **My documents & interview practice**.
2. In **Upload a document**: choose the file (PDF, Word .docx, TXT or MD), choose **What is it? → My CV**,
   type a title (for example "Kitchen CV") and, in **Tags**, the jobs it is best for (for example "kitchen hand, dishwasher").
3. Press **Upload**. Do the same for each CV and cover letter.
4. CVs you saved before in **My profile & CVs**: press **🔄 Add my saved CVs** once.

Your documents are private. Only you (and the admin) can see them. Another user's questions never find them.

## 6. Make a new CV and cover letter for a job

**Way 1 - from the knowledge base page:**

1. **📚 Knowledge base** → **My documents & interview practice** → card **✍️ Make a CV for a job**.
2. Choose a saved job, **or** type the job title and paste the whole job advert.
3. Press **Make my CV + cover letter** and wait (local AI: up to a few minutes).

**Way 2 - from a job:** open the job (**🔎 Find jobs** → click a job) and press **📚 Create from my knowledge base**.

Then, on the job page:

1. Read the CV, cover letter and email. Fix anything that is wrong.
2. Replace every **[ADD: ...]** note with true information (or delete it).
3. Download: **⬇ CV (PDF)**, **⬇ CV (Word)**, **⬇ Cover letter (PDF)**, **⬇ Cover letter (Word)**.
4. Apply on the employer's website, or use **Send application** (it only sends when you press Send).

The AI only uses facts from your own CVs and profile. It never invents jobs, dates or skills.

## 7. Ask questions and practise interviews

- **📚 Knowledge base** (Ask page): type a question, for example "Which of my CVs is best for a cleaner job?"
  The answer shows its sources.
- **My documents & interview practice** → **Interview practice**: type the job (for example
  "kitchen hand at a busy cafe") and press **Make questions**. Open **Show answer tip** for each question.

## 8. If something does not work

| Message | What to do |
|---|---|
| Ollama is not reachable / Local AI (Ollama) is not running | Open the Ollama app, wait 10 seconds, reload the page. |
| Ollama model '...' is not installed | Choose another model in System settings, or run `ollama pull <name>`. |
| Local AI took too long | Use a smaller model, close other big programs, or try again. (Wait time: `OLLAMA_TIMEOUT` in `.env`, default 600 seconds.) |
| The knowledge base service is not running | Run the start file again. Check System health. |
| No CV in your knowledge base yet | Upload at least one CV (What is it? → My CV). |
| Docker: Ollama not reachable from the app | Docker uses `http://host.docker.internal:11434`. If it still fails, set the Windows environment variable `OLLAMA_HOST=0.0.0.0`, restart Ollama, then run docker-start.bat again. |
| Free basic mode is used | AI is off, or no model/key is chosen. See steps 3 and 4. |

If the local AI fails in the middle of a job, the app uses the free basic version, so you still get a draft.

More technical details: [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md).
