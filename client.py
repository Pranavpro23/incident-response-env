"""Typed client for the Incident Response Environment."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

try:
    from .models import IncidentAction, IncidentObservation
except ImportError:
    from models import IncidentAction, IncidentObservation  # type: ignore[no-redef]


class IncidentResponseEnv(EnvClient[IncidentAction, IncidentObservation, State]):
    """
    Async WebSocket client for the Incident Response Environment.

    Example (async):
        >>> async with IncidentResponseEnv(base_url="http://localhost:8000") as env:
        ...     result = await env.reset(task="alert_triage")
        ...     obs = result.observation
        ...     result = await env.step(IncidentAction(
        ...         command="check_alerts",
        ...         parameters={},
        ...         reasoning="Check active alerts first",
        ...     ))

    Example (Docker):
        >>> import asyncio
        >>> async def main():
        ...     env = await IncidentResponseEnv.from_docker_image("incident-response-env:latest")
        ...     result = await env.reset(task="alert_triage")
        ...     await env.close()
        >>> asyncio.run(main())
    """

    def _step_payload(self, action: IncidentAction) -> Dict:
        return {
            "command": action.command,
            "parameters": action.parameters,
            "reasoning": action.reasoning,
        }

    def _parse_result(self, payload: Dict) -> StepResult[IncidentObservation]:
        obs_data = payload.get("observation", {})
        observation = IncidentObservation(
            done=payload.get("done", False),
            reward=payload.get("reward"),
            message=obs_data.get("message", ""),
            incident_id=obs_data.get("incident_id", ""),
            task_name=obs_data.get("task_name", ""),
            step_number=obs_data.get("step_number", 0),
            max_steps=obs_data.get("max_steps", 10),
            active_alerts=obs_data.get("active_alerts", []),
            command_output=obs_data.get("command_output", ""),
            available_commands=obs_data.get("available_commands", []),
            task_objective=obs_data.get("task_objective", ""),
            services_summary=obs_data.get("services_summary", {}),
            metadata=obs_data.get("metadata", {}),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
