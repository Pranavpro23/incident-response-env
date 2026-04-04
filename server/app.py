"""
FastAPI application for the Incident Response Environment.

Endpoints (provided by openenv-core):
    POST /reset     — Start a new episode (pass {"task": "alert_triage|root_cause_analysis|incident_remediation"})
    POST /step      — Execute an action
    GET  /state     — Current environment state
    GET  /schema    — Action / observation JSON schemas
    WS   /ws        — WebSocket for persistent sessions

Usage:
    # Direct (development):
    uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

    # Via uv:
    uv run --project . server --port 8000

    # Docker:
    docker build -t incident-response-env . && docker run -p 8000:8000 incident-response-env
"""

from __future__ import annotations

try:
    from openenv.core.env_server.http_server import create_app
except ImportError as exc:
    raise ImportError(
        "openenv-core is required. Install with: pip install openenv-core>=0.2.0"
    ) from exc

try:
    from ..models import IncidentAction, IncidentObservation
    from .incident_environment import IncidentResponseEnvironment
except ImportError:
    from models import IncidentAction, IncidentObservation
    from server.incident_environment import IncidentResponseEnvironment


app = create_app(
    IncidentResponseEnvironment,
    IncidentAction,
    IncidentObservation,
    env_name="incident_response",
    max_concurrent_envs=4,
)


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    """
    Entry point for uv run / direct Python execution.

    Examples:
        uv run --project . server
        uv run --project . server --port 8001
        python -m server.app
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
