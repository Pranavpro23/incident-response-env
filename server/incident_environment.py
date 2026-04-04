"""
Incident Response Environment — core logic.

The SRE agent receives alerts, investigates services, and takes remediation
actions across three tasks of increasing difficulty.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import IncidentAction, IncidentObservation, IncidentState
    from ..scenarios import SCENARIOS
except ImportError:
    from models import IncidentAction, IncidentObservation, IncidentState
    from scenarios import SCENARIOS


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TASK_COMMANDS: Dict[str, List[str]] = {
    "alert_triage": [
        "check_alerts", "check_service_health", "view_logs",
        "view_metrics", "check_dependencies", "view_deployment_history",
        "classify_incident",
    ],
    "root_cause_analysis": [
        "check_alerts", "check_service_health", "view_logs",
        "view_metrics", "check_dependencies", "view_deployment_history",
        "identify_root_cause",
    ],
    "incident_remediation": [
        "check_alerts", "check_service_health", "view_logs",
        "view_metrics", "check_dependencies", "view_deployment_history",
        "restart_service", "scale_service", "rollback_deployment",
        "resolve_incident",
    ],
}


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class IncidentResponseEnvironment(Environment):
    """
    OpenEnv environment simulating SRE on-call incident response.

    Tasks
    -----
    alert_triage        (easy)   — classify severity + primary affected service
    root_cause_analysis (medium) — identify root cause + component
    incident_remediation (hard)  — multi-step investigate → remediate → verify → resolve

    Reward shaping
    --------------
    Each investigative command earns +0.05 (capped at 4 unique commands) to
    encourage systematic diagnosis before acting. The main reward arrives at
    the terminal action, with partial credit for partial correctness.
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self) -> None:
        super().__init__()
        self._task_name: str = "alert_triage"
        self._scenario: Dict[str, Any] = {}
        self._services: Dict[str, Dict] = {}
        self._inv_actions_done: set = set()
        self._remediation_steps: List[str] = []
        self._actions_history: List[str] = []
        self._cumulative_reward: float = 0.0
        self._resolved: bool = False
        self._episode_id: str = str(uuid4())
        self._step_count: int = 0
        self._done: bool = False
        # Remediation tracking (task 3)
        self._auth_rolled_back: bool = False
        self._auth_verified_healthy: bool = False
        self._gw_verified_healthy: bool = False

    # ------------------------------------------------------------------
    # OpenEnv API
    # ------------------------------------------------------------------

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        task: str = "alert_triage",
        **kwargs: Any,
    ) -> IncidentObservation:
        """Reset to a new episode for the given task."""
        if task not in SCENARIOS:
            task = "alert_triage"

        self._task_name = task
        self._scenario = SCENARIOS[task]
        self._services = deepcopy(self._scenario["services"])
        self._inv_actions_done = set()
        self._remediation_steps = []
        self._actions_history = []
        self._cumulative_reward = 0.0
        self._resolved = False
        self._done = False
        self._auth_rolled_back = False
        self._auth_verified_healthy = False
        self._gw_verified_healthy = False
        self._episode_id = episode_id or str(uuid4())
        self._step_count = 0

        alerts = self._scenario["alerts"]
        return IncidentObservation(
            done=False,
            reward=0.0,
            message=(
                f"=== INCIDENT ALERT: {self._scenario['title']} ===\n"
                f"Incident ID: {self._scenario['incident_id']}\n\n"
                f"{self._scenario['description']}\n\n"
                f"OBJECTIVE: {self._scenario['task_objective']}"
            ),
            incident_id=self._scenario["incident_id"],
            task_name=task,
            step_number=0,
            max_steps=self._scenario["max_steps"],
            active_alerts=alerts,
            command_output="",
            available_commands=_TASK_COMMANDS[task],
            task_objective=self._scenario["task_objective"],
            services_summary={s: d["health"] for s, d in self._services.items()},
        )

    def step(
        self,
        action: IncidentAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> IncidentObservation:
        """Execute a command and return the resulting observation."""
        if self._done:
            return self._make_obs(
                "Episode already finished. Call reset() to start a new episode.",
                reward=0.0,
                done=True,
            )

        self._step_count += 1
        cmd = action.command.strip().lower()
        params = {k.lower(): v for k, v in action.parameters.items()}
        self._actions_history.append(
            f"step={self._step_count} cmd={cmd} params={params}"
        )

        output, reward, done = self._dispatch(cmd, params)

        self._cumulative_reward += reward
        if done:
            self._done = True

        max_steps = self._scenario["max_steps"]
        if self._step_count >= max_steps and not done:
            done = True
            self._done = True
            output += f"\n\n[TIMEOUT] Maximum steps ({max_steps}) reached."

        return self._make_obs(output, reward=reward, done=done)

    @property
    def state(self) -> IncidentState:
        return IncidentState(
            episode_id=self._episode_id,
            step_count=self._step_count,
            task_name=self._task_name,
            incident_id=self._scenario.get("incident_id", ""),
            services_state=deepcopy(self._services),
            actions_history=list(self._actions_history),
            investigation_actions=list(self._inv_actions_done),
            remediation_steps=list(self._remediation_steps),
            resolved=self._resolved,
            cumulative_reward=self._cumulative_reward,
            ground_truth=dict(self._scenario.get("ground_truth", {})),
            max_steps=self._scenario.get("max_steps", 10),
        )

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def _dispatch(
        self, cmd: str, params: Dict[str, str]
    ) -> tuple[str, float, bool]:
        """Route a command to its handler. Returns (output, reward, done)."""
        handlers = {
            "check_alerts": self._cmd_check_alerts,
            "check_service_health": self._cmd_service_health,
            "view_logs": self._cmd_view_logs,
            "view_metrics": self._cmd_view_metrics,
            "check_dependencies": self._cmd_dependencies,
            "view_deployment_history": self._cmd_deployment_history,
            "classify_incident": self._cmd_classify_incident,
            "identify_root_cause": self._cmd_identify_root_cause,
            "restart_service": self._cmd_restart_service,
            "scale_service": self._cmd_scale_service,
            "rollback_deployment": self._cmd_rollback_deployment,
            "resolve_incident": self._cmd_resolve_incident,
        }
        if cmd not in handlers:
            avail = ", ".join(_TASK_COMMANDS[self._task_name])
            return (
                f"Unknown command: '{cmd}'. Available: {avail}",
                0.0,
                False,
            )
        return handlers[cmd](params)

    # ------------------------------------------------------------------
    # Investigative reward helper
    # ------------------------------------------------------------------

    def _inv_reward(self, key: str) -> float:
        """Return 0.05 for each unique investigative action, capped at 4 (0.20 total)."""
        if key in self._inv_actions_done:
            return 0.0
        if len(self._inv_actions_done) >= 4:
            return 0.0
        self._inv_actions_done.add(key)
        return 0.05

    # ------------------------------------------------------------------
    # Investigative commands (all tasks)
    # ------------------------------------------------------------------

    def _cmd_check_alerts(self, _params: Dict) -> tuple[str, float, bool]:
        alerts = self._scenario["alerts"]
        out = "=== ACTIVE ALERTS ===\n" + "\n".join(f"  {a}" for a in alerts)
        return out, self._inv_reward("check_alerts"), False

    def _cmd_service_health(self, params: Dict) -> tuple[str, float, bool]:
        svc = params.get("service", "")
        if svc not in self._services:
            avail = ", ".join(self._services.keys())
            return f"Unknown service '{svc}'. Available: {avail}", 0.0, False

        s = self._services[svc]
        out = (
            f"=== HEALTH: {svc} ===\n"
            f"  Status:       {s['health']}\n"
            f"  Error rate:   {s['error_rate_pct']:.1f}%\n"
            f"  Latency P99:  {s['latency_p99_ms']}ms\n"
            f"  CPU:          {s['cpu_pct']}%\n"
            f"  Memory:       {s['mem_pct']}%\n"
            f"  Instances:    {s['instances']}\n"
            f"  Version:      {s['version']}"
        )

        reward = self._inv_reward(f"health:{svc}")

        # Task 3: post-rollback verification rewards
        if self._task_name == "incident_remediation" and self._auth_rolled_back:
            gt = self._scenario["ground_truth"]
            correct_svc = gt["correct_service"]

            if svc == correct_svc and not self._auth_verified_healthy:
                if s["health"] == "HEALTHY":
                    self._auth_verified_healthy = True
                    # Trigger cascade recovery of api-gateway
                    recovery = self._scenario["recovery"].get("after_auth_healthy", {})
                    for rsvc, updates in recovery.items():
                        if rsvc in self._services:
                            self._services[rsvc].update(updates)
                    reward = max(reward, 0.10)
                    out += (
                        "\n  VERIFICATION: auth-service fully recovered. "
                        "API gateway should recover soon."
                    )

            elif (
                svc == "api-gateway"
                and self._auth_verified_healthy
                and not self._gw_verified_healthy
            ):
                if self._services["api-gateway"]["health"] == "HEALTHY":
                    self._gw_verified_healthy = True
                    reward = max(reward, 0.10)
                    out += (
                        "\n  VERIFICATION: api-gateway circuit breaker reset. "
                        "All /auth/* paths operational."
                    )

        return out, reward, False

    def _cmd_view_logs(self, params: Dict) -> tuple[str, float, bool]:
        svc = params.get("service", "")
        if svc not in self._services:
            avail = ", ".join(self._services.keys())
            return f"Unknown service '{svc}'. Available: {avail}", 0.0, False
        logs = self._scenario["logs"].get(svc, ["[No logs available]"])
        out = f"=== LOGS: {svc} (last {len(logs)} entries) ===\n"
        out += "\n".join(f"  {line}" for line in logs)
        return out, self._inv_reward(f"logs:{svc}"), False

    def _cmd_view_metrics(self, params: Dict) -> tuple[str, float, bool]:
        svc = params.get("service", "")
        if svc not in self._services:
            avail = ", ".join(self._services.keys())
            return f"Unknown service '{svc}'. Available: {avail}", 0.0, False
        metrics = self._scenario["metrics"].get(svc, {})
        out = f"=== METRICS: {svc} ===\n"
        out += "\n".join(f"  {k}: {v}" for k, v in metrics.items())
        return out, self._inv_reward(f"metrics:{svc}"), False

    def _cmd_dependencies(self, params: Dict) -> tuple[str, float, bool]:
        svc = params.get("service", "")
        deps = self._scenario.get("dependencies", {})
        if svc not in deps and svc not in self._services:
            avail = ", ".join(self._services.keys())
            return f"Unknown service '{svc}'. Available: {avail}", 0.0, False
        upstream = deps.get(svc, [])
        downstream = [s for s, d in deps.items() if svc in d]
        out = (
            f"=== DEPENDENCIES: {svc} ===\n"
            f"  Depends on:       {', '.join(upstream) if upstream else 'none'}\n"
            f"  Depended on by:   {', '.join(downstream) if downstream else 'none'}\n"
        )
        if upstream:
            out += "  Upstream health:\n"
            for dep in upstream:
                h = self._services.get(dep, {}).get("health", "UNKNOWN")
                out += f"    {dep}: {h}\n"
        return out, self._inv_reward(f"deps:{svc}"), False

    def _cmd_deployment_history(self, params: Dict) -> tuple[str, float, bool]:
        svc = params.get("service", "")
        history = self._scenario.get("deployment_history", {})
        if svc not in history:
            if svc not in self._services:
                avail = ", ".join(self._services.keys())
                return f"Unknown service '{svc}'. Available: {avail}", 0.0, False
            return f"No deployment history found for '{svc}'.", 0.0, False
        entries = history[svc]
        out = f"=== DEPLOYMENT HISTORY: {svc} ===\n"
        for e in entries:
            desc = e.get("description", "")
            out += (
                f"  [{e['status'].upper()}] v{e['version']} — "
                f"deployed {e['deployed_at']} by {e['deployed_by']}"
            )
            if desc:
                out += f"\n    Note: {desc}"
            out += "\n"
        return out, self._inv_reward(f"deploy:{svc}"), False

    # ------------------------------------------------------------------
    # Task 1: classify_incident
    # ------------------------------------------------------------------

    def _cmd_classify_incident(self, params: Dict) -> tuple[str, float, bool]:
        if self._task_name != "alert_triage":
            return (
                "classify_incident is only available in the alert_triage task.",
                0.0, False,
            )

        severity = params.get("severity", "").upper()
        service = params.get("affected_service", "").lower()
        gt = self._scenario["ground_truth"]
        gt_severity = gt["severity"].upper()
        gt_service = gt["affected_service"].lower()

        severity_ok = severity == gt_severity
        service_ok = service == gt_service

        score = 0.0
        if severity_ok:
            score += 0.45
        elif severity in {"P1", "P2"} and gt_severity in {"P1", "P2"}:
            score += 0.20   # adjacent P-level partial credit

        if service_ok:
            score += 0.45

        # Efficiency bonus: correct classification with ≤ 3 investigation steps
        if severity_ok and service_ok and len(self._inv_actions_done) <= 3:
            score = min(score + 0.10, 1.0)

        score = min(score, 1.0)
        msg = self._grade_message(
            "classify_incident",
            {
                "severity": f"{severity} (correct: {gt_severity}) {'✓' if severity_ok else '✗'}",
                "affected_service": f"{service} (correct: {gt_service}) {'✓' if service_ok else '✗'}",
            },
            score,
        )
        return msg, score, True

    # ------------------------------------------------------------------
    # Task 2: identify_root_cause
    # ------------------------------------------------------------------

    def _cmd_identify_root_cause(self, params: Dict) -> tuple[str, float, bool]:
        if self._task_name != "root_cause_analysis":
            return (
                "identify_root_cause is only available in the root_cause_analysis task.",
                0.0, False,
            )

        cause = params.get("cause", "").lower().replace(" ", "_")
        component = params.get("component", "").lower()
        gt = self._scenario["ground_truth"]
        gt_cause = gt["cause"].lower()
        gt_component = gt["component"].lower()
        partial_causes = [c.lower() for c in gt.get("partial_causes", [])]
        partial_components = [c.lower() for c in gt.get("partial_components", [])]

        cause_ok = cause == gt_cause
        component_ok = component == gt_component

        score = 0.0
        if cause_ok:
            score += 0.50
        elif cause in partial_causes:
            score += 0.20

        if component_ok:
            score += 0.40
        elif component in partial_components:
            score += 0.10

        score = min(score, 1.0)
        msg = self._grade_message(
            "identify_root_cause",
            {
                "cause": f"{cause} (correct: {gt_cause}) {'✓' if cause_ok else ('~' if cause in partial_causes else '✗')}",
                "component": f"{component} (correct: {gt_component}) {'✓' if component_ok else ('~' if component in partial_components else '✗')}",
            },
            score,
        )
        return msg, score, True

    # ------------------------------------------------------------------
    # Task 3: remediation actions
    # ------------------------------------------------------------------

    def _cmd_restart_service(self, params: Dict) -> tuple[str, float, bool]:
        if self._task_name != "incident_remediation":
            return "restart_service is only available in the incident_remediation task.", 0.0, False

        svc = params.get("service", "")
        if svc not in self._services:
            avail = ", ".join(self._services.keys())
            return f"Unknown service '{svc}'. Available: {avail}", 0.0, False

        gt = self._scenario["ground_truth"]
        if svc == gt["correct_service"]:
            step_key = f"restart:{svc}"
            if step_key not in self._remediation_steps:
                self._remediation_steps.append(step_key)
                self._services[svc]["health"] = "DEGRADED"  # temporary improvement
                out = (
                    f"=== RESTARTING {svc} ===\n"
                    f"  {svc} is restarting...\n"
                    f"  Status: DEGRADED (recovering)\n"
                    f"  WARNING: Root cause (memory leak in v{self._services[svc]['version']}) "
                    f"not fixed — will likely OOM again.\n"
                    f"  Consider rollback_deployment for a permanent fix."
                )
                return out, 0.05, False
            return (
                f"{svc} already restarted — memory leak continues. Use rollback_deployment.",
                0.0, False,
            )
        return (
            f"Restarted {svc}. No improvement — this service is not the root cause.",
            -0.05, False,
        )

    def _cmd_scale_service(self, params: Dict) -> tuple[str, float, bool]:
        if self._task_name != "incident_remediation":
            return "scale_service is only available in the incident_remediation task.", 0.0, False

        svc = params.get("service", "")
        replicas = params.get("replicas", "3")
        if svc not in self._services:
            avail = ", ".join(self._services.keys())
            return f"Unknown service '{svc}'. Available: {avail}", 0.0, False

        out = (
            f"=== SCALING {svc} to {replicas} replicas ===\n"
            f"  Done. Note: scaling a service with a memory leak accelerates OOM failures."
        )
        return out, 0.0, False

    def _cmd_rollback_deployment(self, params: Dict) -> tuple[str, float, bool]:
        if self._task_name != "incident_remediation":
            return "rollback_deployment is only available in the incident_remediation task.", 0.0, False

        svc = params.get("service", "")
        if svc not in self._services:
            avail = ", ".join(self._services.keys())
            return f"Unknown service '{svc}'. Available: {avail}", 0.0, False

        gt = self._scenario["ground_truth"]

        if svc == gt["correct_service"] and not self._auth_rolled_back:
            prev_version = self._services[svc]["prev_version"]
            current_version = self._services[svc]["version"]
            # Apply service recovery
            recovery = self._scenario["recovery"]["after_rollback_auth"]
            for rsvc, updates in recovery.items():
                if rsvc in self._services:
                    self._services[rsvc].update(updates)

            self._auth_rolled_back = True
            step_key = f"rollback:{svc}"
            if step_key not in self._remediation_steps:
                self._remediation_steps.append(step_key)

            out = (
                f"=== ROLLBACK: {svc} ===\n"
                f"  Rolling back {svc}: v{current_version} → v{prev_version}...\n"
                f"  Deployment complete. v{prev_version} is now active.\n"
                f"  Memory usage: dropping 96% → 35% (no leak in v{prev_version})\n"
                f"  Status: HEALTHY\n"
                f"  IMPORTANT: Verify service health and downstream recovery before resolving."
            )
            return out, 0.35, False

        if svc == gt["correct_service"] and self._auth_rolled_back:
            return (
                f"{svc} already rolled back. Verify with check_service_health.",
                0.0, False,
            )

        return (
            f"Rolled back {svc} — no improvement. This service is not the root cause.",
            -0.05, False,
        )

    def _cmd_resolve_incident(self, params: Dict) -> tuple[str, float, bool]:
        if self._task_name != "incident_remediation":
            return "resolve_incident is only available in the incident_remediation task.", 0.0, False

        if not self._auth_rolled_back:
            return (
                "Cannot resolve: auth-service still runs the faulty version. "
                "Root cause has not been addressed.",
                0.0, False,
            )

        resolution = params.get("resolution", "No resolution provided")
        gt = self._scenario["ground_truth"]
        correct_svc = gt["correct_service"]

        resolve_reward = 0.10  # base for reaching resolution
        if self._auth_verified_healthy:
            resolve_reward += 0.10
        if self._gw_verified_healthy:
            resolve_reward += 0.10

        self._resolved = True
        out = (
            f"=== INCIDENT RESOLVED ===\n"
            f"  Incident ID:   {self._scenario['incident_id']}\n"
            f"  Resolution:    {resolution}\n"
            f"  {correct_svc}: {self._services[correct_svc]['health']}\n"
            f"  api-gateway:   {self._services.get('api-gateway', {}).get('health', 'UNKNOWN')}\n"
            f"  Steps taken:   {self._step_count}\n"
            f"  Incident closed."
        )
        return out, resolve_reward, True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_obs(
        self,
        command_output: str,
        reward: float,
        done: bool,
    ) -> IncidentObservation:
        alerts = list(self._scenario.get("alerts", []))
        if self._auth_rolled_back:
            alerts = [
                a for a in alerts
                if not ("auth-service" in a.lower() and "oom" in a.lower())
            ]

        return IncidentObservation(
            done=done,
            reward=reward,
            message=(
                f"Step {self._step_count}/{self._scenario['max_steps']} — "
                f"{'RESOLVED' if self._resolved else 'IN PROGRESS'}"
            ),
            incident_id=self._scenario.get("incident_id", ""),
            task_name=self._task_name,
            step_number=self._step_count,
            max_steps=self._scenario["max_steps"],
            active_alerts=alerts,
            command_output=command_output,
            available_commands=_TASK_COMMANDS[self._task_name],
            task_objective=self._scenario["task_objective"],
            services_summary={
                svc: data["health"] for svc, data in self._services.items()
            },
        )

    @staticmethod
    def _grade_message(cmd: str, results: Dict[str, str], score: float) -> str:
        lines = [f"=== GRADED: {cmd} | score: {score:.2f}/1.00 ==="]
        for k, v in results.items():
            lines.append(f"  {k}: {v}")
        lines.append(f"\nEpisode complete. Final score: {score:.3f}")
        return "\n".join(lines)
