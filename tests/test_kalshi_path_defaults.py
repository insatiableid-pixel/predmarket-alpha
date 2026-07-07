from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_script(relative_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, REPO / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_manual_drop_path_uses_configurable_root(monkeypatch, tmp_path: Path) -> None:
    from predmarket.shared_helpers import manual_drop_path

    root = tmp_path / "manual"
    monkeypatch.setenv("PREDMARKET_MANUAL_DROPS_ROOT", str(root))

    assert manual_drop_path("kalshi_ticks") == root / "kalshi_ticks"


def test_default_roots_are_home_relative() -> None:
    from predmarket.shared_helpers import DEFAULT_MANUAL_DROPS_ROOT, DEFAULT_PROJECTS_ROOT

    assert DEFAULT_MANUAL_DROPS_ROOT == Path.home() / "manual_drops"
    assert DEFAULT_PROJECTS_ROOT == Path.home() / "projects"
    source = (REPO / "predmarket" / "shared_helpers.py").read_text(encoding="utf-8")
    assert 'Path("/home/mrwatson/manual_drops")' not in source
    assert 'Path("/home/mrwatson/projects")' not in source


def test_manual_drop_specific_override_wins(monkeypatch, tmp_path: Path) -> None:
    from predmarket.shared_helpers import manual_drop_path

    root = tmp_path / "manual"
    override = tmp_path / "specific"
    monkeypatch.setenv("PREDMARKET_MANUAL_DROPS_ROOT", str(root))
    monkeypatch.setenv("UNIT_SPECIFIC_PATH", str(override))

    assert manual_drop_path("kalshi_ticks", env_vars=("UNIT_SPECIFIC_PATH",)) == override


def test_fable_collector_defaults_follow_manual_drop_root(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "portable-manual-drops"
    monkeypatch.setenv("PREDMARKET_MANUAL_DROPS_ROOT", str(root))

    builder = load_script("scripts/kalshi_labeled_observation_builder.py", "_path_default_builder")
    backtest = load_script("scripts/kalshi_labeled_oos_backtest.py", "_path_default_backtest")
    passive = load_script(
        "scripts/kalshi_passive_liquidity_paper_fill_loop.py", "_path_default_passive"
    )
    tick = load_script("scripts/kalshi_tick_recorder.py", "_path_default_tick")
    line_moves = load_script(
        "scripts/kalshi_sports_line_move_delta_logger.py", "_path_default_line_moves"
    )
    archive = load_script("scripts/kalshi_resolved_archive_backfill.py", "_path_default_archive")

    assert builder.DEFAULT_PENDING_DIR == root / "kalshi_oos_pending"
    assert builder.DEFAULT_LABEL_DIR == root / "kalshi_oos_labels"
    assert builder.DEFAULT_SETTLED_RAW_DIR == root / "kalshi_oos_settlements"
    assert (
        builder.DEFAULT_SETTLED_SNAPSHOT_PATH
        == root / "kalshi_oos_settlements" / "kalshi_settled_markets_latest.json"
    )
    assert backtest.DEFAULT_LABEL_DIR == root / "kalshi_oos_labels"
    assert passive.DEFAULT_STATE_DIR == root / "kalshi_passive_liquidity_paper_fills"
    assert tick.DEFAULT_JSONL_DIR == root / "kalshi_ticks"
    assert line_moves.DEFAULT_STATE_DIR == root / "kalshi_sports_line_moves"
    assert archive.DEFAULT_RAW_DIR == root / "kalshi_resolved_archive_backfill"


def test_script_specific_path_overrides_follow_env(monkeypatch, tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    tick_dir = tmp_path / "ticks"
    monkeypatch.setenv("KALSHI_LABELED_OOS_LABEL_DIR", str(label_dir))
    monkeypatch.setenv("KALSHI_TICK_RECORDER_JSONL_DIR", str(tick_dir))

    backtest = load_script("scripts/kalshi_labeled_oos_backtest.py", "_path_override_backtest")
    tick = load_script("scripts/kalshi_tick_recorder.py", "_path_override_tick")

    assert backtest.DEFAULT_LABEL_DIR == label_dir
    assert tick.DEFAULT_JSONL_DIR == tick_dir


def test_always_on_collector_has_no_machine_specific_home_paths() -> None:
    text = (REPO / "scripts" / "kalshi_always_on_collector.py").read_text(encoding="utf-8")

    assert "/home/mrwatson" not in text


def test_makefile_uses_configurable_roots_for_local_data_paths() -> None:
    text = (REPO / "Makefile").read_text(encoding="utf-8")

    assert "PREDMARKET_MANUAL_DROPS_ROOT ?=" in text
    assert "PREDMARKET_PROJECTS_ROOT ?=" in text
    assert "/home/mrwatson/manual_drops" not in text
    assert "/home/mrwatson/projects" not in text
    assert "/mnt/c/Users/mrwat" not in text


def test_donor_bridge_defaults_do_not_hardcode_local_roots() -> None:
    inventory = (REPO / "predmarket" / "source_inventory.py").read_text(encoding="utf-8")
    wrappers = (REPO / "predmarket" / "external_artifact_wrappers.py").read_text(
        encoding="utf-8"
    )

    assert "/home/mrwatson/manual_drops" not in inventory
    assert "/home/mrwatson/projects" not in inventory
    assert "/home/mrwatson/manual_drops" not in wrappers
    assert "manual_drop_path(\"predmarket_external_artifacts\")" in wrappers


def test_sports_consensus_scripts_do_not_hardcode_local_roots() -> None:
    for path in sorted((REPO / "scripts").glob("kalshi_sports_consensus_*.py")):
        text = path.read_text(encoding="utf-8")
        assert "/home/mrwatson/manual_drops" not in text, path
        assert "/home/mrwatson/projects" not in text, path


def test_sports_evidence_scripts_do_not_hardcode_local_roots() -> None:
    paths = [
        "scripts/kalshi_atp_proxy_observation_loop.py",
        "scripts/kalshi_sports_proxy_observation_loop.py",
        "scripts/kalshi_sports_microstructure_observation_loop.py",
        "scripts/kalshi_sports_proxy_feature_model_falsification.py",
        "scripts/kalshi_sports_proxy_capacity_correlation_decay.py",
    ]

    for relative in paths:
        text = (REPO / relative).read_text(encoding="utf-8")
        assert "/home/mrwatson/manual_drops" not in text, relative
        assert "/home/mrwatson/projects" not in text, relative


def test_core_capture_reference_defaults_do_not_hardcode_local_roots() -> None:
    paths = [
        "predmarket/kalshi_universe_scan.py",
        "predmarket/kalshi_manual_drop_capture.py",
        "predmarket/sports_consensus_reference_builder.py",
        "predmarket/type2_candidate_disposition.py",
        "predmarket/type2_reference_builder.py",
        "scripts/kalshi_paper_settlement_reconcile.py",
        "scripts/kalshi_near_resolution_flow_terms_capture.py",
        "scripts/kalshi_ghost_listing_depth_diagnostic.py",
    ]

    for relative in paths:
        text = (REPO / relative).read_text(encoding="utf-8")
        assert "/home/mrwatson/manual_drops" not in text, relative
        assert "/home/mrwatson/projects" not in text, relative
        assert "/mnt/c/Users/mrwat" not in text, relative


def test_sports_consensus_key_file_default_follows_manual_drop_root(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "manual"
    override = tmp_path / "secrets" / "odds-key.txt"
    monkeypatch.setenv("PREDMARKET_MANUAL_DROPS_ROOT", str(root))

    builder = load_script(
        "predmarket/sports_consensus_reference_builder.py",
        "_path_default_sports_consensus_builder",
    )

    assert builder.DEFAULT_KEY_FILE == root / "secrets" / "the_odds_api_key.txt"

    monkeypatch.setenv("KALSHI_SPORTS_CONSENSUS_KEY_FILE", str(override))
    overridden = load_script(
        "predmarket/sports_consensus_reference_builder.py",
        "_path_override_sports_consensus_builder",
    )

    assert overridden.DEFAULT_KEY_FILE == override


def test_world_cup_atp_replay_defaults_do_not_hardcode_local_roots() -> None:
    paths = [
        "scripts/kalshi_world_cup_proxy_observation_loop.py",
        "scripts/kalshi_world_cup_proxy_feature_model_falsification.py",
        "scripts/kalshi_world_cup_outcome_independence_diagnostic.py",
        "scripts/kalshi_atp_proxy_evidence_gate.py",
        "scripts/kalshi_sports_proxy_research_candidate_replay.py",
        "scripts/kalshi_sports_blocker_clearance_cycle.py",
    ]

    for relative in paths:
        text = (REPO / relative).read_text(encoding="utf-8")
        assert "/home/mrwatson/manual_drops" not in text, relative
        assert "/home/mrwatson/projects" not in text, relative


def test_sports_feature_packet_defaults_do_not_hardcode_local_roots() -> None:
    text = (REPO / "scripts/kalshi_sports_proxy_feature_packet.py").read_text(
        encoding="utf-8"
    )

    assert "/home/mrwatson/manual_drops" not in text
    assert "/home/mrwatson/projects" not in text


def test_ev_overlay_local_scout_defaults_do_not_hardcode_local_roots() -> None:
    paths = [
        "scripts/kalshi_ev_nfl_overlay_assembler.py",
        "scripts/kalshi_ev_local_contract_evidence_scout.py",
    ]

    for relative in paths:
        text = (REPO / relative).read_text(encoding="utf-8")
        assert "/home/mrwatson/manual_drops" not in text, relative
        assert "/home/mrwatson/projects" not in text, relative


def test_contract_ev_ledger_defaults_do_not_hardcode_local_roots(monkeypatch, tmp_path: Path) -> None:
    manual_root = tmp_path / "manual"
    projects_root = tmp_path / "projects"
    monkeypatch.setenv("PREDMARKET_MANUAL_DROPS_ROOT", str(manual_root))
    monkeypatch.setenv("PREDMARKET_PROJECTS_ROOT", str(projects_root))

    ledger = load_script("scripts/kalshi_contract_ev_ledger.py", "_path_default_ev_ledger")
    text = (REPO / "scripts" / "kalshi_contract_ev_ledger.py").read_text(encoding="utf-8")

    assert "/home/mrwatson/manual_drops" not in text
    assert "/home/mrwatson/projects" not in text
    assert ledger.OFFICIAL_TERMS_SNAPSHOT_PATHS[0] == manual_root / "kalshi"
    assert ledger.CALIBRATED_PROBABILITY_OVERLAY_PATHS[0] == (
        manual_root / "kalshi_ev_probabilities"
    )
    assert ledger.CONTRACT_MAPPING_OVERLAY_PATHS[0] == (
        manual_root / "kalshi_ev_contract_mappings"
    )
    assert ledger.DEFAULT_NFL_FAIR_LINE_REVIEW_PATH == (
        projects_root
        / "nfl_quant_glm51_greenfield"
        / "docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.json"
    )


def test_macro_unlock_scout_defaults_do_not_hardcode_local_roots(
    monkeypatch, tmp_path: Path
) -> None:
    manual_root = tmp_path / "manual"
    projects_root = tmp_path / "projects"
    monkeypatch.setenv("PREDMARKET_MANUAL_DROPS_ROOT", str(manual_root))
    monkeypatch.setenv("PREDMARKET_PROJECTS_ROOT", str(projects_root))

    scout = load_script("scripts/codex_macro_unlock_scout.py", "_path_default_unlock_scout")
    text = (REPO / "scripts" / "codex_macro_unlock_scout.py").read_text(encoding="utf-8")

    assert "/home/mrwatson/manual_drops" not in text
    assert "/home/mrwatson/projects" not in text
    assert scout.DEFAULT_MANUAL_DROPS == manual_root
    assert scout.DEFAULT_MLB_REPO == projects_root / "mlb-platform"
    assert scout.local_make_command("atp-oracle", "macro-status") == (
        f"cd {projects_root / 'atp-oracle'} && make macro-status"
    )


def test_crypto_weather_probability_defaults_do_not_hardcode_local_roots() -> None:
    paths = [
        "scripts/kalshi_crypto_proxy_feature_packet.py",
        "scripts/kalshi_crypto_proxy_observation_loop.py",
        "scripts/kalshi_crypto_proxy_feature_model_falsification.py",
        "scripts/kalshi_crypto_proxy_research_candidate_replay.py",
        "scripts/kalshi_crypto_proxy_capacity_correlation_decay.py",
        "scripts/kalshi_weather_proxy_feature_packet.py",
        "scripts/kalshi_weather_proxy_observation_loop.py",
        "scripts/kalshi_weather_proxy_feature_model_falsification.py",
        "scripts/kalshi_weather_proxy_research_candidate_replay.py",
        "scripts/kalshi_weather_proxy_capacity_correlation_decay.py",
        "scripts/kalshi_probability_breadth_scout.py",
        "scripts/kalshi_ev_queue_robustness.py",
    ]

    for relative in paths:
        text = (REPO / relative).read_text(encoding="utf-8")
        assert "/home/mrwatson/manual_drops" not in text, relative
        assert "/home/mrwatson/projects" not in text, relative
