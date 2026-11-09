# AI assistant setup (Windows PowerShell)

The application entry point is `main.py` (login, home, simulation dashboard).
The assistant uses the official OpenAI Python SDK with OpenRouter's compatible
Responses API. Defaults are `OPENAI_BASE_URL=https://openrouter.ai/api/v1` and
`OPENAI_MODEL=openai/gpt-5-mini`. Set `OPENAI_API_KEY` to an **OpenRouter** API key,
not a direct OpenAI key. The base URL and model can both be overridden.
OpenRouter documents `/responses` as stateless: this app sends history explicitly,
uses `store=False`, and never sends `previous_response_id`.
See https://openrouter.ai/docs/api/reference/responses/overview .

Use your existing Python environment, or create a virtual environment with
Python 3.10 or newer (3.12 recommended for broad GUI package compatibility):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For an environment that already runs this project, install only the new dependency:

```powershell
python -m pip install -r requirements-ai.txt
```

These install commands access the network. No packages were installed during implementation.
If the Windows `python` alias fails, use the actual interpreter path. The inspected
environment has Python 3.15.2 at:

```powershell
& "$env:LOCALAPPDATA\Python\pythoncore-3.15-64\python.exe" main.py
```

Set variables in the same PowerShell window used to launch the app. This key prompt
avoids putting your key in shell command history:

```powershell
$aiSecret = Read-Host 'OpenRouter API key' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $aiSecret).Password
$env:OPENAI_BASE_URL = 'https://openrouter.ai/api/v1'
$env:OPENAI_MODEL = 'openai/gpt-5-mini'
python main.py
```

For persistent per-user variables, use Windows “Edit environment variables for your
account”, create `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL`, then restart VS Code and terminals.
Environment variables are plaintext credentials; do not share them. `.env.example`
is a template only; the app does not automatically load `.env` files.

## Offline checks

```powershell
python -m unittest discover -s tests -v
python -m compileall -q main.py simulation_dash.py ai_chat.py ai_service.py tests
```

Tests use injected mock clients, never paid API requests. Missing credentials produce
a useful message without network access. Simulation, forms, and chat interface remain
usable without credentials; actual generated answers require the SDK and a valid key.

## First real connection test (only when you approve sending a paid request)

Launch `main.py`, sign in and open the simulation dashboard's AI assistant. Ask
“Explain PEEP in a synthetic ventilation simulation.” Leave parameter sharing off.
Click Send to AI, review Details, and confirm. Expect an educational answer while
the dialog stays open. Ask a follow-up to check history. Optionally check Include
form parameters, review the data preview, and confirm a second request.

The **Include Simulation Data** checkbox is visible and unchecked by default.
Off sends only the exact query text and the text-only conversation history, without
collecting dashboard data. On reads a fresh snapshot when Send is clicked: all numeric
configured ranges, current dashboard displays, ventilation mode, alarm flags/thresholds,
waveforms, available structured clinical selections and all AI form controls. Defaults,
manual entries, configured ranges and displayed values are labeled separately. The
snapshot timestamp is not a measurement timestamp; inactive displays can retain their
last values. No simulator update is triggered just to collect data.

Every request requires confirmation showing whether data is included and the exact
SDK request payload in Details, including instructions, permitted history and new data.
The confirmed snapshot is sent unchanged; later requests read values again.
Patient names, IDs, notes, CT images and free-text alarm logs are never automatically
attached. Clinical selections are restricted to the form's predefined choices; numeric
patient entries are restricted to recognized simulation/display parameter names.
Only synthetic, non-identifiable text is permitted.
Automatic detection of identifiers in free text is not reliable: review every preview.
The assistant keeps two separate histories, each with up to ten successful pairs:
text-only and simulation-assisted. Data-derived answers and their associated questions
are excluded from text-only requests, including after switching the checkbox off.
Fresh context is attached only to the current simulation-assisted request; past answers
in that lane may reference older data. Text you type yourself is sent as entered;
the application cannot determine whether manually entered text describes clinical data.
Close the dialog to discard its in-memory conversations. No chat is
saved locally. Requests use `store=False`; this does not override provider retention
policies of OpenRouter and its downstream model providers. Responses cannot modify
simulation or ventilator settings. Each confirmation identifies OpenRouter as the
default routing service; if you override the base URL, review that service's policies.

One request runs at a time. Closing waits for completion (45-second SDK timeout,
no automatic retries). Authentication, quota, connection, timeout, empty-output and
other failures are displayed safely; failed turns do not enter API history.
This is an educational/research tool, not validated clinical decision support.
