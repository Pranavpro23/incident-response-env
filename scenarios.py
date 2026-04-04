"""
Incident scenarios for the three tasks:
  1. alert_triage        (easy)   — classify severity + primary affected service
  2. root_cause_analysis (medium) — identify root cause + component
  3. incident_remediation (hard)  — investigate, remediate, verify, resolve
"""

from typing import Any, Dict


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _service(
    name: str,
    health: str,  # HEALTHY | DEGRADED | CRITICAL | CRASHING
    error_rate: float = 0.0,
    latency_p99_ms: int = 80,
    cpu_pct: int = 20,
    mem_pct: int = 35,
    instances: int = 3,
    version: str = "1.0.0",
    prev_version: str = "0.9.0",
) -> Dict[str, Any]:
    return {
        "health": health,
        "error_rate_pct": error_rate,
        "latency_p99_ms": latency_p99_ms,
        "cpu_pct": cpu_pct,
        "mem_pct": mem_pct,
        "instances": instances,
        "version": version,
        "prev_version": prev_version,
    }


# ---------------------------------------------------------------------------
# Task 1 — Alert Triage (easy)
# ---------------------------------------------------------------------------

ALERT_TRIAGE_SCENARIO: Dict[str, Any] = {
    "title": "Payment Service Outage",
    "description": (
        "You are the on-call SRE. Multiple alerts just fired at 2:47 AM. "
        "Your job: classify the overall incident severity (P1/P2/P3) and "
        "identify the PRIMARY affected service."
    ),
    "task_objective": (
        "Execute: classify_incident with parameters "
        "{'severity': 'P1'|'P2'|'P3', 'affected_service': '<service-name>'}. "
        "Investigate first, then classify."
    ),
    "incident_id": "INC-20240315-001",
    "max_steps": 8,
    "services": {
        "payment-service": _service(
            "payment-service", "CRITICAL",
            error_rate=89.3, latency_p99_ms=12400,
            cpu_pct=95, mem_pct=72, instances=3,
            version="2.1.4", prev_version="2.1.3",
        ),
        "api-gateway": _service(
            "api-gateway", "DEGRADED",
            error_rate=12.1, latency_p99_ms=4200,
            cpu_pct=68, mem_pct=45, instances=4,
        ),
        "checkout-service": _service(
            "checkout-service", "DEGRADED",
            error_rate=23.4, latency_p99_ms=9800,
            cpu_pct=55, mem_pct=40, instances=2,
        ),
        "inventory-service": _service(
            "inventory-service", "HEALTHY",
            error_rate=0.2, latency_p99_ms=95,
            cpu_pct=22, mem_pct=38,
        ),
        "user-service": _service(
            "user-service", "HEALTHY",
            error_rate=0.1, latency_p99_ms=75,
            cpu_pct=18, mem_pct=30,
        ),
    },
    "alerts": [
        "[CRITICAL] payment-service: HTTP 5xx error rate 89.3% (threshold: 1%) for 8 min",
        "[WARNING]  api-gateway: P99 latency 4200ms (threshold: 500ms) for 8 min",
        "[WARNING]  checkout-service: Error rate 23.4% (threshold: 5%) for 6 min",
        "[INFO]     payment-service: Database connection timeout errors detected",
        "[INFO]     inventory-service: DB connection pool at 67% utilization",
    ],
    "logs": {
        "payment-service": [
            "2024-03-15T02:39:12Z ERROR  Failed to connect to payment-db: connection timeout (attempt 1/3)",
            "2024-03-15T02:39:13Z ERROR  Failed to connect to payment-db: connection timeout (attempt 2/3)",
            "2024-03-15T02:39:14Z ERROR  Failed to connect to payment-db: connection timeout (attempt 3/3)",
            "2024-03-15T02:39:14Z ERROR  Payment processing failed: db_connection_error for txn_id=TXN-88291",
            "2024-03-15T02:39:15Z ERROR  HTTP 500 returned to client: /api/payments/charge",
            "2024-03-15T02:40:02Z ERROR  Circuit breaker OPEN: payment-db (50 consecutive failures)",
            "2024-03-15T02:40:03Z ERROR  Rejecting all requests: payment-db circuit breaker open",
            "2024-03-15T02:41:18Z WARN   Retrying payment-db connection (attempt 1) — still failing",
            "2024-03-15T02:45:00Z ERROR  89.3% of requests returning 500 in last 60s",
        ],
        "api-gateway": [
            "2024-03-15T02:39:20Z WARN   Upstream payment-service returning 5xx (error_rate=12.1%)",
            "2024-03-15T02:39:22Z WARN   P99 latency spike: 4200ms on /api/payments/* routes",
            "2024-03-15T02:40:01Z ERROR  Upstream connection timeout: payment-service /api/payments/charge",
            "2024-03-15T02:40:55Z INFO   Routing 100% traffic to payment-service (no fallback configured)",
        ],
        "checkout-service": [
            "2024-03-15T02:39:30Z ERROR  Payment service call failed: HTTP 500 — cannot complete checkout",
            "2024-03-15T02:39:30Z ERROR  order_id=ORD-99821 stuck in PENDING state",
            "2024-03-15T02:41:00Z ERROR  23.4% of checkout attempts failing (payment-service errors)",
        ],
        "inventory-service": [
            "2024-03-15T02:38:00Z INFO   DB connection pool at 67% — within normal range",
            "2024-03-15T02:42:00Z INFO   Inventory queries completing normally (avg 42ms)",
        ],
        "user-service": [
            "2024-03-15T02:42:00Z INFO   All requests processing normally",
            "2024-03-15T02:43:00Z INFO   Auth token validation: avg 21ms",
        ],
    },
    "metrics": {
        "payment-service": {
            "error_rate_1m": "89.3%",
            "error_rate_5m": "72.1%",
            "p50_latency": "450ms",
            "p99_latency": "12400ms",
            "requests_per_sec": 124,
            "success_per_sec": 13,
            "cpu": "95%",
            "memory": "72%",
            "active_db_connections": "0/50 (circuit breaker open)",
        },
        "api-gateway": {
            "error_rate_1m": "12.1%",
            "p99_latency": "4200ms",
            "requests_per_sec": 890,
            "cpu": "68%",
            "memory": "45%",
        },
        "checkout-service": {
            "error_rate_1m": "23.4%",
            "p99_latency": "9800ms",
            "requests_per_sec": 45,
            "cpu": "55%",
            "memory": "40%",
        },
        "inventory-service": {
            "error_rate_1m": "0.2%",
            "p99_latency": "95ms",
            "requests_per_sec": 210,
            "cpu": "22%",
            "memory": "38%",
        },
        "user-service": {
            "error_rate_1m": "0.1%",
            "p99_latency": "75ms",
            "requests_per_sec": 340,
            "cpu": "18%",
            "memory": "30%",
        },
    },
    "dependencies": {
        "api-gateway": ["payment-service", "checkout-service", "user-service", "inventory-service"],
        "checkout-service": ["payment-service", "inventory-service"],
        "payment-service": ["payment-db"],
        "inventory-service": ["inventory-db"],
        "user-service": ["user-db"],
    },
    "deployment_history": {
        "payment-service": [
            {"version": "2.1.4", "deployed_at": "2024-03-15T01:15:00Z", "deployed_by": "ci-bot", "status": "active"},
            {"version": "2.1.3", "deployed_at": "2024-03-14T14:30:00Z", "deployed_by": "jane.doe", "status": "previous"},
        ],
        "api-gateway": [
            {"version": "3.2.1", "deployed_at": "2024-03-14T10:00:00Z", "deployed_by": "ci-bot", "status": "active"},
        ],
    },
    "ground_truth": {
        "severity": "P1",
        "affected_service": "payment-service",
    },
}


# ---------------------------------------------------------------------------
# Task 2 — Root Cause Analysis (medium)
# ---------------------------------------------------------------------------

ROOT_CAUSE_SCENARIO: Dict[str, Any] = {
    "title": "Orders API Degradation",
    "description": (
        "Production incident: orders-api is returning 503 errors for ~40% of requests. "
        "The issue started ~25 minutes ago. Investigate the root cause and identify "
        "the specific component responsible."
    ),
    "task_objective": (
        "Execute: identify_root_cause with parameters "
        "{'cause': '<root-cause-category>', 'component': '<service-or-db-name>'}. "
        "Investigate thoroughly before submitting."
    ),
    "incident_id": "INC-20240315-002",
    "max_steps": 12,
    "services": {
        "orders-api": _service(
            "orders-api", "DEGRADED",
            error_rate=41.2, latency_p99_ms=31000,
            cpu_pct=62, mem_pct=48, instances=3,
        ),
        "orders-db": _service(
            "orders-db", "DEGRADED",
            error_rate=0.0, latency_p99_ms=8300,
            cpu_pct=98, mem_pct=60, instances=1,
        ),
        "inventory-service": _service("inventory-service", "HEALTHY", error_rate=0.1),
        "payment-service": _service("payment-service", "HEALTHY", error_rate=0.2),
        "cache-service": _service("cache-service", "HEALTHY", error_rate=0.0, latency_p99_ms=2),
    },
    "alerts": [
        "[WARNING] orders-api: Error rate 41.2% (threshold: 5%) for 25 min",
        "[WARNING] orders-api: P99 latency 31000ms (threshold: 2000ms) for 25 min",
        "[WARNING] orders-db: CPU usage 98% for 25 min",
        "[INFO]    orders-db: Slow query alert — queries exceeding 5s threshold",
        "[INFO]    orders-api: Connection pool exhaustion warnings",
    ],
    "logs": {
        "orders-api": [
            "2024-03-15T03:12:00Z ERROR  Database query timeout after 30s: SELECT * FROM orders WHERE customer_id=?",
            "2024-03-15T03:12:01Z ERROR  No database connections available (pool exhausted 50/50)",
            "2024-03-15T03:12:01Z ERROR  Returning 503 Service Unavailable to client",
            "2024-03-15T03:13:45Z ERROR  Database query timeout after 30s: SELECT * FROM orders WHERE status IN (?)",
            "2024-03-15T03:14:00Z WARN   DB connection pool usage: 50/50 (100%) — connections waiting: 127",
            "2024-03-15T03:15:22Z ERROR  Transaction rollback: db_timeout after 30000ms",
            "2024-03-15T03:16:00Z ERROR  41.2% error rate in last 60s (threshold: 5%)",
        ],
        "orders-db": [
            "2024-03-15T03:11:55Z WARN   Slow query detected (8.3s): SELECT * FROM orders WHERE customer_id = 88291 AND status IN ('pending','processing') [rows_examined=4891230, rows_sent=3]",
            "2024-03-15T03:12:00Z WARN   Query plan: FULL TABLE SCAN on orders (4.8M rows)",
            "2024-03-15T03:12:01Z WARN   Slow query detected (9.1s): SELECT * FROM orders WHERE status='pending' [rows_examined=4891230]",
            "2024-03-15T03:12:10Z WARN   Active connections: 50/50 (connection pool exhausted)",
            "2024-03-15T03:12:10Z WARN   Waiting queue: 127 clients waiting for connection",
            "2024-03-15T03:13:00Z WARN   CPU usage 98% — sustained high load from sequential scans",
            "2024-03-15T03:14:30Z INFO   Recent schema change detected: migration 20240315_add_order_filters (25 min ago)",
            "2024-03-15T03:15:00Z WARN   Slow query detected (11.2s): SELECT COUNT(*) FROM orders WHERE customer_id=? [no index]",
        ],
        "inventory-service": [
            "2024-03-15T03:12:00Z INFO   All queries completing normally (avg 31ms)",
        ],
        "payment-service": [
            "2024-03-15T03:12:00Z INFO   Processing payments normally",
        ],
        "cache-service": [
            "2024-03-15T03:12:00Z INFO   Cache hit rate: 89.2% — operating normally",
        ],
    },
    "metrics": {
        "orders-api": {
            "error_rate_1m": "41.2%",
            "p99_latency": "31000ms",
            "p50_latency": "28400ms",
            "requests_per_sec": 88,
            "cpu": "62%",
            "memory": "48%",
            "db_pool_used": "50/50 (100%)",
            "db_pool_waiting": 127,
        },
        "orders-db": {
            "cpu": "98%",
            "memory": "60%",
            "active_connections": "50/50",
            "slow_queries_per_min": 84,
            "avg_query_time_ms": 8300,
            "rows_examined_avg": "4.8M per query",
            "replication_lag_ms": 0,
        },
        "inventory-service": {
            "error_rate_1m": "0.1%",
            "p99_latency": "88ms",
            "cpu": "23%",
        },
        "cache-service": {
            "hit_rate": "89.2%",
            "error_rate_1m": "0.0%",
            "p99_latency": "2ms",
        },
    },
    "dependencies": {
        "orders-api": ["orders-db", "cache-service", "inventory-service"],
        "inventory-service": ["inventory-db"],
        "payment-service": ["payment-db"],
    },
    "deployment_history": {
        "orders-db": [
            {
                "version": "migration_20240315_add_order_filters",
                "deployed_at": "2024-03-15T02:47:00Z",
                "deployed_by": "bob.smith",
                "status": "active",
                "description": "Added new filter columns to orders table for reporting. NOTE: index creation was deferred.",
            },
            {
                "version": "migration_20240314_add_payment_ref",
                "deployed_at": "2024-03-14T16:00:00Z",
                "deployed_by": "ci-bot",
                "status": "previous",
            },
        ],
        "orders-api": [
            {
                "version": "1.8.2",
                "deployed_at": "2024-03-14T10:00:00Z",
                "deployed_by": "ci-bot",
                "status": "active",
                "description": "Updated order filtering to use new DB columns from migration.",
            },
        ],
    },
    "ground_truth": {
        "cause": "missing_database_index",
        "component": "orders-db",
        # Partial credit causes (checked in grader)
        "partial_causes": ["slow_database_query", "database_performance", "full_table_scan"],
        "partial_components": ["orders-api"],
    },
}


# ---------------------------------------------------------------------------
# Task 3 — Incident Remediation (hard)
# ---------------------------------------------------------------------------

INCIDENT_REMEDIATION_SCENARIO: Dict[str, Any] = {
    "title": "Auth Service Memory Leak — Cascading API Gateway Failures",
    "description": (
        "Production P1 incident: api-gateway is returning 503 errors on all /auth/* "
        "paths. The auth-service is crashing repeatedly with OOM errors. "
        "A new version was deployed 2 hours ago. "
        "Investigate, remediate, verify recovery, and resolve the incident."
    ),
    "task_objective": (
        "Investigate the incident, execute the correct remediation steps, verify "
        "service recovery, then call resolve_incident with "
        "{'resolution': '<description of what you did>'}."
    ),
    "incident_id": "INC-20240315-003",
    "max_steps": 20,
    "services": {
        "api-gateway": _service(
            "api-gateway", "DEGRADED",
            error_rate=34.7, latency_p99_ms=6100,
            cpu_pct=72, mem_pct=50, instances=4,
            version="3.2.1",
        ),
        "auth-service": _service(
            "auth-service", "CRASHING",
            error_rate=78.2, latency_p99_ms=0,
            cpu_pct=12, mem_pct=96,
            instances=2, version="2.4.0", prev_version="2.3.1",
        ),
        "user-db": _service(
            "user-db", "HEALTHY",
            error_rate=0.0, latency_p99_ms=45,
            cpu_pct=28, mem_pct=42,
        ),
        "cache-service": _service(
            "cache-service", "HEALTHY",
            error_rate=0.0, latency_p99_ms=2,
            cpu_pct=15, mem_pct=30,
        ),
        "notification-service": _service(
            "notification-service", "HEALTHY",
            error_rate=0.1, latency_p99_ms=210,
            cpu_pct=20, mem_pct=35,
        ),
    },
    "alerts": [
        "[CRITICAL] auth-service: OOM kill detected — container restarted 8 times in last 2h",
        "[CRITICAL] api-gateway: Error rate 34.7% on /auth/* paths (threshold: 1%)",
        "[WARNING]  auth-service: Memory usage 96% (threshold: 85%)",
        "[WARNING]  api-gateway: Circuit breaker OPEN for auth-service",
        "[INFO]     auth-service: Container restart count: 8 (last restart: 3 min ago)",
    ],
    "logs": {
        "auth-service": [
            "2024-03-15T00:48:00Z INFO   auth-service v2.4.0 started successfully",
            "2024-03-15T00:52:00Z INFO   Processing JWT validation requests normally",
            "2024-03-15T01:05:00Z WARN   Memory usage climbing: 45% → 62% (was 35% on v2.3.1)",
            "2024-03-15T01:25:00Z WARN   Memory usage: 78% — leak suspected in token cache",
            "2024-03-15T01:48:00Z WARN   Memory usage: 91% — GC pressure high",
            "2024-03-15T01:55:00Z ERROR  Memory usage: 96% — approaching OOM threshold",
            "2024-03-15T02:03:00Z ERROR  java.lang.OutOfMemoryError: Java heap space",
            "2024-03-15T02:03:01Z ERROR  Container killed by OOM killer (exit code 137)",
            "2024-03-15T02:03:15Z INFO   auth-service v2.4.0 restarted",
            "2024-03-15T02:20:00Z ERROR  Memory usage: 89% — cycle repeating",
            "2024-03-15T02:34:00Z ERROR  java.lang.OutOfMemoryError: Java heap space",
            "2024-03-15T02:34:01Z ERROR  Container killed by OOM killer (exit code 137)",
            "2024-03-15T02:34:15Z INFO   auth-service v2.4.0 restarted (restart #5)",
            "2024-03-15T02:44:00Z ERROR  java.lang.OutOfMemoryError: Java heap space",
            "2024-03-15T02:44:01Z ERROR  Container killed by OOM killer (exit code 137)",
            "2024-03-15T02:44:15Z INFO   auth-service v2.4.0 restarted (restart #8, current)",
            "2024-03-15T02:44:20Z WARN   Memory already at 34% — leak accumulating from first request",
        ],
        "api-gateway": [
            "2024-03-15T02:03:30Z ERROR  auth-service health check failed: connection refused",
            "2024-03-15T02:03:31Z WARN   Circuit breaker HALF-OPEN: auth-service (testing)",
            "2024-03-15T02:04:00Z ERROR  Upstream auth-service: connection reset during restart",
            "2024-03-15T02:04:01Z ERROR  Circuit breaker OPEN: auth-service — all /auth/* requests failing",
            "2024-03-15T02:44:30Z ERROR  34.7% of /auth/* requests returning 503",
            "2024-03-15T02:44:31Z INFO   /api/* routes (non-auth) operating normally",
        ],
        "user-db": [
            "2024-03-15T02:44:00Z INFO   All queries completing normally (avg 45ms)",
            "2024-03-15T02:44:00Z INFO   Connection pool: 12/100 connections in use",
        ],
        "cache-service": [
            "2024-03-15T02:44:00Z INFO   Cache hit rate: 91.3% — normal operation",
        ],
        "notification-service": [
            "2024-03-15T02:44:00Z INFO   Processing notifications normally",
        ],
    },
    "metrics": {
        "auth-service": {
            "error_rate_1m": "78.2%",
            "memory": "96% (7.68GB / 8GB heap)",
            "cpu": "12% (low — mostly blocked on GC)",
            "restarts_last_2h": 8,
            "uptime_current": "3 minutes",
            "version": "2.4.0",
        },
        "api-gateway": {
            "error_rate_auth_paths": "34.7%",
            "error_rate_other_paths": "0.1%",
            "p99_latency": "6100ms",
            "circuit_breaker_auth": "OPEN",
            "cpu": "72%",
            "memory": "50%",
        },
        "user-db": {
            "cpu": "28%",
            "memory": "42%",
            "connections": "12/100",
            "avg_query_ms": 45,
        },
        "cache-service": {
            "hit_rate": "91.3%",
            "memory": "30%",
            "p99_latency": "2ms",
        },
    },
    "dependencies": {
        "api-gateway": ["auth-service", "notification-service", "user-db"],
        "auth-service": ["user-db", "cache-service"],
        "notification-service": ["user-db"],
    },
    "deployment_history": {
        "auth-service": [
            {
                "version": "2.4.0",
                "deployed_at": "2024-03-15T00:45:00Z",
                "deployed_by": "ci-bot",
                "status": "active",
                "description": "Added token introspection cache for performance. JIRA: AUTH-1892",
            },
            {
                "version": "2.3.1",
                "deployed_at": "2024-03-14T11:00:00Z",
                "deployed_by": "alice.chen",
                "status": "previous",
                "description": "Hotfix: token expiry edge case. Stable in production for 13h.",
            },
            {
                "version": "2.3.0",
                "deployed_at": "2024-03-13T14:00:00Z",
                "deployed_by": "ci-bot",
                "status": "archived",
            },
        ],
        "api-gateway": [
            {
                "version": "3.2.1",
                "deployed_at": "2024-03-14T10:00:00Z",
                "deployed_by": "ci-bot",
                "status": "active",
            }
        ],
    },
    "ground_truth": {
        "correct_remediation": "rollback_deployment",
        "correct_service": "auth-service",
        "correct_version": "2.3.1",
    },
    # How services recover after correct remediation
    "recovery": {
        "after_rollback_auth": {
            "auth-service": {"health": "HEALTHY", "mem_pct": 35, "error_rate": 0.2, "restarts": 0},
        },
        "after_auth_healthy": {
            "api-gateway": {"health": "HEALTHY", "error_rate": 0.1, "circuit_breaker": "CLOSED"},
        },
    },
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "alert_triage": ALERT_TRIAGE_SCENARIO,
    "root_cause_analysis": ROOT_CAUSE_SCENARIO,
    "incident_remediation": INCIDENT_REMEDIATION_SCENARIO,
}

TASK_NAMES = list(SCENARIOS.keys())
