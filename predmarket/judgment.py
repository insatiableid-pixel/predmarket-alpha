"""Structured judgment protocols for human-in-the-loop forecasting.

Implements Petropoulos et al. (2022) §2.10 — structured judgmental adjustments,
analyst calibration tracking, and multi-analyst aggregation.

Enhances the binary approve/reject workflow with confidence ratings,
structured reasoning capture, concern tracking, and per-analyst scoring.
"""

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("predmarket.judgment")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class JudgmentRequest:
    """Structured request for human judgment on a forecast.

    Attributes:
        contract_id: Market contract identifier.
        model_prob: Model's predicted probability.
        market_implied: Market-implied probability.
        edge: Estimated edge (model_prob - market_implied).
        category: Market category (political, econ, sports, etc.).
        venue: Exchange/market venue name.
        structured_questions: Pre-generated questions the analyst should answer.
    """

    contract_id: str
    model_prob: float
    market_implied: float
    edge: float
    category: str
    venue: str
    structured_questions: list[str] = field(default_factory=list)


@dataclass
class JudgmentResponse:
    """Analyst's structured judgment on a forecast.

    Attributes:
        contract_id: Market contract identifier.
        approved: Whether the analyst approves execution.
        confidence: Analyst's confidence in their judgment (0-1).
        reasoning: Free-text explanation of the judgment.
        concerns: List of specific concerns raised.
        override_probability: Optional probability override from the analyst.
        analyst_id: Identifier for the analyst.
        timestamp: Unix timestamp of the judgment.
    """

    contract_id: str
    approved: bool
    confidence: float = 0.5
    reasoning: str = ""
    concerns: list[str] = field(default_factory=list)
    override_probability: float | None = None
    analyst_id: str = ""
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Structured protocol
# ---------------------------------------------------------------------------


class StructuredJudgmentProtocol:
    """Generates structured judgment requests and validates responses.

    Implements the structured analogies approach from §2.10.3: rather than
    asking "approve yes/no?", the protocol generates specific questions that
    force the analyst to confront known failure modes.
    """

    # Category-specific question templates
    _QUESTIONS: dict[str, list[str]] = {
        "political": [
            "Is the base rate appropriate for this specific race/context?",
            "Are there recent developments (scandals, endorsements, court rulings) "
            "not captured by the model?",
            "Is the polling data recent and reliable, or stale/noisy?",
            "Does the market price reflect insider information the model lacks?",
            "Are there structural factors (gerrymandering, incumbency advantage) "
            "the model may misweight?",
        ],
        "econ": [
            "Is the base rate for this economic indicator appropriate?",
            "Has there been a regime change (policy shift, crisis) the model hasn't adapted to?",
            "Are leading indicators consistent with the model's forecast?",
            "Could central bank intervention or fiscal policy change the outcome?",
        ],
        "sports": [
            "Are there key player injuries or suspensions not reflected in the model?",
            "Is the venue/weather factor accounted for?",
            "Has the team's recent form changed significantly from historical data?",
        ],
        "default": [
            "Is the base rate appropriate for this market?",
            "Are there recent developments not captured by the model?",
            "Is the market price reflecting information the model lacks?",
            "Is the liquidity sufficient for reliable price discovery?",
        ],
    }

    def create_judgment_request(self, forecast_dict: dict[str, Any]) -> JudgmentRequest:
        """Generate a structured judgment request from a forecast.

        Args:
            forecast_dict: Forecast output with keys: contract_id, model_prob,
                market_implied, category, venue, status.

        Returns:
            JudgmentRequest with category-appropriate structured questions.
        """
        category = forecast_dict.get("category", "default")
        model_prob = forecast_dict.get("model_prob", 0.5)
        market_implied = forecast_dict.get("market_implied", 0.5)
        edge = model_prob - market_implied

        questions = self._QUESTIONS.get(category, self._QUESTIONS["default"]).copy()

        # Add edge-specific questions
        if abs(edge) > 0.10:
            questions.append(
                f"The detected edge is {edge:+.1%}. Is this edge genuine or an "
                f"artifact of model miscalibration?"
            )
        if abs(edge) < 0.03:
            questions.append(
                "The edge is below the minimum threshold. Is there a reason to "
                "believe the model is being too conservative?"
            )

        return JudgmentRequest(
            contract_id=forecast_dict.get("contract_id", ""),
            model_prob=model_prob,
            market_implied=market_implied,
            edge=edge,
            category=category,
            venue=forecast_dict.get("venue", ""),
            structured_questions=questions,
        )

    def validate_response(self, response: JudgmentResponse) -> bool:
        """Validate that a judgment response is well-formed and substantive.

        Returns False if reasoning is empty, confidence is outside [0,1],
        or an override probability is outside [0,1].
        """
        if not response.reasoning or len(response.reasoning.strip()) < 10:
            logger.warning(
                "Judgment for %s rejected: reasoning is empty or too short.",
                response.contract_id,
            )
            return False
        if not (0.0 <= response.confidence <= 1.0):
            logger.warning(
                "Judgment for %s rejected: confidence %.2f outside [0, 1].",
                response.contract_id,
                response.confidence,
            )
            return False
        if response.override_probability is not None and not (
            0.0 <= response.override_probability <= 1.0
        ):
            logger.warning(
                "Judgment for %s rejected: override probability outside [0, 1].",
                response.contract_id,
            )
            return False
        return True

    def aggregate_judgments(self, responses: list[JudgmentResponse]) -> JudgmentResponse:
        """Aggregate multiple analyst judgments into a single consensus.

        Uses median probability, union of concerns, and mean confidence.

        Args:
            responses: List of validated JudgmentResponse objects.

        Returns:
            Single consensus JudgmentResponse.

        Raises:
            ValueError: If responses is empty.
        """
        if not responses:
            raise ValueError("Cannot aggregate empty judgment list.")

        # Approval: majority vote
        approved = sum(1 for r in responses if r.approved) > len(responses) / 2

        # Probability: median of all estimates (including override if present)
        probs = []
        for r in responses:
            if r.override_probability is not None:
                probs.append(r.override_probability)
            else:
                probs.append(r.model_prob if hasattr(r, "model_prob") else 0.5)
        median_prob = float(np.median(probs))

        # Confidence: mean
        avg_confidence = float(np.mean([r.confidence for r in responses]))

        # Concerns: union (deduplicated)
        all_concerns = []
        seen = set()
        for r in responses:
            for c in r.concerns:
                c_lower = c.lower().strip()
                if c_lower not in seen:
                    seen.add(c_lower)
                    all_concerns.append(c)

        # Reasoning: concatenate
        combined_reasoning = " | ".join(f"[{r.analyst_id}]: {r.reasoning}" for r in responses)

        return JudgmentResponse(
            contract_id=responses[0].contract_id,
            approved=approved,
            confidence=avg_confidence,
            reasoning=combined_reasoning,
            concerns=all_concerns,
            override_probability=median_prob,
            analyst_id="AGGREGATE",
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# Analyst calibration tracker
# ---------------------------------------------------------------------------


class JudgmentTracker:
    """Tracks analyst judgment accuracy and calibration over time.

    Records each judgment alongside the actual outcome and computes
    per-analyst Brier scores, accuracy rates, confidence calibration,
    and calibration slope (regression of outcome on forecast probability).

    All data is persisted in a SQLite table `judgment_history`.
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(Path(__file__).resolve().parents[1] / "data" / "database.sqlite")
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS judgment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                analyst_id TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                approved INTEGER NOT NULL,
                confidence REAL NOT NULL,
                override_probability REAL,
                reasoning TEXT,
                actual_outcome INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def record(self, judgment: JudgmentResponse, actual_outcome: int):
        """Record a judgment alongside the resolved outcome.

        Args:
            judgment: The analyst's judgment.
            actual_outcome: Binary outcome (0 or 1).
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO judgment_history
                (timestamp, analyst_id, contract_id, approved, confidence,
                 override_probability, reasoning, actual_outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                judgment.timestamp,
                judgment.analyst_id,
                judgment.contract_id,
                int(judgment.approved),
                judgment.confidence,
                judgment.override_probability,
                judgment.reasoning,
                actual_outcome,
            ),
        )
        conn.commit()
        conn.close()

    def get_analyst_calibration(self, analyst_id: str) -> dict[str, float]:
        """Compute calibration metrics for a specific analyst.

        Returns:
            Dict with keys: brier_score, accuracy, avg_confidence,
            calibration_slope, n_judgments.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            SELECT override_probability, confidence, actual_outcome
            FROM judgment_history
            WHERE analyst_id = ? AND actual_outcome IS NOT NULL
            """,
            (analyst_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "brier_score": float("nan"),
                "accuracy": 0.0,
                "avg_confidence": 0.0,
                "calibration_slope": float("nan"),
                "n_judgments": 0,
            }

        probs = [r[0] if r[0] is not None else 0.5 for r in rows]
        confidences = [r[1] for r in rows]
        outcomes = [r[2] for r in rows]

        brier = float(np.mean([(p - o) ** 2 for p, o in zip(probs, outcomes)]))
        predicted_yes = [p > 0.5 for p in probs]
        actual_yes = [o == 1 for o in outcomes]
        accuracy = sum(1 for pred, act in zip(predicted_yes, actual_yes) if pred == act) / len(
            outcomes
        )

        # Calibration slope: regress outcome on forecast probability
        cal_slope = float("nan")
        if len(set(outcomes)) > 1:
            probs_arr = np.array(probs)
            outcomes_arr = np.array(outcomes, dtype=float)
            # Simple OLS: outcome = a + b * prob
            b = np.corrcoef(probs_arr, outcomes_arr)[0, 1]
            if not np.isnan(b):
                cal_slope = float(b * np.std(outcomes_arr) / max(np.std(probs_arr), 1e-10))

        return {
            "brier_score": brier,
            "accuracy": accuracy,
            "avg_confidence": float(np.mean(confidences)),
            "calibration_slope": cal_slope,
            "n_judgments": len(rows),
        }

    def get_best_analysts(self, n: int = 5) -> list[str]:
        """Return top analysts ranked by Brier score (lower is better).

        Args:
            n: Number of analysts to return.

        Returns:
            List of analyst_id strings, best first.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            SELECT analyst_id,
                   AVG((COALESCE(override_probability, 0.5) - actual_outcome) * 
                       (COALESCE(override_probability, 0.5) - actual_outcome)) as avg_brier
            FROM judgment_history
            WHERE actual_outcome IS NOT NULL
            GROUP BY analyst_id
            HAVING COUNT(*) >= 3
            ORDER BY avg_brier ASC
            LIMIT ?
            """,
            (n,),
        )
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return results
