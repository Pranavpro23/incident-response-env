"""
Data models for the Incident Response Environment.

An AI agent acts as an on-call SRE, investigating and resolving production incidents.
"""

from typing import Dict, List, Optional

from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field


class IncidentAction(Action):
    """Action taken by the SRE agent during incident response."""

    command: str = Field(
        ...,
        description=(
            "Command to execute. One of: check_alerts, check_service_health, "
            "view_logs, view_metrics, check_dependencies, view_deployment_history, "
            "classify_incident, identify_root_cause, restart_service, "
            "scale_service, rollback_deployment, resolve_incident"
        ),
    )
    parameters: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Command parameters. Examples: "
            "{'service': 'auth-service'} for health/log/metric commands; "
            "{'severity': 'P1', 'affected_service': 'payment-service'} for classify_incident; "
            "{'cause': 'missing_database_index', 'component': 'orders-db'} for identify_root_cause; "
            "{'resolution': 'description'} for resolve_incident"
        ),
    )
    reasoning: str = Field(
        default="",
        description="Agent's reasoning for choosing this action (chain-of-thought)",
    )


class IncidentObservation(Observation):
    """Observation returned to the SRE agent after each action."""

    message: str = Field(
        default="",
        description="Status message describing the current incident situation",
    )
    incident_id: str = Field(
        default="",
        description="Unique identifier for the current incident",
    )
    task_name: str = Field(
        default="",
        description="Name of the current task (alert_triage / root_cause_analysis / incident_remediation)",
    )
    step_number: int = Field(
        default=0,
        description="Current step number in the episode",
    )
    max_steps: int = Field(
        default=10,
        description="Maximum steps allowed for this task",
    )
    active_alerts: List[str] = Field(
        default_factory=list,
        description="List of currently active alerts",
    )
    command_output: str = Field(
        default="",
        description="Output from the last executed command",
    )
    available_commands: List[str] = Field(
        default_factory=list,
        description="Commands available for the current task",
    )
    task_objective: str = Field(
        default="",
        description="Description of what the agent needs to accomplish",
    )
    services_summary: Dict[str, str] = Field(
        default_factory=dict,
        description="High-level health status of all services (HEALTHY/DEGRADED/CRITICAL/CRASHING)",
    )


class IncidentState(State):
    """Internal state of the Incident Response environment."""

    task_name: str = Field(default="", description="Current task name")
    incident_id: str = Field(default="", description="Incident identifier")
    services_state: Dict[str, Dict] = Field(
        default_factory=dict,
        description="Detailed state of all services",
    )
    actions_history: List[str] = Field(
        default_factory=list,
        description="History of actions taken this episode",
    )
    investigation_actions: List[str] = Field(
        default_factory=list,
        description="Unique investigative commands executed",
    )
    remediation_steps: List[str] = Field(
        default_factory=list,
        description="Remediation steps completed (task 3)",
    )
    resolved: bool = Field(default=False, description="Whether the incident is resolved")
    cumulative_reward: float = Field(
        default=0.0, description="Total reward accumulated this episode"
    )
    ground_truth: Dict[str, str] = Field(
        default_factory=dict,
        description="Ground truth answers for grading",
    )
    max_steps: int = Field(default=10, description="Max steps for current task")
