"""In-process routine scheduler (P5).

Minimal schedule syntax (UTC, no heavy cron dependency):

- ``every_<N>m`` — every N minutes (e.g. ``every_30m``)
- ``every_<N>h`` — every N hours (e.g. ``every_6h``)
- ``daily_HH:MM`` — once a day at HH:MM UTC (e.g. ``daily_09:30``)

A background asyncio task ticks every 60s and executes due routines through
``chief_of_staff.execute_task`` so every run flows through the normal
governance path: mutating actions still pause as PENDING_APPROVAL in the
ledger, and the scheduler never auto-approves YELLOW gates. Routine errors
are recorded as ``error`` status — never fabricated output.

Runs in-process only (no multi-worker). Default OFF unless ROUTINES_ENABLED=1.
"""

import asyncio
import inspect
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from .store import RoutineStore

logger = logging.getLogger(__name__)

TICK_SECONDS = 60


def parse_cron(spec: str) -> Dict[str, Any]:
    """Parse a routine schedule. Raises ValueError on anything unsupported."""
    s = (spec or "").strip()
    m = re.fullmatch(r"every_(\d+)([mh])", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        minutes = n if unit == "m" else n * 60
        if unit == "m" and not 5 <= n <= 10080:
            raise ValueError(f"Unsupported schedule '{s}': minutes must be 5..10080 (minimum every_5m).")
        if unit == "h" and not 1 <= n <= 720:
            raise ValueError(f"Unsupported schedule '{s}': hours must be 1..720.")
        return {"kind": "interval", "minutes": minutes}
    m = re.fullmatch(r"daily_(\d{1,2}):(\d{2})", s)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError(
                f"Unsupported schedule '{s}': hour must be 00..23, minute 00..59."
            )
        return {"kind": "daily", "hour": hour, "minute": minute}
    raise ValueError(
        f"Unsupported schedule '{s}': expected every_<N>m, every_<N>h, or daily_HH:MM."
    )


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_due(routine: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """True when an enabled routine should run at ``now``. Fail-closed: False."""
    if not routine.get("enabled"):
        return False
    try:
        parsed = parse_cron(str(routine.get("cron", "")))
    except ValueError:
        return False
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    last_run = _parse_time(routine.get("last_run"))

    if parsed["kind"] == "interval":
        if last_run is None:
            return True
        return (now - last_run) >= timedelta(minutes=parsed["minutes"])

    # daily: due when today's scheduled time has passed and we have not
    # already run at/after it.
    scheduled = now.replace(
        hour=parsed["hour"], minute=parsed["minute"], second=0, microsecond=0
    )
    if now < scheduled:
        return False
    if last_run is None:
        return True
    return last_run < scheduled


def _status_from_events(events: List[Dict[str, Any]]) -> str:
    types = {e.get("type") for e in events if isinstance(e, dict)}
    if "approval_required" in types:
        return "pending_approval"
    if "action_rejected" in types:
        return "rejected"
    if "model_error" in types:
        return "error"
    return "completed"


async def _collect_events(
    executor: Callable[..., Any], prompt: str
) -> List[Dict[str, Any]]:
    """Drive an executor (async-gen like execute_task, or awaitable) to a list."""
    result = executor(prompt)
    if inspect.isasyncgen(result):
        events = []
        async for event in result:
            events.append(event)
        return events
    if inspect.isawaitable(result):
        resolved = await result
        if inspect.isasyncgen(resolved):
            events = []
            async for event in resolved:
                events.append(event)
            return events
        if isinstance(resolved, list):
            return resolved
        return []
    raise TypeError("Routine executor must return an async generator or awaitable.")


def _default_executor(prompt: str) -> AsyncIterator[Dict[str, Any]]:
    from ..orchestrator.chief_of_staff import chief_of_staff

    return chief_of_staff.execute_task(prompt)


async def run_due_routines(
    now: Optional[datetime] = None,
    executor: Optional[Callable[..., Any]] = None,
    store: Optional[RoutineStore] = None,
) -> List[Dict[str, Any]]:
    """Execute every due routine once. Fail-closed per routine; never raises."""
    store = store or RoutineStore()
    now = now or datetime.now(timezone.utc)
    run_at = now.isoformat()
    executor = executor or _default_executor
    outcomes: List[Dict[str, Any]] = []
    try:
        routines = store.list()
    except Exception as e:
        logger.error("Routine tick aborted: store unreadable (%s).", type(e).__name__)
        return outcomes
    for routine in routines:
        try:
            if not is_due(routine, now):
                continue
        except Exception:
            continue
        try:
            events = await _collect_events(executor, routine["prompt"])
            # Vault compounding for verified researcher output happens inside
            # execute_task itself (vault_compounded event); the scheduler only
            # records the outcome here — it never fabricates vault content.
            status = _status_from_events(events)
        except Exception as e:
            logger.error(
                "Routine '%s' failed: %s.", routine.get("name"), type(e).__name__
            )
            status = "error"
        try:
            store.record_run(routine["id"], status, run_at=run_at)
        except Exception as e:
            logger.error(
                "Routine '%s' ran (%s) but the run could not be recorded (%s).",
                routine.get("name"),
                status,
                type(e).__name__,
            )
        outcomes.append(
            {"id": routine["id"], "name": routine["name"], "status": status}
        )
    return outcomes


async def _routine_loop(tick_seconds: int = TICK_SECONDS) -> None:
    while True:
        try:
            await run_due_routines()
        except Exception as e:  # belt-and-braces: the tick itself never dies loudly
            logger.error("Routine scheduler tick failed: %s.", type(e).__name__)
        await asyncio.sleep(tick_seconds)


def routines_enabled() -> bool:
    return (os.getenv("ROUTINES_ENABLED", "0") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def start_routine_loop(tick_seconds: int = TICK_SECONDS) -> asyncio.Task:
    """Start the in-process background tick. Caller owns cancellation."""
    loop = asyncio.get_running_loop()
    task = loop.create_task(_routine_loop(tick_seconds=tick_seconds))
    logger.info("Routine scheduler started (in-process, tick=%ss).", tick_seconds)
    return task
