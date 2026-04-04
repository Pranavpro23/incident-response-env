"""
Baseline inference script for the Incident Response Environment.

MANDATORY ENVIRONMENT VARIABLES
--------------------------------
  API_BASE_URL      LLM API endpoint  (default: https://router.huggingface.co/v1)
  MODEL_NAME        Model identifier  (default: Qwen/Qwen2.5-72B-Instruct)
  HF_TOKEN          HuggingFace / API key
  LOCAL_IMAGE_NAME  Docker image name (optional; if set, spins up a container)
  ENV_BASE_URL      Direct server URL (optional; used when LOCAL_IMAGE_NAME is not set)

STDOUT FORMAT (mandatory — must not deviate)
--------------------------------------------
  [START] task=<task> env=<env> model=<model>
  [STEP]  step=<n> action=<str> reward=<0.00> done=<true|false> error=<msg|null>
  [END]   success=<true|false> steps=<n> score=<0.000> rewards=<r1,r2,...>

Run:
    python inference.py
"""

from __future__ import annotations

import asyncio
import json
import os
import textwrap
from typing import Any, Dict, List, Optional

from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY") or "no-key"
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME", "")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:8000")
BENCHMARK = "incident_response"

TASKS = ["alert_triage", "root_cause_analysis", "incident_remediation"]

MAX_STEPS = {
    "alert_triage": 8,
    "root_cause_analysis": 12,
    "incident_remediation": 20,
}

SUCCESS_THRESHOLD = 0.5   # score ≥ 0.5 counts as success
TEMPERATURE = 0.3
MAX_TOKENS = 512

# ---------------------------------------------------------------------------
# Logging helpers  (exact format required by the harness)
# ---------------------------------------------------------------------------


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(
    step: int,
    action: str,
    reward: float,
    done: bool,
    error: Optional[str],
) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    # Sanitise action string — no newlines
    action_safe = action.replace("\n", " ").replace("\r", "")
    print(
        f"[STEP] step={step} action={action_safe} "
        f"reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(
    success: bool,
    steps: int,
    score: float,
    rewards: List[float],
) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} "
        f"score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent(
    """
    You are an expert Site Reliability Engineer (SRE) responding to production incidents.
    You will be given an incident with active alerts, and you must investigate and resolve it.

    AVAILABLE COMMANDS AND PARAMETERS:
    - check_alerts                            — list active alerts
    - check_service_health  service=<name>    — health status of a service
    - view_logs             service=<name>    — recent log entries
    - view_metrics          service=<name>    — current metrics
    - check_dependencies    service=<name>    — upstream/downstream services
    - view_deployment_history service=<name>  — recent deployments
    - classify_incident     severity=P1|P2|P3  affected_service=<name>   [task 1]
    - identify_root_cause   cause=<cause>  component=<name>              [task 2]
    - restart_service       service=<name>                               [task 3]
    - rollback_deployment   service=<name>                               [task 3]
    - resolve_incident      resolution=<description>                     [task 3]

    STRATEGY:
    1. Start by checking alerts and the most suspicious services.
    2. Correlate logs, metrics, and deployment history.
    3. Act on evidence — don't guess.
    4. For task 1: use classify_incident once you know severity and primary service.
    5. For task 2: use identify_root_cause once you have identified the root cause.
    6. For task 3: remediate the correct service, verify recovery, then resolve.

    RESPONSE FORMAT — you must respond with ONLY valid JSON, no extra text:
    {
      "command": "<command>",
      "parameters": {"key": "value"},
      "reasoning": "<one sentence explaining why>"
    }
    """
).strip()


def build_user_prompt(
    task: str,
    obs: Any,
    step: int,
    history: List[str],
) -> str:
    alerts_block = "\n".join(f"  {a}" for a in (obs.active_alerts or []))
    services_block = "\n".join(
        f"  {svc}: {health}" for svc, health in (obs.services_summary or {}).items()
    )
    history_block = "\n".join(history[-6:]) if history else "None"

    return textwrap.dedent(
        f"""
        TASK: {task}
        OBJECTIVE: {obs.task_objective}

        CURRENT SITUATION (step {step}/{obs.max_steps}):
        {obs.message}

        ACTIVE ALERTS:
        {alerts_block}

        SERVICE STATUS:
        {services_block}

        LAST COMMAND OUTPUT:
        {obs.command_output or '(none — start of episode)'}

        RECENT ACTIONS:
        {history_block}

        AVAILABLE COMMANDS: {', '.join(obs.available_commands or [])}

        What is your next action? Respond with JSON only.
        """
    ).strip()


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def get_model_action(
    client: OpenAI,
    task: str,
    obs: Any,
    step: int,
    history: List[str],
) -> Dict[str, Any]:
    """Call the LLM and parse the JSON action. Falls back to check_alerts on error."""
    user_prompt = build_user_prompt(task, obs, step, history)
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        text = (completion.choices[0].message.content or "").strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(
                line for line in lines
                if not line.startswith("```")
            )

        parsed = json.loads(text)
        return {
            "command": str(parsed.get("command", "check_alerts")),
            "parameters": {
                str(k): str(v)
                for k, v in parsed.get("parameters", {}).items()
            },
            "reasoning": str(parsed.get("reasoning", "")),
        }
    except Exception as exc:
        print(f"[DEBUG] LLM parse error: {exc}", flush=True)
        return {"command": "check_alerts", "parameters": {}, "reasoning": "fallback"}


# ---------------------------------------------------------------------------
# Episode runner
# ---------------------------------------------------------------------------


async def run_episode(
    env: Any,
    client: OpenAI,
    task: str,
) -> None:
    """Run a single episode for one task, emitting structured stdout logs."""
    from models import IncidentAction  # local import to avoid circular at module level

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False
    history: List[str] = []

    log_start(task=task, env=BENCHMARK, model=MODEL_NAME)

    try:
        result = await env.reset(task=task)
        obs = result.observation

        for step in range(1, MAX_STEPS[task] + 1):
            if result.done:
                break

            action_dict = get_model_action(client, task, obs, step, history)
            action = IncidentAction(
                command=action_dict["command"],
                parameters=action_dict["parameters"],
                reasoning=action_dict["reasoning"],
            )
            action_str = (
                f"{action.command}"
                + (f"({','.join(f'{k}={v}' for k,v in action.parameters.items())})" if action.parameters else "()")
            )

            try:
                result = await env.step(action)
                reward = result.reward or 0.0
                done = result.done
                error = None
            except Exception as exc:
                reward = 0.0
                done = False
                error = str(exc)[:120]
                result = type("R", (), {"observation": obs, "done": False, "reward": 0.0})()

            obs = result.observation
            rewards.append(reward)
            steps_taken = step

            log_step(step=step, action=action_str, reward=reward, done=done, error=error)

            history.append(
                f"step={step}: {action_str} -> reward={reward:.2f} output={str(getattr(obs, 'command_output', ''))[:80]}"
            )

            if done:
                break

        # Score = sum of rewards (already in [0,1] range per episode)
        score = sum(rewards)
        score = min(max(score, 0.0), 1.0)
        success = score >= SUCCESS_THRESHOLD

    except Exception as exc:
        print(f"[DEBUG] Episode error: {exc}", flush=True)
    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    from client import IncidentResponseEnv

    if LOCAL_IMAGE_NAME:
        # Spin up a Docker container from the image
        env = await IncidentResponseEnv.from_docker_image(LOCAL_IMAGE_NAME)
    else:
        # Connect directly to a running server
        env = IncidentResponseEnv(base_url=ENV_BASE_URL)
        await env.connect()

    try:
        for task in TASKS:
            await run_episode(env, client, task)
    finally:
        try:
            await env.close()
        except Exception as exc:
            print(f"[DEBUG] env.close() error: {exc}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
