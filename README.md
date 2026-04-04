# Incident Response Environment

An **OpenEnv** environment that trains AI agents to act as on-call Site Reliability Engineers (SREs) responding to production incidents. The agent investigates system alerts, diagnoses root causes, executes remediation steps, and resolves incidents — the same workflow that human engineers follow in real production systems.

## Motivation

On-call incident response is one of the highest-stakes, time-pressured tasks in software engineering. Engineers must:
- Triage noisy, multi-service alert storms
- Identify root causes from logs, metrics, and deployment history
- Execute the correct remediation without causing further damage
- Verify recovery before closing an incident

This environment fills a gap in current agent benchmarks: it requires **causal reasoning under ambiguity**, **multi-step planning**, and **tool-use discipline** — all in a domain with immediate real-world value.

---

## Action Space

```python
class IncidentAction(Action):
    command: str            # one of the commands below
    parameters: Dict[str, str]  # command-specific key-value pairs
    reasoning: str          # agent's chain-of-thought (encourages deliberate action)
```

| Command | Parameters | Description |
|---|---|---|
| `check_alerts` | — | List all active alerts |
| `check_service_health` | `service=<name>` | Health status, error rate, latency, CPU/memory |
| `view_logs` | `service=<name>` | Recent log entries for a service |
| `view_metrics` | `service=<name>` | Detailed metrics (error rate, latency, throughput) |
| `check_dependencies` | `service=<name>` | Upstream/downstream dependency graph |
| `view_deployment_history` | `service=<name>` | Recent deployments with version and notes |
| `classify_incident` | `severity=P1\|P2\|P3`, `affected_service=<name>` | **Task 1 terminal** — classify the incident |
| `identify_root_cause` | `cause=<cause>`, `component=<name>` | **Task 2 terminal** — submit root cause |
| `restart_service` | `service=<name>` | Restart a service (task 3) |
| `scale_service` | `service=<name>`, `replicas=<n>` | Scale a service (task 3) |
| `rollback_deployment` | `service=<name>` | Rollback to previous version (task 3) |
| `resolve_incident` | `resolution=<description>` | **Task 3 terminal** — close the incident |

---

## Observation Space

```python
class IncidentObservation(Observation):
    message: str                       # situation summary
    incident_id: str                   # e.g. "INC-20240315-001"
    task_name: str                     # current task
    step_number: int                   # current step
    max_steps: int                     # episode limit
    active_alerts: List[str]           # live alert list
    command_output: str                # output of last command
    available_commands: List[str]      # commands for this task
    task_objective: str                # what the agent must accomplish
    services_summary: Dict[str, str]  # service → HEALTHY/DEGRADED/CRITICAL/CRASHING
    done: bool                         # episode ended
    reward: float                      # step reward
```

---

## Tasks

### Task 1: `alert_triage` — Easy

**Scenario:** Payment service is down at 2:47 AM. Multiple downstream alerts are firing.  
**Objective:** Identify incident severity (P1/P2/P3) and the primary affected service.  
**Max steps:** 8  
**Terminal action:** `classify_incident`

**Grading:**
| Component | Score |
|---|---|
| Correct severity (P1) | +0.45 |
| Correct service (payment-service) | +0.45 |
| Efficiency bonus (≤ 3 investigation steps) | +0.10 |
| Investigation actions (max 4) | +0.05 each |

---

### Task 2: `root_cause_analysis` — Medium

**Scenario:** Orders API is returning 503s. DB is overloaded. A migration ran 25 minutes ago.  
**Objective:** Identify the root cause category and the specific component responsible.  
**Max steps:** 12  
**Terminal action:** `identify_root_cause`

**Grading:**
| Component | Score |
|---|---|
| Exact cause (`missing_database_index`) | +0.50 |
| Partial cause (e.g. `slow_database_query`) | +0.20 |
| Exact component (`orders-db`) | +0.40 |
| Partial component (e.g. `orders-api`) | +0.10 |
| Investigation actions (max 4) | +0.05 each |

---

### Task 3: `incident_remediation` — Hard

**Scenario:** Auth service (v2.4.0, deployed 2h ago) has a memory leak causing OOM crashes. API gateway circuit breaker is open.  
**Objective:** Diagnose, roll back the faulty deployment, verify recovery, resolve.  
**Max steps:** 20  
**Terminal action:** `resolve_incident`

**Grading:**
| Step | Score |
|---|---|
| Investigation actions (max 4 × 0.05) | up to 0.20 |
| `rollback_deployment auth-service` (correct fix) | +0.35 |
| `check_service_health auth-service` after rollback (healthy) | +0.10 |
| `check_service_health api-gateway` after auth recovery (healthy) | +0.10 |
| `resolve_incident` (base) | +0.10 |
| Resolve bonus: auth verified | +0.10 |
| Resolve bonus: gateway verified | +0.10 |

**Wrong actions:** `restart_service` (temporary, +0.05), `scale_service` (no effect, 0), rolling back wrong service (−0.05).

---

## Reward Design

The reward function provides **dense partial-progress signals** across the full trajectory:

- **Investigative actions** each earn `+0.05` (capped at 4 unique commands, max `0.20`) to encourage systematic diagnosis before acting
- **Correct terminal action** delivers the main score (0.40–0.90 depending on correctness)
- **Incorrect remediation** incurs small penalties (`-0.05`) to discourage random actions
- **Verification steps** in task 3 are rewarded separately (`+0.10` each) to encourage confirming recovery
- **Efficiency bonus** in task 1 rewards confident correct classification

This design avoids the sparse reward problem while still requiring the agent to get the diagnosis right.

---

## Baseline Scores

Measured with `Qwen/Qwen2.5-72B-Instruct` via HuggingFace router:

| Task | Score | Notes |
|---|---|---|
| `alert_triage` | **1.000** | Correctly classified P1 + payment-service in 2 steps |
| `root_cause_analysis` | **0.600** | Correct component (orders-db), partial cause match |
| `incident_remediation` | **0.200** | Diagnosed correctly but exhausted steps before remediating |

Task 3 is intentionally designed to challenge frontier models — it requires the agent to stop re-investigating and commit to a `rollback_deployment` action. Models that loop on investigation without acting will score low, which is expected behaviour for a *hard* task.

---

## Setup

### Prerequisites

- Python 3.10+
- Docker
- `pip install openenv-core>=0.2.3`

### Run locally (without Docker)

```bash
cd incident_response_env
pip install -r requirements.txt
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

### Run with Docker

```bash
docker build -t incident-response-env .
docker run -p 8000:8000 incident-response-env
```

### Run inference script

```bash
# Against a running local server:
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="your-token"
export ENV_BASE_URL="http://localhost:8000"
python inference.py

# Against a Docker image:
export LOCAL_IMAGE_NAME="incident-response-env:latest"
python inference.py
```

### Validate

```bash
openenv validate
```

---

## Project Structure

```
incident_response_env/
├── models.py               # IncidentAction, IncidentObservation, IncidentState
├── scenarios.py            # Scenario data for all 3 tasks
├── client.py               # IncidentResponseEnv (typed WebSocket client)
├── server/
│   ├── app.py              # FastAPI app (openenv create_app)
│   └── incident_environment.py  # Environment logic, reward & grader
├── inference.py            # Baseline inference script
├── openenv.yaml            # OpenEnv spec metadata
├── pyproject.toml          # Project dependencies & entry points
├── requirements.txt
├── Dockerfile
└── README.md
```
