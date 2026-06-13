"""Research experiment queue for agent-generated alpha ideas."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ExperimentProposal:
    name: str
    hypothesis: str
    patch_ref: str
    experiment_config: Dict[str, Any]
    proposer: str = "agent"
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_ts: float = field(default_factory=time.time)
    status: str = "QUEUED"
    reason_code: str = ""


class ExperimentQueue:
    """Append-only JSONL queue for model, feature, and strategy proposals."""

    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir) / "research" / "experiment_queue.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def submit(self, proposal: ExperimentProposal) -> str:
        self._append(asdict(proposal))
        return proposal.proposal_id

    def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = self._read_all()
        if status is not None:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def record_result(
        self,
        proposal_id: str,
        status: str,
        report_ref: str = "",
        reason_code: str = "",
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        row = {
            "proposal_id": proposal_id,
            "updated_ts": time.time(),
            "status": status,
            "report_ref": report_ref,
            "reason_code": reason_code,
            "metrics": metrics or {},
        }
        self._append(row)

    def rejected_reason_seen(self, reason_code: str) -> bool:
        return any(
            row.get("status") == "REJECTED" and row.get("reason_code") == reason_code
            for row in self._read_all()
        )

    def has_similar_hypothesis(self, hypothesis: str) -> bool:
        normalized = " ".join(hypothesis.lower().split())
        return any(
            " ".join(str(row.get("hypothesis", "")).lower().split()) == normalized
            for row in self._read_all()
        )

    def _append(self, payload: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True, default=str) + "\n")

    def _read_all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows
