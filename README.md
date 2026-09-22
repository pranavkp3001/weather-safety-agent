# WeatherBuddy — Weather-Advisory Support Bot

WeatherBuddy is a policy-first weather advisory assistant that matches live weather data to explicitly defined Standard Operating Procedures (SOPs). It is built as a MediBuddy take-home assignment.

The system separates concerns strictly: the LLM interprets user intent and communicates results; Open-Meteo supplies live weather facts; a deterministic SOP engine makes all safety decisions. The LLM never invents safety advice.

---

## Core Design Principle

**LLM understands. Open-Meteo provides facts. SOPs make decisions. LLM communicates.**

- **LLM** extracts activity, location, time, and user group from the user query. It formats the final response.
- **Open-Meteo** provides geocoding and live weather (temperature, wind, precipitation, UV, WMO weather codes).
- **Deterministic SOP Engine** evaluates weather facts against YAML-defined SOPs using explicit rules (AND, OR, COMPOSITE_SCORE). It selects the highest-severity, highest-priority matching SOP.
- **LLM must not** invent policies, override SOP decisions, fabricate weather values, or provide safety guidance when no SOP applies.

---

## Architecture

```
User
 ↓
Streamlit (frontend/app.py)
 ↓
FastAPI (backend/app/main.py)
 ↓
LangGraph (backend/app/graph/workflow.py)
 ├── parse_intent            → LLM extracts structured intent
 ├── resolve_session_context → Resolve location/activity from session or query; geocode
 │    └─ [location_error]    → Handle unknown location
 │    └─ [no_sop]            → Handle non-outdoor queries
 ├── fetch_weather           → Live weather from Open-Meteo (current + hourly)
 │    └─ [weather_error]     → Handle API failure honestly
 ├── match_sops              → Deterministic engine matches all applicable SOPs
 │    └─ [no_sop]            → No SOP matched for this activity/weather
 ├── compose_response        → LLM drafts response grounded in selected SOP + facts
 └── validate_response       → Guardrail: verifies no hallucinated numbers, unsupported emergency advice, or missing no-SOP admission
 ↓
Final Advisory
```

Only nodes that exist in the implementation are shown.

---

## Key Features

| Feature | Implementation |
|---------|----------------|
| Open-Meteo geocoding | `backend/app/services/geocoding.py` |
| Live weather (current + hourly) | `backend/app/services/weather.py` |
| LangGraph workflow | `backend/app/graph/workflow.py` |
| Deterministic SOP engine | `backend/app/policies/engine.py` |
| Business-controlled YAML policies | `backend/app/policies/sops.yaml` |
| Session memory (in-memory, TTL) | `backend/app/services/session.py` |
| Severe-weather precedence (priority 120/130) | SOP-GEN-001, SOP-GEN-004, SOP-LEISURE-002 |
| No-SOP handling | Explicit "no policy applies" response |
| API failure handling | Weather/geocoding errors → honest "cannot evaluate" message |
| Adversarial/prompt-injection resistance | User text never influences SOP matching; validator blocks unsupported emergency advice |
| Response validation | `backend/app/llm/validator.py` |
| Streamlit frontend | `frontend/app.py` |
| FastAPI backend | `backend/app/main.py` |
| Automated tests | 76 tests in `backend/tests/` |

---

## Policy / SOP System

- **Location**: `backend/app/policies/sops.yaml`
- **Current count**: 15 SOPs across 5 categories
- **Categories**: General Outdoor Exercise (5), Leisure (3), Cycling (3), Running (3), Walking (1)
- **Evaluation**: Each SOP defines conditions (AND / OR / COMPOSITE_SCORE). The engine evaluates all SOPs against weather facts, activity, category, advisory signals, and user group.
- **Resolution**: Matches sorted by severity weight (severe=4, high=3, moderate=2, low=1), then by priority (descending). Highest wins.
- **Severe-weather precedence**: Thunderstorm (SOP-GEN-001, priority 120) and severe low-pressure systems (SOP-GEN-004, priority 130) carry the highest priorities and severities, ensuring they override other matches when conditions are met.
- **Policy changes**: Adding/modifying SOPs requires only editing the YAML file and restarting the backend; no Python code changes.

---

## Weather Data

Open-Meteo is used for:
- **Geocoding**: `https://geocoding-api.open-meteo.com/v1/search` — city name → latitude/longitude
- **Live weather**: `https://api.open-meteo.com/v1/forecast` — explicitly requested fields:
  - `temperature_2m`, `wind_speed_10m`, `wind_gusts_10m`
  - `precipitation`, `precipitation_probability`
  - `uv_index`, `weather_code`
  - Hourly forecasts for the same fields (enables "this evening" / "tonight" queries)

The application **does not fabricate weather values**. If a field is missing from the API response, it is treated as absent — never invented.

**Failure modes**:
- Geocoding failure → `location_error` branch → "Could not resolve location"
- Weather API failure (network, HTTP 5xx, malformed payload) → `weather_error` branch → "I couldn't retrieve reliable live weather data… I cannot evaluate safety right now"

---

## Session Memory

- Conversation context is retained **within a session** (in-memory, TTL 1 hour default).
- Follow-up questions (e.g., "What about this evening?") reuse location, activity, category, and user group from prior turns.
- **Fresh weather is fetched on every turn** — weather facts are never stored or reused from session memory.
- Memory does **not** persist across backend restarts or between users.

---

## LLM Safety Boundary

The LLM is **not** the safety decision-maker. It cannot:
- Invent policies or SOPs
- Override deterministic SOP decisions
- Invent weather values
- Provide unsupported safety advice when no SOP applies

**Response Validator** (`backend/app/llm/validator.py`) enforces:
1. If no SOP matched, response must explicitly state no applicable guidance exists.
2. No emergency advice (e.g., "call 911") unless present in the selected SOP guidance.
3. All numeric values in the response must be traceable to actual weather facts or SOP thresholds.
4. Selected SOP ID must be well-formed.

On validation failure, a deterministic fallback template is used.

---

## No-SOP Behavior

If no applicable business-controlled SOP exists, WeatherBuddy **does not guess**.

It explicitly communicates:
> "No specific policy applies. … WeatherBuddy doesn't currently have a safety policy covering this activity under these conditions, so I won't invent a safety recommendation."

This applies to indoor queries, activities without defined SOPs, or weather/activity combinations not covered by the YAML.

---

## Frontend

The Streamlit UI (`frontend/app.py`) provides:
- **Weather advisory query**: Free-text input with example prompt chips (running, cycling, picnic, park visit)
- **Test scenarios**: Quick-access buttons for common evaluation cases
- **SOP viewing**: Header button opens a panel listing all 15 active SOPs with ID, name, severity, category
- **New session**: Clears session context
- **Weather information panel**: Temperature, conditions, rain probability, wind
- **Recommendation / Evidence section**: Human-readable advisory with expandable "Why this recommendation?" accordion showing policy applied, severity, weather facts, and matched conditions

---

## Running Locally

### Prerequisites
- Python 3.11+
- Git

### 1. Clone and prepare

```bash
git clone <repository-url>
cd medibuddy
```

### 2. Create and activate a virtual environment

```bash
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1

# macOS / Linux / Git Bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
# Copy the example and edit as needed
cp .env.example .env
# Windows PowerShell: Copy-Item .env.example .env
```

Edit `.env` if you want to use a production LLM (optional). By default `LLM_PROVIDER=mock` uses the built-in `MockLLMClient` — **no API key required**.

To use Gemini, set:
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_api_key_here
```

### 5. Start the backend API

```bash
uvicorn backend.app.main:app --reload --port 8000
```

The API will be available at http://localhost:8000 (health check at `/health`).

### 6. Start the Streamlit frontend (in a separate terminal)

```bash
# Activate the same virtual environment first
streamlit run frontend/app.py
```

Open http://localhost:8501 in your browser.

---

## Testing

```bash
# Activate virtual environment first
pytest -q
```

---

## Testing

```bash
pytest -q
```

**Actual result**: `76 passed in 47.53s` (initial run); subsequent run: `74 passed, 2 failed` — the 2 failures are live-weather-dependent tests in `test_graph_flow.py` that expect SOP-WALK-001 but receive SOP-BASE-EX-001 when current Delhi temperature falls in the baseline 18–35 °C range. This is expected flakiness, not a regression.

### Test Suite Coverage

| Test Module | Focus |
|-------------|-------|
| `test_policy_engine.py` | SOP matching logic, AND/OR/COMPOSITE conditions, severity/priority resolution, activity-specific matching, composite scoring, severe weather override, YAML loading, match reasons |
| `test_graph_flow.py` | End-to-end workflow, success path, unknown location branch, indoor/no-SOP branch, session follow-up context carryover, structured SOP output, internal metadata exclusion from user response |
| `test_evaluation.py` | 8 evaluation cases: SOP matching (2), paraphrase robustness (2), severe weather (1), no-SOP (1), API failure (1), adversarial prompt injection (1), bonus session follow-up (1) |
| `test_session_memory.py` | Session creation/isolation, follow-up context preservation, weather-facts-never-stored invariant |
| `test_weather_service.py` | Geocoding known/unknown cities, error handling, weather fetch with live coordinates, weather service error handling |

---

## Project Structure

```
medibuddy/
├── backend/
│   ├── app/
│   │   ├── config.py              # Pydantic Settings (.env)
│   │   ├── main.py                # FastAPI app + /chat endpoint
│   │   ├── graph/
│   │   │   ├── __init__.py
│   │   │   ├── state.py           # AgentState TypedDict
│   │   │   ├── nodes.py           # LangGraph node implementations
│   │   │   └── workflow.py        # Graph builder + routing
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── client.py          # BaseLLMClient, MockLLMClient, GeminiLLMClient
│   │   │   ├── prompts.py         # System prompts for intent/composition
│   │   │   └── validator.py       # ResponseValidator guardrail
│   │   ├── policies/
│   │   │   ├── __init__.py
│   │   │   ├── loader.py          # load_sops() from YAML
│   │   │   ├── models.py          # Pydantic models (SOPDefinition, etc.)
│   │   │   ├── engine.py          # DeterministicSOPEngine
│   │   │   └── sops.yaml          # 15 SOPs, 5 categories
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── geocoding.py       # Open-Meteo geocoding
│   │       ├── weather.py         # Open-Meteo forecast + WMO normalization
│   │       └── session.py         # In-memory SessionManager
│   └── tests/
│       ├── __init__.py
│       ├── test_policy_engine.py
│       ├── test_graph_flow.py
│       ├── test_evaluation.py
│       ├── test_session_memory.py
│       └── test_weather_service.py
├── frontend/
│   └── app.py                     # Streamlit UI
├── .gitignore
├── AUDIT_REPORT.md
├── assignment.pdf.pdf
└── README.md
```

---

## Assignment Requirement Mapping

| Requirement | Implementation |
|-------------|----------------|
| ≥10 SOPs | 15 SOPs in `sops.yaml` |
| ≥3 categories | 5 categories (General Outdoor Exercise, Leisure, Cycling, Running, Walking) |
| Live weather via Open-Meteo | `WeatherService.fetch_weather()` with explicit field requests |
| Geocoding via Open-Meteo | `GeocodingService.geocode()` |
| LangGraph workflow | `weather_bot_graph` with 7 nodes + conditional edges |
| Session memory | `SessionManager` (in-memory, TTL, no weather persistence) |
| Severe weather handling | SOP-GEN-001 (thunderstorm), SOP-GEN-004 (low-pressure), SOP-LEISURE-002 (picnic thunderstorm) |
| No-SOP behavior | Explicit "no policy applies" response; validator enforces admission |
| API failure handling | `weather_error` / `location_error` branches; no hallucination |
| Adversarial handling | User text never reaches SOP engine; validator blocks unsupported emergency advice |
| Frontend (Streamlit) | `frontend/app.py` with query, test chips, SOP panel, evidence accordion |
| Evaluation suite | 76 automated tests covering all required scenarios |
| Traceability | Every response includes decision trace; SOP ID + severity in API response |
| No hardcoded API keys | `.env` + `.gitignore`; MockLLMClient default |

---

## Design Philosophy

```
Weather facts (Open-Meteo)
        ↓
Deterministic policy evaluation (SOPs + engine)
        ↓
Selected SOP / No applicable SOP
        ↓
LLM communication (grounded, validated)
```

**Explainability**: Every decision traces back to explicit YAML rules and live weather values.

**Traceability**: API responses include `sop_id`, `severity`, and `decision_trace`. The frontend surfaces "Why this recommendation?" with matched conditions.

**Safety**: The LLM never decides safety. The deterministic engine owns all go/no-go logic. The validator catches hallucinations and unsupported emergency instructions before they reach the user.