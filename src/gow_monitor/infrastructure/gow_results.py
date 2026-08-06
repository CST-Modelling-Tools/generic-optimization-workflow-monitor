from __future__ import annotations

import heapq
import json
import math
import re
import statistics
import threading
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gow_monitor.domain import (
    EvaluationPoint,
    ObjectiveDirection,
    PopulationDiversityPoint,
    RunReference,
    RunSnapshot,
    RunState,
)
from gow_monitor.domain.diversity import confidence_ellipse_area


@dataclass(frozen=True, slots=True)
class GowPathResolution:
    selected_path: Path
    results_root: Path
    runs_root: Path
    direct_run_root: Path | None = None


class _RunningMedian:
    """Track a numeric median in O(log n) per inserted value."""

    def __init__(self) -> None:
        self._lower: list[float] = []
        self._upper: list[float] = []

    def add(self, value: float) -> None:
        if not self._lower or value <= -self._lower[0]:
            heapq.heappush(self._lower, -value)
        else:
            heapq.heappush(self._upper, value)

        if len(self._lower) > len(self._upper) + 1:
            heapq.heappush(self._upper, -heapq.heappop(self._lower))
        elif len(self._upper) > len(self._lower):
            heapq.heappush(self._lower, -heapq.heappop(self._upper))

    @property
    def value(self) -> float | None:
        if not self._lower:
            return None
        if len(self._lower) == len(self._upper):
            return (-self._lower[0] + self._upper[0]) / 2.0
        return -self._lower[0]


@dataclass(slots=True)
class _GenerationMoments:
    count: int = 0
    evaluation: int = 0
    sums: dict[str, float] = field(default_factory=dict)
    cross_sums: dict[tuple[str, str], float] = field(
        default_factory=dict
    )

    def add(
        self,
        *,
        evaluation: int,
        parameters: dict[str, float],
    ) -> None:
        self.count += 1
        self.evaluation = max(self.evaluation, evaluation)
        names = tuple(sorted(parameters))

        for name in names:
            self.sums[name] = (
                self.sums.get(name, 0.0) + parameters[name]
            )

        for left_index, left_name in enumerate(names):
            left_value = parameters[left_name]
            for right_name in names[left_index:]:
                key = (left_name, right_name)
                self.cross_sums[key] = (
                    self.cross_sums.get(key, 0.0)
                    + left_value * parameters[right_name]
                )


@dataclass(frozen=True, slots=True)
class _CachedShardRun:
    fingerprint: tuple[tuple[str, int, int], ...]
    snapshot: RunSnapshot
    history: tuple[EvaluationPoint, ...]


class _ShardRunAccumulator:
    _MAX_HISTORY_POINTS = 4096
    _RECENT_HISTORY_POINTS = 100

    def __init__(
        self,
        run: RunReference,
    ) -> None:
        self.run = run
        self.evaluation_count = 0
        self.failed_evaluations = 0
        self.successful_evaluations = 0
        self.objective_sum = 0.0
        self.latest_objective: float | None = None
        self.best_objective: float | None = None
        self.best_candidate_id: str | None = None
        self.run_started_at: float | None = None
        self.run_finished_at: float | None = None
        self.median = _RunningMedian()
        self.sample_step = 1
        self.sampled_history: list[EvaluationPoint] = []
        self.recent_history: deque[EvaluationPoint] = deque(
            maxlen=self._RECENT_HISTORY_POINTS
        )
        self.seen_keys: set[str] = set()
        self.parameterized_count = 0
        self.parameter_presence: dict[str, int] = {}
        self.parameter_minima: dict[str, float] = {}
        self.parameter_maxima: dict[str, float] = {}
        self.generations: dict[int, _GenerationMoments] = {}

    def consume(
        self,
        payload: dict[str, Any],
        *,
        source: Path,
    ) -> None:
        key = GowFilesystemRunReader._record_key(
            payload,
            source,
        )
        if key in self.seen_keys:
            return
        self.seen_keys.add(key)

        self.evaluation_count += 1
        evaluation = self.evaluation_count
        status = GowFilesystemRunReader._fitness_status(payload)
        objective = (
            GowFilesystemRunReader._fitness_objective(payload)
            if status == "ok"
            else None
        )
        candidate_id = GowFilesystemRunReader._candidate_id(payload)
        generation_id = GowFilesystemRunReader._generation_id(payload)
        started_at = GowFilesystemRunReader._timestamp_value(
            payload.get("started_at")
        )
        finished_at = GowFilesystemRunReader._timestamp_value(
            payload.get("finished_at")
        )

        if started_at is not None:
            self.run_started_at = (
                started_at
                if self.run_started_at is None
                else min(self.run_started_at, started_at)
            )
        if finished_at is not None:
            self.run_finished_at = (
                finished_at
                if self.run_finished_at is None
                else max(self.run_finished_at, finished_at)
            )

        if status != "ok":
            self.failed_evaluations += 1

        if objective is not None:
            self.successful_evaluations += 1
            self.objective_sum += objective
            self.latest_objective = objective
            self.median.add(objective)

            if self.best_objective is None:
                self.best_objective = objective
                self.best_candidate_id = candidate_id
            elif self.run.direction is ObjectiveDirection.MAXIMIZE:
                if objective > self.best_objective:
                    self.best_objective = objective
                    self.best_candidate_id = candidate_id
            elif objective < self.best_objective:
                self.best_objective = objective
                self.best_candidate_id = candidate_id

        mean_so_far = (
            self.objective_sum / self.successful_evaluations
            if self.successful_evaluations
            else None
        )
        point = EvaluationPoint(
            evaluation=evaluation,
            candidate_id=candidate_id,
            status=status,
            objective=objective,
            best_so_far=self.best_objective,
            mean_so_far=mean_so_far,
            median_so_far=self.median.value,
            generation_id=generation_id,
        )
        self.recent_history.append(point)

        if evaluation == 1 or evaluation % self.sample_step == 0:
            self.sampled_history.append(point)
            if len(self.sampled_history) > self._MAX_HISTORY_POINTS:
                self.sampled_history = self.sampled_history[::2]
                self.sample_step *= 2

        parameters = dict(
            GowFilesystemRunReader._parameter_items(payload)
        )
        if generation_id is not None and parameters:
            self._consume_parameters(
                evaluation=evaluation,
                generation_id=generation_id,
                parameters=parameters,
            )

    def _consume_parameters(
        self,
        *,
        evaluation: int,
        generation_id: int,
        parameters: dict[str, float],
    ) -> None:
        self.parameterized_count += 1

        for name, value in parameters.items():
            self.parameter_presence[name] = (
                self.parameter_presence.get(name, 0) + 1
            )
            self.parameter_minima[name] = min(
                value,
                self.parameter_minima.get(name, value),
            )
            self.parameter_maxima[name] = max(
                value,
                self.parameter_maxima.get(name, value),
            )

        generation = self.generations.setdefault(
            generation_id,
            _GenerationMoments(),
        )
        generation.add(
            evaluation=evaluation,
            parameters=parameters,
        )

    def history(self) -> tuple[EvaluationPoint, ...]:
        merged = {
            point.evaluation: point
            for point in self.sampled_history
        }
        merged.update(
            {
                point.evaluation: point
                for point in self.recent_history
            }
        )
        if self.recent_history:
            latest = self.recent_history[-1]
            merged[latest.evaluation] = latest
        return tuple(merged[index] for index in sorted(merged))

    def diversity(self) -> tuple[PopulationDiversityPoint, ...]:
        if self.parameterized_count == 0:
            return ()

        common_names = tuple(
            sorted(
                name
                for name, count in self.parameter_presence.items()
                if count == self.parameterized_count
            )
        )
        active_names = tuple(
            name
            for name in common_names
            if not math.isclose(
                self.parameter_minima[name],
                self.parameter_maxima[name],
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        )
        observations: list[PopulationDiversityPoint] = []

        for generation_id in sorted(self.generations):
            generation = self.generations[generation_id]
            covariance = self._normalized_covariance(
                generation,
                active_names,
            )
            spread = sum(
                math.sqrt(max(0.0, covariance[index][index]))
                for index in range(len(covariance))
            )
            observations.append(
                PopulationDiversityPoint(
                    generation_id=generation_id,
                    evaluation=generation.evaluation,
                    spread=spread,
                    ellipse_area=confidence_ellipse_area(covariance),
                    population_size=generation.count,
                    active_dimensions=len(active_names),
                )
            )

        return tuple(observations)

    def _normalized_covariance(
        self,
        generation: _GenerationMoments,
        active_names: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        if generation.count < 2 or not active_names:
            return ()

        denominator = generation.count - 1
        rows: list[tuple[float, ...]] = []

        for left_name in active_names:
            row: list[float] = []
            left_range = (
                self.parameter_maxima[left_name]
                - self.parameter_minima[left_name]
            )
            for right_name in active_names:
                right_range = (
                    self.parameter_maxima[right_name]
                    - self.parameter_minima[right_name]
                )
                key = tuple(sorted((left_name, right_name)))
                cross_sum = generation.cross_sums.get(key, 0.0)
                raw_covariance = (
                    cross_sum
                    - (
                        generation.sums[left_name]
                        * generation.sums[right_name]
                        / generation.count
                    )
                ) / denominator
                row.append(
                    raw_covariance / (left_range * right_range)
                )
            rows.append(tuple(row))

        return tuple(rows)


class GowFilesystemRunReader:
    """Read GOW artifacts from an output root or any nested folder."""

    _shard_cache: dict[Path, _CachedShardRun] = {}
    _shard_cache_lock = threading.Lock()

    def __init__(self, selected_path: str | Path) -> None:
        self.resolution = self.resolve_selected_path(selected_path)
        self.selected_path = self.resolution.selected_path
        self.results_root = self.resolution.results_root
        self.runs_root = self.resolution.runs_root
        self.direct_run_root = self.resolution.direct_run_root

    @classmethod
    def resolve_selected_path(
        cls,
        selected_path: str | Path,
    ) -> GowPathResolution:
        selected = Path(selected_path).expanduser().resolve()

        if not selected.exists():
            raise FileNotFoundError(
                f"The selected path does not exist: {selected}"
            )
        if not selected.is_dir():
            raise NotADirectoryError(
                f"The selected path is not a directory: {selected}"
            )

        for current in (selected, *selected.parents):
            child_runs = current / "runs"
            if child_runs.is_dir():
                return GowPathResolution(
                    selected_path=selected,
                    results_root=current,
                    runs_root=child_runs,
                )

            if current.name.lower() == "runs":
                return GowPathResolution(
                    selected_path=selected,
                    results_root=current.parent,
                    runs_root=current,
                )

            if current.parent.name.lower() == "runs":
                return GowPathResolution(
                    selected_path=selected,
                    results_root=current.parent.parent,
                    runs_root=current.parent,
                    direct_run_root=current,
                )

        inferred_run = cls._infer_run_root_from_artifacts(selected)
        if inferred_run is not None:
            return GowPathResolution(
                selected_path=selected,
                results_root=inferred_run.parent,
                runs_root=inferred_run.parent,
                direct_run_root=inferred_run,
            )

        return GowPathResolution(
            selected_path=selected,
            results_root=selected,
            runs_root=selected / "runs",
        )

    @classmethod
    def _infer_run_root_from_artifacts(
        cls,
        selected: Path,
    ) -> Path | None:
        for current in (selected, *selected.parents):
            if cls._looks_like_run_root(current):
                return current
        return None

    @staticmethod
    def _looks_like_run_root(path: Path) -> bool:
        if not path.is_dir():
            return False
        if (path / "results.jsonl").is_file():
            return True
        if (path / "summary.json").is_file():
            return True
        try:
            return next(path.rglob("result.json"), None) is not None
        except OSError:
            return False

    def discover_runs(self) -> tuple[RunReference, ...]:
        if self.direct_run_root is not None:
            run_roots = (self.direct_run_root,)
        elif self.runs_root.is_dir():
            run_roots = tuple(
                path
                for path in self.runs_root.iterdir()
                if path.is_dir() and not path.name.startswith(".")
            )
        elif self._looks_like_run_root(self.selected_path):
            run_roots = (self.selected_path,)
        else:
            return ()

        references = [
            self._build_reference(run_root)
            for run_root in run_roots
        ]
        return tuple(
            sorted(references, key=lambda item: item.run_id.lower())
        )

    def state_of(self, run: RunReference) -> RunState:
        return self.snapshot_of(run).state

    @staticmethod
    def _state_from_records(
        run: RunReference,
        records: dict[str, dict[str, Any]],
    ) -> RunState:
        if not run.run_root.is_dir():
            return RunState.UNKNOWN
        if not records:
            return RunState.WAITING
        if (run.run_root / "results.jsonl").is_file():
            return RunState.COMPLETED
        return RunState.RUNNING

    def snapshot_of(self, run: RunReference) -> RunSnapshot:
        return self.snapshot_and_history_of(run)[0]

    def history_of(self, run: RunReference) -> tuple[EvaluationPoint, ...]:
        return self.snapshot_and_history_of(run)[1]

    def snapshot_and_history_of(
        self,
        run: RunReference,
    ) -> tuple[RunSnapshot, tuple[EvaluationPoint, ...]]:
        shard_paths = self._generation_shard_paths(run.run_root)
        if shard_paths:
            cached = self._snapshot_and_history_from_shards(
                run,
                shard_paths,
            )
            return cached.snapshot, cached.history

        records = self._records_by_attempt(run.run_root)
        return (
            self._snapshot_from_records(run, records),
            self._history_from_records(run, records),
        )

    def _snapshot_from_records(
        self,
        run: RunReference,
        records: dict[str, dict[str, Any]],
    ) -> RunSnapshot:
        failed = sum(
            1
            for record in records.values()
            if self._fitness_status(record) != "ok"
        )

        valid_results: list[tuple[str | None, float]] = []
        for record in records.values():
            if self._fitness_status(record) != "ok":
                continue
            objective = self._fitness_objective(record)
            if objective is None:
                continue
            valid_results.append((self._candidate_id(record), objective))

        objectives = [objective for _candidate_id, objective in valid_results]
        best_candidate_id: str | None = None
        best_objective: float | None = None
        latest_objective: float | None = None
        mean_objective: float | None = None
        median_objective: float | None = None

        if valid_results:
            best_selector = (
                max
                if run.direction is ObjectiveDirection.MAXIMIZE
                else min
            )
            best_candidate_id, best_objective = best_selector(
                valid_results,
                key=lambda item: item[1],
            )
            latest_objective = valid_results[-1][1]
            mean_objective = statistics.fmean(objectives)
            median_objective = statistics.median(objectives)

        source_paths = {
            str(record.get("_monitor_source", ""))
            for record in records.values()
            if record.get("_monitor_source")
        }
        started_values = tuple(
            timestamp
            for record in records.values()
            if (
                timestamp := self._timestamp_value(
                    record.get("started_at")
                )
            )
            is not None
        )
        finished_values = tuple(
            timestamp
            for record in records.values()
            if (
                timestamp := self._timestamp_value(
                    record.get("finished_at")
                )
            )
            is not None
        )
        metadata = self._metadata_for(run.run_id, run.run_root)
        return RunSnapshot(
            reference=run,
            state=self._state_from_records(run, records),
            evaluation_count=len(records),
            failed_evaluations=failed,
            result_sources=len(source_paths),
            successful_evaluations=len(valid_results),
            best_objective=best_objective,
            latest_objective=latest_objective,
            mean_objective=mean_objective,
            median_objective=median_objective,
            best_candidate_id=best_candidate_id,
            run_started_at=(
                min(started_values) if started_values else None
            ),
            run_finished_at=(
                max(finished_values) if finished_values else None
            ),
            planned_evaluations=self._nonnegative_int(
                metadata.get("max_evaluations")
            ),
            completed_generations=self._nonnegative_int(
                metadata.get("completed_generations")
            ),
        )

    def _history_from_records(
        self,
        run: RunReference,
        records: dict[str, dict[str, Any]],
    ) -> tuple[EvaluationPoint, ...]:
        history: list[EvaluationPoint] = []
        running_median = _RunningMedian()
        objective_sum = 0.0
        valid_count = 0
        best_so_far: float | None = None

        for evaluation, record in enumerate(records.values(), start=1):
            status = self._fitness_status(record)
            objective = (
                self._fitness_objective(record)
                if status == "ok"
                else None
            )

            if objective is not None:
                objective_sum += objective
                valid_count += 1
                running_median.add(objective)
                if best_so_far is None:
                    best_so_far = objective
                elif run.direction is ObjectiveDirection.MAXIMIZE:
                    best_so_far = max(best_so_far, objective)
                else:
                    best_so_far = min(best_so_far, objective)

            mean_so_far = (
                objective_sum / valid_count
                if valid_count
                else None
            )
            history.append(
                EvaluationPoint(
                    evaluation=evaluation,
                    candidate_id=self._candidate_id(record),
                    status=status,
                    objective=objective,
                    best_so_far=best_so_far,
                    mean_so_far=mean_so_far,
                    median_so_far=running_median.value,
                    generation_id=self._generation_id(record),
                    parameters=self._parameter_items(record),
                )
            )

        return tuple(history)

    @staticmethod
    def _generation_shard_paths(
        run_root: Path,
    ) -> tuple[Path, ...]:
        generation_root = run_root / "generations"
        if not generation_root.is_dir():
            return ()
        try:
            return tuple(sorted(generation_root.glob("g*.jsonl")))
        except OSError:
            return ()

    def _snapshot_and_history_from_shards(
        self,
        run: RunReference,
        shard_paths: tuple[Path, ...],
    ) -> _CachedShardRun:
        metadata_path = run.run_root / "summary.json"
        fingerprint_items: list[tuple[str, int, int]] = []

        for path in shard_paths:
            try:
                stat = path.stat()
            except OSError:
                continue
            fingerprint_items.append(
                (str(path), stat.st_size, stat.st_mtime_ns)
            )

        if metadata_path.is_file():
            try:
                stat = metadata_path.stat()
            except OSError:
                pass
            else:
                fingerprint_items.append(
                    (
                        str(metadata_path),
                        stat.st_size,
                        stat.st_mtime_ns,
                    )
                )

        fingerprint = tuple(fingerprint_items)
        cache_key = run.run_root.resolve()

        with self._shard_cache_lock:
            cached = self._shard_cache.get(cache_key)
            if cached is not None and cached.fingerprint == fingerprint:
                return cached

        accumulator = _ShardRunAccumulator(run)
        source_count = 0

        for shard_path in shard_paths:
            source_count += 1
            for line_number, payload in self._read_jsonl(shard_path):
                source = Path(f"{shard_path}#{line_number}")
                accumulator.consume(payload, source=source)

        metadata = self._metadata_for(run.run_id, run.run_root)
        finalized = bool(metadata.get("finalized", False))
        if finalized or (run.run_root / "results.jsonl").is_file():
            state = RunState.COMPLETED
        elif accumulator.evaluation_count:
            state = RunState.RUNNING
        else:
            state = RunState.WAITING

        mean_objective = (
            accumulator.objective_sum
            / accumulator.successful_evaluations
            if accumulator.successful_evaluations
            else None
        )
        history = accumulator.history()
        snapshot = RunSnapshot(
            reference=run,
            state=state,
            evaluation_count=accumulator.evaluation_count,
            failed_evaluations=accumulator.failed_evaluations,
            result_sources=source_count,
            successful_evaluations=(
                accumulator.successful_evaluations
            ),
            best_objective=accumulator.best_objective,
            latest_objective=accumulator.latest_objective,
            mean_objective=mean_objective,
            median_objective=accumulator.median.value,
            best_candidate_id=accumulator.best_candidate_id,
            run_started_at=accumulator.run_started_at,
            run_finished_at=accumulator.run_finished_at,
            planned_evaluations=self._nonnegative_int(
                metadata.get("max_evaluations")
            ),
            completed_generations=self._nonnegative_int(
                metadata.get("completed_generations")
            ),
            history_is_sampled=(
                accumulator.evaluation_count > len(history)
            ),
            population_diversity=accumulator.diversity(),
        )
        result = _CachedShardRun(
            fingerprint=fingerprint,
            snapshot=snapshot,
            history=history,
        )

        with self._shard_cache_lock:
            self._shard_cache[cache_key] = result

        return result

    @staticmethod
    def _timestamp_value(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            numeric = float(value)
            if math.isfinite(numeric) and numeric >= 0.0:
                return numeric
            return None

        text = str(value).strip()
        if not text:
            return None

        try:
            numeric = float(text)
        except ValueError:
            numeric = None
        if (
            numeric is not None
            and math.isfinite(numeric)
            and numeric >= 0.0
        ):
            return numeric

        normalized = (
            text[:-1] + "+00:00"
            if text.upper().endswith("Z")
            else text
        )
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        timestamp = parsed.timestamp()
        if not math.isfinite(timestamp) or timestamp < 0.0:
            return None
        return timestamp

    @staticmethod
    def _nonnegative_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def diagnostics(self) -> dict[str, object]:
        references = self.discover_runs()
        return {
            "selected_path": str(self.selected_path),
            "results_root": str(self.results_root),
            "runs_root": str(self.runs_root),
            "direct_run_root": (
                str(self.direct_run_root)
                if self.direct_run_root is not None
                else None
            ),
            "runs_found": len(references),
            "run_ids": [reference.run_id for reference in references],
        }

    def _build_reference(self, run_root: Path) -> RunReference:
        metadata = self._metadata_for(run_root.name, run_root)
        direction = self._parse_direction(metadata)
        problem_id = metadata.get("problem_id")
        if not isinstance(problem_id, str) or not problem_id.strip():
            problem_id = self._problem_id_from_first_result(run_root)

        return RunReference(
            run_id=run_root.name,
            run_root=run_root.resolve(),
            direction=direction,
            problem_id=problem_id,
        )

    def _metadata_for(
        self,
        run_id: str,
        run_root: Path,
    ) -> dict[str, Any]:
        for path in (
            run_root / "summary.json",
            self.results_root / "summary.json",
        ):
            payload = self._read_json_object(path)
            if not payload:
                continue
            payload_run_id = payload.get("run_id")
            if payload_run_id is None or str(payload_run_id) == run_id:
                return payload
        return {}

    @staticmethod
    def _parse_direction(
        metadata: dict[str, Any],
    ) -> ObjectiveDirection:
        objective = metadata.get("objective")
        raw_direction = (
            objective.get("direction")
            if isinstance(objective, dict)
            else metadata.get("direction")
        )
        try:
            return ObjectiveDirection(str(raw_direction).lower())
        except ValueError:
            return ObjectiveDirection.UNKNOWN

    def _problem_id_from_first_result(
        self,
        run_root: Path,
    ) -> str | None:
        shard_paths = self._generation_shard_paths(run_root)
        if shard_paths:
            for _line_number, record in self._read_jsonl(
                shard_paths[0]
            ):
                problem_id = record.get("problem_id")
                if isinstance(problem_id, str) and problem_id.strip():
                    return problem_id
                break

        for record in self._records_by_attempt(run_root).values():
            problem_id = record.get("problem_id")
            if isinstance(problem_id, str) and problem_id.strip():
                return problem_id
        return None

    def _records_by_attempt(
        self,
        run_root: Path,
    ) -> dict[str, dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}

        try:
            result_paths = sorted(run_root.rglob("result.json"))
        except OSError:
            result_paths = []

        for path in result_paths:
            payload = self._read_json_object(path)
            if payload:
                payload["_monitor_source"] = str(path)
                records[self._record_key(payload, path)] = payload

        final_results = run_root / "results.jsonl"
        for line_number, payload in self._read_jsonl(final_results):
            payload["_monitor_source"] = str(final_results)
            key_path = Path(f"{final_results}#{line_number}")
            records[self._record_key(payload, key_path)] = payload

        return records

    @staticmethod
    def _record_key(payload: dict[str, Any], source: Path) -> str:
        for key in ("attempt_id", "candidate_id"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return f"{key}:{value}"
        return f"source:{source}"

    @staticmethod
    def _candidate_id(payload: dict[str, Any]) -> str | None:
        value = payload.get("candidate_id")
        if value is None or not str(value).strip():
            return None
        return str(value)

    @staticmethod
    def _generation_id(payload: dict[str, Any]) -> int | None:
        raw_generation = payload.get("generation_id")
        if not isinstance(raw_generation, bool):
            try:
                generation = int(raw_generation)
            except (TypeError, ValueError):
                generation = -1
            if generation >= 0:
                return generation

        for key in ("candidate_local_id", "candidate_id"):
            value = payload.get(key)
            if value is None:
                continue
            match = re.search(r"(?:^|_)g(\d+)(?:_|$)", str(value))
            if match is not None:
                return int(match.group(1))
        return None

    @staticmethod
    def _parameter_items(
        payload: dict[str, Any],
    ) -> tuple[tuple[str, float], ...]:
        raw_parameters = payload.get("params")
        if not isinstance(raw_parameters, dict):
            return ()

        parameters: list[tuple[str, float]] = []
        for raw_name, raw_value in raw_parameters.items():
            if isinstance(raw_value, bool):
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            parameters.append((str(raw_name), value))

        return tuple(sorted(parameters))

    @staticmethod
    def _fitness_status(payload: dict[str, Any]) -> str:
        fitness = payload.get("fitness")
        if isinstance(fitness, dict):
            return str(fitness.get("status", "unknown")).lower()
        return str(payload.get("status", "unknown")).lower()

    @staticmethod
    def _fitness_objective(payload: dict[str, Any]) -> float | None:
        fitness = payload.get("fitness")
        raw_objective = (
            fitness.get("objective")
            if isinstance(fitness, dict)
            else payload.get("objective")
        )
        if isinstance(raw_objective, bool):
            return None
        try:
            objective = float(raw_objective)
        except (TypeError, ValueError):
            return None
        return objective if math.isfinite(objective) else None

    @staticmethod
    def _read_json_object(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _read_jsonl(
        path: Path,
    ) -> Iterator[tuple[int, dict[str, Any]]]:
        if not path.is_file():
            return
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                for line_number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        payload = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        yield line_number, payload
        except (OSError, UnicodeError):
            return
