from pathlib import Path


def test_no_legacy_execution_venues_in_runtime_source():
    forbidden = ("ForecastEx", "Interactive Brokers", "ib_insync", "CME Group")
    hits = []
    for path in Path("predmarket").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                hits.append(f"{path}:{token}")

    assert hits == []
