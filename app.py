"""PrepPilot - turns a job description into a personalised interview preparation plan and runs a mock interview.
AI mode : Claude or Gemini (key in .env)      Offline mode : rule-based plan and answer feedback, no key needed."""
import os, re, json, time
from concurrent.futures import ThreadPoolExecutor
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
LEVELS = ("Fresher", "Junior (1-3 yrs)", "Mid-level (3-6 yrs)", "Senior (6+ yrs)")

SKILL_Q = {
 "python": "Explain the difference between a list, tuple, set and dict in Python and when you would use each.",
 "java": "Explain how the JVM, JRE and JDK differ and how garbage collection works.",
 "javascript": "Explain closures, the event loop and the difference between var, let and const in JavaScript.",
 "typescript": "What problems does TypeScript solve compared with JavaScript, and what are generics?",
 "c++": "Explain pointers vs references in C++ and how memory is managed.",
 "c#": "Explain the difference between value types and reference types in C#.",
 "sql": "Explain INNER vs LEFT JOIN, GROUP BY with HAVING, and how an index speeds up a query.",
 "mysql": "How do indexes and transactions (ACID) work in a relational database such as MySQL?",
 "postgresql": "What are transactions, isolation levels and indexes in PostgreSQL?",
 "mongodb": "When would you choose a document database like MongoDB over a relational database?",
 "react": "Explain props vs state, the virtual DOM and when useEffect runs.",
 "angular": "Explain components, services and dependency injection in Angular.",
 "node.js": "How does Node.js handle many concurrent requests with a single thread?",
 "flask": "Walk through how a request flows through a Flask application from URL to response.",
 "django": "Explain Django's MVT pattern and how the ORM maps models to tables.",
 "spring boot": "What does Spring Boot auto-configuration do and how does dependency injection work?",
 "rest api": "What makes an API RESTful? Explain HTTP methods, status codes and idempotency.",
 "docker": "What is the difference between a Docker image and a container, and why use Docker?",
 "kubernetes": "What problems does Kubernetes solve, and what are pods and deployments?",
 "aws": "Which AWS services would you use to host a web application, and why?",
 "azure": "Which Azure services would you use to host and monitor a web application?",
 "git": "Explain git merge vs rebase and how you resolve a merge conflict.",
 "data structures": "Compare arrays, linked lists, hash maps and trees. When would you use each?",
 "algorithms": "Explain time and space complexity using binary search and sorting as examples.",
 "oop": "Explain the four OOP pillars with a real-world example.",
 "unit testing": "What makes a good unit test, and what is the difference between a mock and a stub?",
 "ci/cd": "What does a CI/CD pipeline do and what stages does it usually have?",
 "machine learning": "Explain overfitting and how you would prevent it.",
 "agile": "How does a Scrum sprint work and what is your role in it?",
 "linux": "How would you find which process is using a port and stop it on Linux?",
 "microservices": "What are the trade-offs between microservices and a monolith?",
}
EXTRA = "html,css,excel,power bi,tableau,pandas,numpy,tensorflow,pytorch,nlp,deep learning,jira,go,php,redis,kafka,graphql,system design".split(",")
ALL = list(SKILL_Q) + EXTRA
NICE = {"sql": "SQL", "aws": "AWS", "oop": "OOP", "ci/cd": "CI/CD", "nlp": "NLP", "rest api": "REST APIs", "node.js": "Node.js",
        "html": "HTML", "css": "CSS", "mysql": "MySQL", "postgresql": "PostgreSQL", "mongodb": "MongoDB", "c++": "C++", "c#": "C#",
        "graphql": "GraphQL", "php": "PHP", "go": "Go", "typescript": "TypeScript", "javascript": "JavaScript"}
STOP = set("a an the is are was were be to of in on at for and or my your i me we you it do does did can how what when where "
           "which who why with this that there any about would could should explain describe tell give your have has".split())

PLAN_HEAD = """You are an expert technical interviewer and career coach.
Analyse the job description and prepare a personalised interview plan for a candidate at this level: <<LV>>.
Prioritise by relevance to the job description. Do not invent requirements that are not implied by it.
Keep every item short (under 20 words) so the answer is quick to generate.
Reply with ONLY valid JSON (no markdown) in exactly this shape:
"""
PLAN_A = """{"role": "job title",
 "topics": [{"topic": "...", "likelihood": 0-100 integer estimate, "reason": "one short phrase"}],   (8 items, highest likelihood first)
 "technical_questions": ["... exactly 10 ..."],
 "behavioural_questions": ["... exactly 5 ..."]}"""
PLAN_B = """{"concepts_to_revise": ["... 10 short items ..."],
 "system_design": ["... 3-5 likely system design topics ..."],
 "plan": [{"day": 1, "focus": "...", "tasks": ["...", "...", "..."]}],   (exactly 7 days)
 "questions_to_ask": ["... exactly 5 intelligent questions for the interviewer ..."]}"""
PLAN_TAIL = "\n\nJOB DESCRIPTION:\n<<JD>>"

EVAL_PROMPT = """You are a strict but fair interviewer. Evaluate the candidate's answer.
Job description excerpt: <<JD>>
Candidate level: <<LV>>
Question type: <<K>>
Question: <<Q>>
Candidate answer: <<A>>
Score honestly: a vague, off-topic or incorrect answer must score below 5.
Reply with ONLY valid JSON: {"score": integer 0-10, "strengths": ["..."], "weaknesses": ["..."],
 "answer_structure": "how a strong answer should be structured, 1-2 sentences",
 "strong_answer_outline": "3-5 points an excellent answer would include"}"""


def label(s):
    return NICE.get(s, s.title())


def has(term, text):
    return re.findall(r"(?<![\w+#.])" + re.escape(term) + r"(?![\w+#])", text, re.I)


def detect(jd):
    found = [(s, len(m), jd.lower().find(s)) for s in ALL if (m := has(s, jd))]
    return [(s, n) for s, n, _ in sorted(found, key=lambda x: (-x[1], x[2]))]


def role_of(jd):
    for line in jd.splitlines():
        line = line.strip(" -*#\t")
        head = re.split(r"[.:|]", line)[0].strip()
        if 3 <= len(head) <= 90:
            return head[:80]
    return "the role"


def offline_plan(jd, level):
    found = detect(jd)
    skills = [s for s, _ in found]
    fresher, senior = level.startswith("Fresher"), level.startswith("Senior")
    tech = [SKILL_Q.get(s) or f"Describe a project where you used {label(s)}. What did you build and what went wrong?" for s in skills[:8]]
    if senior:
        extra = ["How do you review code and mentor less experienced engineers?",
                 "How would you design a scalable service for the main product described in this role?",
                 "How do you decide between paying down technical debt and shipping features?"]
    else:
        extra = ["Walk me through a project you are proud of and your exact contribution.",
                 "How do you debug a problem you have never seen before?",
                 "How do you make sure the code you write is correct and maintainable?"]
    pool = extra + ["What happens when you type a URL into a browser and press Enter?",
                    "What is the difference between a process and a thread?",
                    "How would you test a login feature?",
                    "Explain a data structure you used in a project and why you chose it."]
    tech = (tech + pool)[:10]
    beh = (["Tell me about a time you led or mentored someone.", "Describe a conflict with a stakeholder and how you resolved it.",
            "Tell me about a decision you made with incomplete information.", "Describe a failure and what you changed afterwards.",
            "Why do you want this role and what will you do in the first 90 days?"] if senior else
           ["Tell me about yourself.", "Describe a time you worked under a tight deadline.",
            "Tell me about a disagreement with a teammate and how you handled it.",
            "Describe a mistake you made and what you learned from it.", "Why do you want this role and this company?"])
    topics = [{"topic": label(s), "likelihood": max(40, min(95, 60 + 10 * n - 3 * i)),
               "reason": f"Mentioned {n} time{'s' if n > 1 else ''} in the job description"} for i, (s, n) in enumerate(found[:7])]
    topics.append({"topic": "Behavioural / HR round", "likelihood": 85, "reason": "Asked in almost every interview"})
    topics = sorted(topics, key=lambda t: -t["likelihood"])
    concepts = [f"{label(s)} fundamentals and common questions" for s in skills[:7]]
    concepts += ["Data structures and algorithms basics", "STAR method for behavioural answers",
                 "Your resume projects: design and your contribution", "Research on the company and the role"]
    jl = jd.lower()
    sd = []
    if re.search(r"scal|distributed|microservice|high.?traffic|performance", jl) or senior:
        sd += ["Design a scalable REST API with caching and load balancing", "Choosing between SQL and NoSQL for a new service"]
    sd += ["Design a URL shortener", "Design a simple chat or notification system", "Database schema design and indexing"]
    s = skills + ["core concepts"] * 4
    plan = [
        {"day": 1, "focus": "Understand the role", "tasks": ["Read the job description and highlight required skills", "Match each skill to a project or experience of yours", f"Revise {label(s[0])} basics"]},
        {"day": 2, "focus": f"Core skills: {label(s[0])} and {label(s[1])}", "tasks": [f"Answer the {label(s[0])} interview question aloud", f"Revise {label(s[1])} fundamentals", "Write short notes on what you find hard"]},
        {"day": 3, "focus": f"{label(s[2])} and data structures", "tasks": [f"Revise {label(s[2])}", "Review arrays, hash maps, stacks, queues and trees", "Solve 3 easy practice problems"]},
        {"day": 4, "focus": "Hands-on practice", "tasks": ["Solve 4 coding problems under a timer", "Practise SQL queries with joins and grouping" if "sql" in skills else "Practise a small coding task end to end", "Review your mistakes"]},
        {"day": 5, "focus": "Projects and system design", "tasks": ["Prepare a 2-minute walkthrough of your best project", "Study 2 system design topics from this plan", "Explain your design choices and trade-offs"]},
        {"day": 6, "focus": "Behavioural round and mock interview", "tasks": ["Write 4 STAR stories (situation, task, action, result)", "Take the mock interview in PrepPilot", "Practise introducing yourself in 60 seconds"]},
        {"day": 7, "focus": "Revision and logistics", "tasks": ["Revise your weakest topics", "Prepare your questions for the interviewer", "Check documents, timing and internet; rest well"]},
    ]
    ask = ["What does success look like in the first 90 days?", "What does the team's tech stack and development process look like?",
           "How are code reviews, testing and deployments handled?", "What are the biggest challenges the team is facing right now?",
           "What learning and growth opportunities does the company offer for this role?"]
    return {"role": role_of(jd), "level": level, "topics": topics, "technical": tech, "behavioural": beh, "concepts": concepts[:12],
            "system_design": sd[:5], "plan": plan, "ask": ask}


STAR = {"situation": r"\b(situation|context|when i|at the time|project)\b", "task": r"\b(task|goal|responsib|needed to|objective)\b",
        "action": r"\b(i (did|built|created|decided|led|implemented|wrote|fixed|organi[sz]ed|took)|my role)\b",
        "result": r"\b(result|outcome|improv|reduc|increas|saved|achiev|learn|delivered)\b"}


def offline_eval(q, a, kind):
    words, low = len(a.split()), a.lower()
    kw = [w for w in re.findall(r"[a-z0-9+#]+", q.lower()) if len(w) >= 4 and w not in STOP]
    cov = sum(1 for w in kw if w[:5] in low) / len(kw) if kw else 0.5
    nums = bool(re.search(r"\d", a))
    ex = bool(re.search(r"\b(for example|for instance|such as|e\.g\.|in my project|i used)\b", low))
    reason = bool(re.search(r"\b(because|therefore|so that|trade-?off|however|which means|complexity)\b", low))
    star = [k for k, p in STAR.items() if re.search(p, low)]
    sc = min(words / 90, 1) * 3 + cov * 2.5
    sc += (len(star) * 0.9 + (0.9 if nums else 0)) if kind == "behavioural" else ((1.5 if ex else 0) + (1.0 if reason else 0) + (1.0 if nums else 0))
    good, bad = [], []
    (good if words >= 60 else bad).append("Good level of detail" if words >= 60 else "Too short: aim for about 60-120 words")
    (good if cov >= 0.6 else bad).append("Covers the key terms of the question" if cov >= 0.6 else "Address the key terms of the question more directly")
    if kind == "behavioural":
        (good if len(star) >= 3 else bad).append("Follows a Situation-Task-Action-Result flow" if len(star) >= 3 else "Missing STAR parts: " + ", ".join(k for k in STAR if k not in star))
    else:
        (good if ex else bad).append("Uses a concrete example" if ex else "Add a real example from a project")
        if reason:
            good.append("Explains reasons and trade-offs")
    if not nums:
        bad.append("Add a measurable detail (numbers, size, time saved)")
    structure = ("STAR: Situation, Task, Action, then a measurable Result and what you learned." if kind == "behavioural" else
                 "Definition, how it works, a real example from your project, then trade-offs or when not to use it.")
    return {"score": max(1, min(10, round(sc))), "strengths": good[:4] or ["You attempted the question and stayed on topic"],
            "weaknesses": bad[:4], "structure": structure, "outline": ""}


def num(x, lo, hi, default):
    try:
        return max(lo, min(hi, int(float(x))))
    except (TypeError, ValueError):
        return default


def norm_plan(d, level):
    def L(k, n):
        return [str(x).strip()[:300] for x in (d.get(k) or []) if str(x).strip()][:n]
    topics = [{"topic": str(t.get("topic", ""))[:80], "likelihood": num(t.get("likelihood"), 0, 100, 50), "reason": str(t.get("reason", ""))[:160]}
              for t in (d.get("topics") or []) if isinstance(t, dict) and t.get("topic")][:10]
    plan = [{"day": i + 1, "focus": str(p.get("focus", ""))[:90], "tasks": [str(x)[:180] for x in (p.get("tasks") or [])][:5]}
            for i, p in enumerate((d.get("plan") or [])[:7]) if isinstance(p, dict)]
    out = {"role": str(d.get("role") or "the role")[:100], "level": level, "topics": topics, "technical": L("technical_questions", 10),
           "behavioural": L("behavioural_questions", 5), "concepts": L("concepts_to_revise", 12), "system_design": L("system_design", 6),
           "plan": plan, "ask": L("questions_to_ask", 5)}
    if len(out["technical"]) < 5 or len(out["behavioural"]) < 3 or len(plan) < 5 or not topics:
        raise ValueError("incomplete AI response")
    return out


_GEMINI = "https://generativelanguage.googleapis.com/v1beta/"
_model_cache = []


def _err(r):
    try:
        return r.json()["error"]["message"]
    except Exception:
        return f"HTTP {r.status_code}"


def gemini(prompt, timeout=40, budget=55):
    """Call Gemini with the key in a header. Picks an available Flash model automatically."""
    key = os.getenv("GEMINI_API_KEY", "").strip().strip("\"'")
    h = {"x-goog-api-key": key, "Content-Type": "application/json"}
    t0 = time.monotonic()
    models = [os.getenv("GEMINI_MODEL", "").strip()]
    if not _model_cache:
        try:
            r = requests.get(_GEMINI + "models", headers=h, params={"pageSize": 100}, timeout=10)
            if r.ok:
                names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                         if "generateContent" in m.get("supportedGenerationMethods", [])]
                good = [n for n in names if "flash" in n and not re.search(r"lite|image|tts|live|audio|preview|exp|8b", n)]
                ver = sorted((n for n in good if re.match(r"gemini-\d", n)), reverse=True)
                _model_cache.extend((ver + [n for n in good if n not in ver])[:3])
            elif "key" in _err(r).lower():
                raise RuntimeError(_err(r))
        except requests.RequestException:
            pass
    models += _model_cache + ["gemini-2.5-flash", "gemini-flash-latest"]
    last = "No Gemini model available"
    for m in dict.fromkeys(x for x in models if x):
        for cfg in ({"responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}},
                    {"responseMimeType": "application/json"}, {}):
            if time.monotonic() - t0 > budget:
                raise RuntimeError("AI request timed out")
            t1 = time.monotonic()
            r = requests.post(_GEMINI + f"models/{m}:generateContent", headers=h, timeout=timeout,
                              json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg})
            if r.ok:
                app.logger.warning("Gemini model %s answered in %.1fs", m, time.monotonic() - t1)
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            last = _err(r)
            if "api key" in last.lower() or r.status_code in (401, 403):
                raise RuntimeError(last)
            if r.status_code != 400:
                break
    raise RuntimeError(last)


def llm(prompt, max_tokens=3500, timeout=60):
    if os.getenv("ANTHROPIC_API_KEY"):
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=timeout,
                          headers={"x-api-key": os.getenv("ANTHROPIC_API_KEY").strip(), "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), "max_tokens": max_tokens,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    if os.getenv("GEMINI_API_KEY"):
        return gemini(prompt, timeout=timeout, budget=timeout)
    return None


def parse(text):
    return json.loads(re.search(r"\{.*\}", text, re.S).group())


def ai_plan(jd, level):
    """Ask the AI for the plan in two smaller parallel requests. If one half fails, the offline engine fills it in."""
    base = offline_plan(jd, level)
    merged = {"role": base["role"], "topics": base["topics"], "technical_questions": base["technical"],
              "behavioural_questions": base["behavioural"], "concepts_to_revise": base["concepts"],
              "system_design": base["system_design"], "plan": base["plan"], "questions_to_ask": base["ask"]}

    def part(schema):
        p = (PLAN_HEAD + schema + PLAN_TAIL).replace("<<LV>>", level).replace("<<JD>>", jd)
        return parse(llm(p, 2500, 70))

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(part, PLAN_A), ex.submit(part, PLAN_B)]
    errs = []
    for f in futs:
        try:
            merged.update(f.result())
        except Exception as e:
            errs.append(e)
    if len(errs) == 2:
        raise errs[0]
    return norm_plan(merged, level), bool(errs)


_hits = {}


def limited(ip, n=15, window=3600):
    now = time.time()
    q = [x for x in _hits.get(ip, []) if now - x < window]
    _hits[ip] = q if len(q) >= n else q + [now]
    return len(q) >= n


def client_ip():
    return request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "?"


def keyed():
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY"))


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/plan")
def api_plan():
    j = request.get_json(silent=True) or {}
    jd = str(j.get("jd", "")).strip()[:12000]
    level = j.get("level") if j.get("level") in LEVELS else LEVELS[0]
    if len(jd) < 60:
        return jsonify(error="Please paste the job description (at least 60 characters)."), 400
    mode, err, data = "Offline mode (rule-based plan)", "", None
    if keyed():
        if limited(client_ip()):
            mode = "Offline mode (demo AI limit reached, try later)"
        else:
            try:
                data, partial = ai_plan(jd, level)
                mode = "AI mode (some parts offline)" if partial else "AI mode"
            except Exception as e:
                app.logger.warning("AI plan failed: %s", e)
                mode, err = "Offline mode (AI unavailable)", str(e)[:200]
    data = data or offline_plan(jd, level)
    data.update(mode=mode, ai_error=err)
    return jsonify(data)


@app.post("/api/evaluate")
def api_evaluate():
    j = request.get_json(silent=True) or {}
    q, a = str(j.get("question", ""))[:500], str(j.get("answer", "")).strip()[:3000]
    kind = "behavioural" if j.get("kind") == "behavioural" else "technical"
    if len(a.split()) < 3:
        return jsonify(error="Please write a longer answer before submitting."), 400
    mode, err, out = "Offline feedback (keyword and structure check)", "", None
    if keyed() and not limited(client_ip(), n=60):
        try:
            p = EVAL_PROMPT.replace("<<JD>>", str(j.get("jd", ""))[:2500]).replace("<<LV>>", str(j.get("level", ""))[:30])
            d = parse(llm(p.replace("<<K>>", kind).replace("<<Q>>", q).replace("<<A>>", a), 1200, 50))
            out = {"score": num(d.get("score"), 0, 10, 5), "strengths": [str(x)[:200] for x in d.get("strengths") or []][:4],
                   "weaknesses": [str(x)[:200] for x in d.get("weaknesses") or []][:4],
                   "structure": str(d.get("answer_structure", ""))[:300], "outline": str(d.get("strong_answer_outline", ""))[:500]}
            mode = "AI feedback"
        except Exception as e:
            app.logger.warning("AI evaluation failed: %s", e)
            mode, err = "Offline feedback (AI unavailable)", str(e)[:200]
    out = out or offline_eval(q, a, kind)
    out.update(mode=mode, ai_error=err)
    return jsonify(out)


@app.errorhandler(Exception)
def on_error(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify(error=e.description), e.code
    app.logger.exception("Unhandled error")
    return jsonify(error="Something went wrong on the server. Please try again."), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)