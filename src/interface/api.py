from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from domain.schemas import UserRequest
from interface.cli import build_engine

app = FastAPI(title="LedgerMind API")
engine = build_engine()

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>LedgerMind</title>
    <style>
      body { font-family: sans-serif; margin: 2rem; max-width: 900px; }
      form { display: grid; gap: .75rem; }
      label { font-weight: 600; }
      input, textarea, button { font: inherit; padding: .6rem; }
      textarea { min-height: 90px; }
      .row { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; }
      pre { background: #111; color: #eee; padding: 1rem; overflow: auto; border-radius: 8px; }
    </style>
  </head>
  <body>
    <h1>LedgerMind</h1>
    <p>Minimal test UI for <code>/analyze</code>.</p>
    <form id="analyze-form">
      <div class="row">
        <div>
          <label for="request_id">Request ID</label>
          <input id="request_id" name="request_id" value="req_web_001" />
        </div>
        <div>
          <label for="user_id">User ID</label>
          <input id="user_id" name="user_id" value="u_123" />
        </div>
      </div>
      <div class="row">
        <div>
          <label for="timezone">Timezone</label>
          <input id="timezone" name="timezone" value="America/New_York" />
        </div>
        <div>
          <label for="policy_profile">Policy Profile</label>
          <input id="policy_profile" name="policy_profile" value="default_v1" />
        </div>
      </div>
      <div>
        <label for="message">Message</label>
        <textarea id="message" name="message">How did I do last month and what should I change?</textarea>
      </div>
      <button type="submit">Analyze</button>
    </form>
    <h2>Response</h2>
    <pre id="result">Submit a request.</pre>
    <script>
      const form = document.getElementById('analyze-form');
      const result = document.getElementById('result');
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
          request_id: form.request_id.value,
          user_id: form.user_id.value,
          message: form.message.value,
          context: {
            timezone: form.timezone.value,
            policy_profile: form.policy_profile.value
          }
        };
        result.textContent = "Loading...";
        try {
          const res = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          const data = await res.json();
          result.textContent = JSON.stringify(data, null, 2);
        } catch (err) {
          result.textContent = String(err);
        }
      });
    </script>
  </body>
</html>
"""

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/analyze")
def analyze(request: UserRequest) -> dict:
    answer, issues = engine.run(request)
    return {
        "request_id": request.request_id,
        "user_id": request.user_id,
        "answer": answer.model_dump(by_alias=True),
        "issues": [issue.__dict__ for issue in issues],
    }
