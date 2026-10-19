# PrepPilot - AI Interview Prep Generator

Paste a job description, pick your experience level, and get: interview topics with estimated likelihood,
10 technical + 5 behavioural questions, a study checklist, a 7-day plan, questions to ask the interviewer,
system-design topics, and a **mock interview** that asks one question at a time and gives a score,
strengths, weaknesses and a suggested answer structure.

## Run in VS Code
1. Open this folder in VS Code, then open a terminal (Ctrl + `).
2. Create and activate a virtual environment
   - Windows: `python -m venv .venv` then `.venv\Scripts\activate`
   - Mac/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `python app.py` and open http://127.0.0.1:5000
5. Click **Load sample**, then **Generate Preparation Plan**, then **Start Mock Interview**.

## AI mode (optional)
Copy `.env.example` to `.env` and add ONE key: `GEMINI_API_KEY` (free from Google AI Studio) or `ANTHROPIC_API_KEY`.
Without a key the app works in offline mode: the plan is built from skills found in the job description and
answer feedback is a keyword and structure check. With a key, Claude/Gemini write the plan and evaluate answers.
Each visitor is limited to a number of AI calls per hour, so a public demo cannot drain your key.

## Deploy free on Render
1. Push this folder to GitHub (check that `.env` is not included).
2. On render.com choose New > Blueprint (uses `render.yaml`) and the Free instance.
3. Optionally add `GEMINI_API_KEY` in the Environment tab. Free services sleep after 15 minutes idle,
   so the first request afterwards takes about a minute.

## Structure
- `app.py` - Flask API: plan generation, mock-interview evaluation, offline engine, AI calls
- `templates/index.html` - UI (Tailwind via CDN, needs internet)
- `docs/Project_Report.docx` - project report
