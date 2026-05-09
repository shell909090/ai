"""Built-in task tool provider for creating sub-tasks (sub-sessions)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from little_agent.tools.protocol import AsyncToolFn, ToolArgDef, ToolDef
from little_agent.types import JSONValue

if TYPE_CHECKING:
    from little_agent.agent.agent import AgentCore
    from little_agent.agent.protocol import Session
    from little_agent.agent.session import SessionCore

logger = logging.getLogger(__name__)

TASK_TIMEOUT = 300.0


@dataclass
class _TaskSpec:
    task_id: int | None
    depends: list[int]
    kwargs: dict[str, JSONValue]
    result_future: asyncio.Future[JSONValue]


def _spec_label(spec: _TaskSpec) -> str:
    """Return a human-readable label for a task spec."""
    return f"id={spec.task_id}" if spec.task_id is not None else "anon"


def _launch_ready_tasks(
    unstarted: list[_TaskSpec],
    completed: dict[int, JSONValue],
    running: dict[asyncio.Task[JSONValue], _TaskSpec],
    execute: Any,
) -> None:
    """Start all tasks whose dependencies are satisfied."""
    for spec in [s for s in unstarted if all(d in completed for d in s.depends)]:
        unstarted.remove(spec)
        logger.info("Task %s starting", _spec_label(spec))
        running[asyncio.create_task(execute(spec))] = spec


def _fail_unresolvable(unstarted: list[_TaskSpec]) -> None:
    """Fail all remaining unstarted tasks due to unresolvable dependencies."""
    for spec in unstarted:
        logger.info(
            "Task %s failed: unresolvable dependency %s",
            _spec_label(spec),
            spec.depends,
        )
        if not spec.result_future.done():
            spec.result_future.set_result(
                {"status": "failed", "output": f"unresolvable dependency: {spec.depends}"}
            )


def _collect_done_tasks(
    done: set[asyncio.Task[JSONValue]],
    running: dict[asyncio.Task[JSONValue], _TaskSpec],
    completed: dict[int, JSONValue],
) -> None:
    """Process finished tasks and record results."""
    for task in done:
        spec = running.pop(task)
        try:
            result: JSONValue = task.result()
        except Exception as e:
            result = {"status": "failed", "output": str(e)}
        status = result.get("status") if isinstance(result, dict) else "unknown"
        logger.info("Task %s finished (status=%s)", _spec_label(spec), status)
        if spec.task_id is not None:
            completed[spec.task_id] = result
        if not spec.result_future.done():
            spec.result_future.set_result(result)


class TaskToolProvider:
    """Provides the built-in create_task tool for spawning sub-sessions."""

    _TOOL_DEF = ToolDef(
        desc="Create a sub-task with its own session and execute it",
        args=[
            ToolArgDef("prompt", "string", "The prompt for the sub-task", True),
            ToolArgDef("id", "integer", "Optional sub-task identifier", False),
            ToolArgDef("depends", "array", "Optional list of dependency task IDs", False),
            ToolArgDef(
                "tools", "array", "Optional list of allowed tool names (default: all)", False
            ),
            ToolArgDef(
                "inheritance", "boolean", "If true, inherit conversation history via fork", False
            ),
        ],
    )

    def __init__(self, agent: AgentCore) -> None:
        self._agent = agent
        self._pending: list[_TaskSpec] = []
        self._scheduler: asyncio.Task[None] | None = None

    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        """Yield the single create_task tool triple."""
        yield ("create_task", self._TOOL_DEF, self._create_task_dispatch)

    async def _create_task_dispatch(self, args: dict[str, JSONValue]) -> JSONValue:
        return await self.create_task(**args)

    def _get_allowed_tools(self, tool_names: Sequence[str] | None) -> list[str]:
        """Return allowed tool names for a sub-task, always excluding create_task."""
        names = set(tool_names) if tool_names is not None else None
        return list(self._agent.tools.desc_tool(names, exclude={"create_task"}).keys())

    async def _fork_for_inheritance(self, session: SessionCore) -> Session:
        """Fork a new session from the current, sharing frozen history."""
        from little_agent.agent.session import SessionCore as SessionCoreImpl

        node = session.tail
        while node is not None and hasattr(node, "frozen"):
            node = node.prev
        fork_tail = node if node is not None else None

        sub_session = SessionCoreImpl(
            session_id=str(uuid.uuid4()),
            cwd=session.cwd,
            agent=self._agent,
        )
        sub_session.tail = fork_tail
        return sub_session

    async def create_task(self, **kwargs: JSONValue) -> JSONValue:
        # Registration is fully synchronous so that all create_task coroutines
        # launched by the same asyncio.gather complete registration before the
        # scheduler (appended to the event-loop queue after these coroutines)
        # starts running.
        task_id_raw = kwargs.get("id")
        task_id = int(task_id_raw) if isinstance(task_id_raw, (int, float)) else None

        depends_raw = kwargs.get("depends")
        depends = (
            [int(d) for d in depends_raw if isinstance(d, (int, float))]
            if isinstance(depends_raw, list)
            else []
        )

        spec = _TaskSpec(
            task_id=task_id,
            depends=depends,
            kwargs=dict(kwargs),
            result_future=asyncio.get_running_loop().create_future(),
        )
        self._pending.append(spec)

        if self._scheduler is None or self._scheduler.done():
            self._scheduler = asyncio.create_task(self._run_scheduler())

        return await spec.result_future

    async def _run_scheduler(self) -> None:
        """Run registered tasks in topological order."""
        specs = list(self._pending)
        self._pending.clear()

        completed: dict[int, JSONValue] = {}
        running: dict[asyncio.Task[JSONValue], _TaskSpec] = {}
        unstarted = list(specs)

        try:
            while unstarted or running:
                _launch_ready_tasks(unstarted, completed, running, self._execute)
                if not running:
                    _fail_unresolvable(unstarted)
                    break
                done, _ = await asyncio.wait(running.keys(), return_when=asyncio.FIRST_COMPLETED)
                _collect_done_tasks(done, running, completed)

        except Exception as e:
            for spec in [*unstarted, *running.values()]:
                if not spec.result_future.done():
                    spec.result_future.set_result(
                        {"status": "failed", "output": f"scheduler error: {e}"}
                    )
            raise

    async def _execute(self, spec: _TaskSpec) -> JSONValue:
        """Run the actual sub-session for one task spec."""
        kwargs = spec.kwargs
        prompt = kwargs.get("prompt")
        if not isinstance(prompt, str):
            return {"status": "failed", "output": "prompt must be a string"}

        tool_names_raw = kwargs.get("tools")
        tool_names: list[str] | None = None
        if isinstance(tool_names_raw, list):
            tool_names = [str(t) for t in tool_names_raw]

        allowed_tools = self._get_allowed_tools(tool_names)
        inheritance = bool(kwargs.get("inheritance", False))

        if inheritance:
            from little_agent.agent.context import current_session

            session = current_session.get()
            if session is None:
                return {
                    "status": "failed",
                    "output": "inheritance=true but no current session context",
                }
            sub_session = await self._fork_for_inheritance(session)
        else:
            sub_session = await self._agent.new()

        try:
            stop_reason, output = await asyncio.wait_for(
                sub_session.prompt(prompt, allowed_tools=allowed_tools), timeout=TASK_TIMEOUT
            )
            return {"status": "completed", "stop_reason": stop_reason, "output": output}
        except TimeoutError:
            return {"status": "timeout", "output": f"Sub-task timed out after {TASK_TIMEOUT}s"}
        except Exception as e:
            return {"status": "failed", "output": str(e)}
