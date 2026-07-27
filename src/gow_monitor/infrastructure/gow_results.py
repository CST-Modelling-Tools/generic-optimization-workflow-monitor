from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gow_monitor.domain import (
    ObjectiveDirection,
    RunReference,
    RunSnapshot,
    RunState,
)


@dataclass(frozen=True, slots=True)
class GowPathResolution:
    selected_path: Path
    results_root: Path
    runs_root: Path
    direct_run_root: Path | None = None


class GowFilesystemRunReader:
    """Read GOW artifacts from an output root or any nested folder."""

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
        if not run.run_root.is_dir():
            return RunState.UNKNOWN
        records = self._records_by_attempt(run.run_root)
        if not records:
            return RunState.WAITING
        if (run.run_root / "results.jsonl").is_file():
            return RunState.COMPLETED
        return RunState.RUNNING

    def snapshot_of(self, run: RunReference) -> RunSnapshot:
        records = self._records_by_attempt(run.run_root)
        failed = sum(
            1
            for record in records.values()
            if self._fitness_status(record) != "ok"
        )
        source_paths = {
            str(record.get("_monitor_source", ""))
            for record in records.values()
            if record.get("_monitor_source")
        }
        return RunSnapshot(
            reference=run,
            state=self.state_of(run),
            evaluation_count=len(records),
            failed_evaluations=failed,
            result_sources=len(source_paths),
        )

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
    def _fitness_status(payload: dict[str, Any]) -> str:
        fitness = payload.get("fitness")
        if isinstance(fitness, dict):
            return str(fitness.get("status", "unknown")).lower()
        return str(payload.get("status", "unknown")).lower()

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
