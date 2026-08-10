from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psutil

from gow_monitor.domain.process_resources import GowProcessResourceSnapshot

_PROCESS_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
    OSError,
)


class GowProcessTreeReader:
    """Collect resource usage for a GOW process and its descendants.

    The reader keeps psutil Process objects alive between samples. This is
    required because ``Process.cpu_percent(interval=None)`` calculates CPU usage
    relative to the previous call made on the same Process instance.
    """

    def __init__(
        self,
        root_pid: int | None = None,
        *,
        psutil_module: Any = psutil,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._psutil = psutil_module
        self._clock = clock
        self._root_pid: int | None = None
        self._process_cache: dict[int, Any] = {}

        if root_pid is not None:
            self.attach(root_pid)

    @property
    def root_pid(self) -> int | None:
        return self._root_pid

    @property
    def is_attached(self) -> bool:
        return self._root_pid is not None

    def attach(self, root_pid: int) -> None:
        """Attach the reader to the PID that identifies the GOW launcher."""

        if isinstance(root_pid, bool) or not isinstance(root_pid, int):
            raise TypeError("root_pid must be an integer")

        if root_pid < 1:
            raise ValueError("root_pid must be positive")

        self._root_pid = root_pid
        self._process_cache.clear()

        try:
            root_process = self._psutil.Process(root_pid)
        except _PROCESS_ERRORS:
            return

        self._cache_process(root_process)

    def detach(self) -> None:
        self._root_pid = None
        self._process_cache.clear()

    def snapshot(self) -> GowProcessResourceSnapshot:
        captured_at = float(self._clock())

        if self._root_pid is None:
            return GowProcessResourceSnapshot.unavailable(
                captured_at=captured_at,
                status="No GOW process is attached",
            )

        try:
            root_process = self._process_for_pid(self._root_pid)
        except _PROCESS_ERRORS:
            self._process_cache.clear()
            return GowProcessResourceSnapshot.unavailable(
                captured_at=captured_at,
                root_pid=self._root_pid,
                status="The attached GOW process no longer exists",
            )

        if not self._is_live(root_process):
            self._process_cache.clear()
            return GowProcessResourceSnapshot.unavailable(
                captured_at=captured_at,
                root_pid=self._root_pid,
                status="The attached GOW process is no longer running",
            )

        discovered: dict[int, Any] = {
            int(root_process.pid): root_process,
        }
        child_discovery_failed = False

        try:
            children = root_process.children(recursive=True)
        except _PROCESS_ERRORS:
            children = ()
            child_discovery_failed = True

        for discovered_process in children:
            try:
                pid = int(discovered_process.pid)
            except (AttributeError, TypeError, ValueError):
                continue

            try:
                process = self._reuse_or_cache(discovered_process)
            except _PROCESS_ERRORS:
                continue

            if self._is_live(process):
                discovered[pid] = process

        cpu_process_percent = 0.0
        memory_rss_bytes = 0
        thread_count = 0
        inaccessible_processes = 0
        live_processes: dict[int, Any] = {}

        for pid, process in discovered.items():
            if not self._is_live(process):
                continue

            live_processes[pid] = process

            try:
                cpu_value = float(process.cpu_percent(interval=None))
            except _PROCESS_ERRORS:
                inaccessible_processes += 1
            else:
                cpu_process_percent += max(0.0, cpu_value)

            try:
                rss_value = int(process.memory_info().rss)
            except _PROCESS_ERRORS:
                inaccessible_processes += 1
            else:
                memory_rss_bytes += max(0, rss_value)

            try:
                process_threads = int(process.num_threads())
            except _PROCESS_ERRORS:
                inaccessible_processes += 1
            else:
                thread_count += max(0, process_threads)

        if self._root_pid not in live_processes:
            self._process_cache.clear()
            return GowProcessResourceSnapshot.unavailable(
                captured_at=captured_at,
                root_pid=self._root_pid,
                status="The attached GOW root process disappeared during sampling",
            )

        self._process_cache = dict(live_processes)

        logical_cores_raw = self._psutil.cpu_count(logical=True)
        logical_cores = max(int(logical_cores_raw or 0), 1)

        cpu_host_percent = min(
            100.0,
            max(0.0, cpu_process_percent / logical_cores),
        )

        process_count = len(live_processes)
        child_process_count = max(0, process_count - 1)

        status_parts = ["GOW process tree telemetry available"]
        if child_discovery_failed:
            status_parts.append("child discovery was partially unavailable")
        if inaccessible_processes:
            status_parts.append(
                f"{inaccessible_processes} metric read(s) were inaccessible"
            )

        return GowProcessResourceSnapshot(
            captured_at=captured_at,
            root_pid=self._root_pid,
            root_name=self._safe_name(root_process),
            available=True,
            status="; ".join(status_parts),
            cpu_process_percent=cpu_process_percent,
            cpu_host_percent=cpu_host_percent,
            memory_rss_bytes=memory_rss_bytes,
            process_count=process_count,
            child_process_count=child_process_count,
            thread_count=thread_count,
            logical_cores=logical_cores,
            active_pids=tuple(sorted(live_processes)),
            inaccessible_processes=inaccessible_processes,
        )

    def _process_for_pid(self, pid: int) -> Any:
        cached = self._process_cache.get(pid)
        if cached is not None:
            return cached

        process = self._psutil.Process(pid)
        return self._cache_process(process)

    def _reuse_or_cache(self, process: Any) -> Any:
        pid = int(process.pid)
        cached = self._process_cache.get(pid)

        if cached is not None and self._same_process(cached, process):
            return cached

        return self._cache_process(process)

    def _cache_process(self, process: Any) -> Any:
        pid = int(process.pid)
        self._process_cache[pid] = process

        try:
            process.cpu_percent(interval=None)
        except _PROCESS_ERRORS:
            pass

        return process

    def _is_live(self, process: Any) -> bool:
        try:
            if not bool(process.is_running()):
                return False

            status = process.status()
        except _PROCESS_ERRORS:
            return False

        zombie_status = getattr(self._psutil, "STATUS_ZOMBIE", "zombie")
        return status != zombie_status

    @staticmethod
    def _safe_create_time(process: Any) -> float | None:
        try:
            return float(process.create_time())
        except _PROCESS_ERRORS:
            return None

    def _same_process(self, first: Any, second: Any) -> bool:
        if int(first.pid) != int(second.pid):
            return False

        first_created = self._safe_create_time(first)
        second_created = self._safe_create_time(second)

        if first_created is None or second_created is None:
            return first is second

        return first_created == second_created

    @staticmethod
    def _safe_name(process: Any) -> str | None:
        try:
            name = str(process.name()).strip()
        except _PROCESS_ERRORS:
            return None

        return name or None


def discover_gow_process_pid(
    *,
    results_root: str | Path,
    run_id: str | None = None,
    psutil_module: Any = psutil,
    exclude_pids: tuple[int, ...] = (),
) -> int | None:
    """Find the active GOW launcher responsible for a monitored result root.

    A run-id match is authoritative. If the run id is not present in the
    command line, an outdir-only match is accepted only when it is unambiguous.
    """

    process_iter = getattr(psutil_module, "process_iter", None)
    if process_iter is None:
        return None

    root_key = (
        str(Path(results_root).expanduser().resolve())
        .replace("\\", "/")
        .casefold()
    )
    run_key = str(run_id or "").strip().casefold()
    excluded = set(exclude_pids)

    run_matches: list[tuple[float, int]] = []
    root_matches: list[tuple[float, int]] = []

    try:
        processes = process_iter(
            attrs=("pid", "name", "cmdline", "create_time")
        )
    except (TypeError, OSError):
        try:
            processes = process_iter()
        except Exception:
            return None

    for process in processes:
        try:
            info = getattr(process, "info", {}) or {}
            pid = int(info.get("pid", getattr(process, "pid", 0)))
        except (TypeError, ValueError, AttributeError):
            continue

        if pid < 1 or pid in excluded:
            continue

        raw_name = info.get("name")
        if raw_name is None:
            try:
                raw_name = process.name()
            except Exception:
                raw_name = ""

        raw_cmdline = info.get("cmdline")
        if raw_cmdline is None:
            try:
                raw_cmdline = process.cmdline()
            except Exception:
                raw_cmdline = ()

        if isinstance(raw_cmdline, str):
            tokens = (raw_cmdline,)
        else:
            try:
                tokens = tuple(str(item) for item in raw_cmdline or ())
            except TypeError:
                tokens = ()

        name = str(raw_name or "").strip().casefold()
        token_names = {
            Path(token.strip('"')).name.casefold()
            for token in tokens
            if token.strip()
        }
        module_launch = any(
            tokens[index].casefold() == "-m"
            and tokens[index + 1].casefold() == "gow"
            for index in range(max(0, len(tokens) - 1))
        )
        is_gow_launcher = (
            name in {"gow", "gow.exe"}
            or bool(token_names & {"gow", "gow.exe"})
            or module_launch
        )
        if not is_gow_launcher:
            continue

        command = " ".join(tokens).replace("\\", "/").casefold()
        root_match = bool(root_key and root_key in command)
        run_match = bool(run_key and run_key in command)

        if not root_match and not run_match:
            continue

        created_raw = info.get("create_time", 0.0)
        try:
            created_at = float(created_raw or 0.0)
        except (TypeError, ValueError):
            created_at = 0.0

        if run_match:
            run_matches.append((created_at, pid))
        elif root_match:
            root_matches.append((created_at, pid))

    if run_matches:
        return max(run_matches)[1]

    if len(root_matches) == 1:
        return root_matches[0][1]

    return None
