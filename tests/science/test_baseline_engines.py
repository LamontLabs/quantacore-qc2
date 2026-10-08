from __future__ import annotations

import copy
import hashlib
import inspect
import json
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from qc2_contracts.runtime import (
    canonical_content_hash,
    canonical_json_bytes,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

from qc2_science import (
    BaselineError,
    BaselineKind,
    InsufficientScoreableRows,
    PRIMARY_REPORTING_K,
    SECONDARY_REPORTING_K,
    build_feature_specs,
    evaluate_baseline_manifest,
    fixture_daily_profile,
    materialize_baseline_manifest,
    materialize_feature_registry,
    scoreable_intersection,
    select_top_k,
    select_top_percentile,
)

ROOT = Path(__file__).resolve().parents[2]
_VALID_FIXTURES = json.loads(
    (ROOT / "packages/contracts/fixtures/v1/valid.json").read_text(encoding="utf-8")
)
_SESSION = "2026-10-05"
_CUTOFF = "2026-10-05T20:00:00Z"
_FEATURES = {
    "return_1": ("fraction", "0.01"),
    "return_5": ("fraction", "0.02"),
    "return_20": ("fraction", "0.03"),
    "relative_volume": ("ratio", "1.25"),
    "breakout_proximity": ("fraction", "0.01"),
}
_VOLUME_CALIBRATION = {"relative_volume_lookback_sessions": 20}
_BREAKOUT_CALIBRATION = {"breakout_proximity_lookback_sessions": 20}
_COMPOSITE_CALIBRATION = {
    **_VOLUME_CALIBRATION,
    **_BREAKOUT_CALIBRATION,
}


def _fixture_contract(name: str) -> dict:
    return copy.deepcopy(
        next(
            item["payload"]
            for item in _VALID_FIXTURES
            if item["contract"] == name
        )
    )


def _build_feature_registry():
    profile = fixture_daily_profile()
    specs = build_feature_specs(profile)
    implementation_hash = hashlib.sha256(
        (ROOT / "packages/science/src/qc2_science/registry.py").read_bytes()
    ).hexdigest()
    return materialize_feature_registry(
        profile,
        definition_ids={spec.stable_key: new_uuidv7() for spec in specs},
        registry_id=new_uuidv7(),
        created_at=_CUTOFF,
        effective_from=_SESSION,
        implementation_hash=implementation_hash,
        environment_namespace="test",
    )


def _calibration_fixture(values: dict[str, int]) -> tuple[dict, tuple[dict, ...]]:
    setting_records = []
    setting_refs = []
    for setting_key, value in sorted(values.items()):
        setting = _fixture_contract("ConfigurationSetting")
        setting.update(
            {
                "id": new_uuidv7(),
                "created_at": _CUTOFF,
                "environment_namespace": "test",
                "setting_key": setting_key,
                "configuration_domain": "EPOCH_SCIENTIFIC",
                "effective_from": _SESSION,
                "value_hash": hashlib.sha256(
                    canonical_json_bytes(
                        {
                            "setting_key": setting_key,
                            "value": value,
                            "unit": "sessions",
                        }
                    )
                ).hexdigest(),
                "value_class": "EMPIRICAL_CALIBRATION_REQUIRED",
                "value_authority": "baseline_test_fixture",
                "fixture_only": True,
                "production_required": False,
                "required_capabilities": ["configuration_read"],
                "secret_reference_ref": None,
                "resource_budget_ref": None,
                "owner_approval_ref": None,
            }
        )
        setting["content_hash"] = canonical_content_hash(
            "ConfigurationSetting", setting
        )
        validate_contract("ConfigurationSetting", setting)
        verify_content_hash("ConfigurationSetting", setting)
        setting_records.append(setting)
        setting_refs.append(
            {
                "target_schema_name": "qc2.integrity_build.ConfigurationSetting.v1",
                "target_id": setting["id"],
                "content_hash": setting["content_hash"],
            }
        )

    configuration = _fixture_contract("ConfigurationManifest")
    configuration.update(
        {
            "id": new_uuidv7(),
            "created_at": _CUTOFF,
            "environment_namespace": "test",
            "configuration_domain": "EPOCH_SCIENTIFIC",
            "effective_from": _SESSION,
            "capability_scope": ["configuration_read"],
            "required_setting_keys": sorted(values),
            "setting_refs": setting_refs,
            "resource_budget_refs": [],
            "policy_hash": hashlib.sha256(
                canonical_json_bytes(
                    {"fixture_only": True, "setting_values": values}
                )
            ).hexdigest(),
            "unresolved_decision_refs": [],
            "fixture_only": True,
            "signed_by_owner": False,
        }
    )
    configuration["content_hash"] = canonical_content_hash(
        "ConfigurationManifest", configuration
    )
    validate_contract("ConfigurationManifest", configuration)
    verify_content_hash("ConfigurationManifest", configuration)
    return configuration, tuple(setting_records)


_FEATURE_REGISTRY_BUNDLE = _build_feature_registry()
_REGISTRY_REF = {
    "target_schema_name": "qc2.scientific_definitions.FeatureRegistry.v1",
    "target_id": _FEATURE_REGISTRY_BUNDLE.registry_contract["id"],
    "content_hash": _FEATURE_REGISTRY_BUNDLE.registry_contract["content_hash"],
}
_CALIBRATION_FIXTURES = {
    "volume": _calibration_fixture(_VOLUME_CALIBRATION),
    "breakout": _calibration_fixture(_BREAKOUT_CALIBRATION),
    "composite": _calibration_fixture(_COMPOSITE_CALIBRATION),
}


def _universe(instrument_ids: list[str]) -> dict:
    payload = _fixture_contract("UniverseManifest")
    payload.update(
        {
            "id": new_uuidv7(),
            "created_at": _CUTOFF,
            "session_id": _SESSION,
            "census_ref": {
                "target_schema_name": "qc2.identity_market.CandidateCensus.v1",
                "target_id": new_uuidv7(),
            },
            "data_bundle_ref": {
                "target_schema_name": "qc2.identity_market.DataBundle.v1",
                "target_id": new_uuidv7(),
            },
            "eligible_instrument_refs": [
                {
                    "target_schema_name": "qc2.identity_market.Instrument.v1",
                    "target_id": instrument_id,
                }
                for instrument_id in instrument_ids
            ],
            "unscorable_instrument_refs": [],
            "reason_counts": [],
            "cutoff": _CUTOFF,
        }
    )
    validate_contract("UniverseManifest", payload)
    return payload


def _snapshot(
    instrument_id: str,
    values: dict[str, str] | None = None,
    *,
    missing: dict[str, str] | None = None,
    extra_features: dict[str, str] | None = None,
) -> dict:
    payload = _fixture_contract("FeatureSnapshot")
    payload.update(
        {
            "id": new_uuidv7(),
            "created_at": "2026-10-05T20:01:00Z",
            "session_id": _SESSION,
            "instrument_ref": {
                "target_schema_name": "qc2.identity_market.Instrument.v1",
                "target_id": instrument_id,
            },
            "registry_ref": copy.deepcopy(_REGISTRY_REF),
            "feature_values": [],
            "decision_cutoff": _CUTOFF,
        }
    )
    normalized_values = dict(values or {})
    missing_values = dict(missing or {})
    for feature_id, (unit, default_value) in _FEATURES.items():
        row = {
            "feature_id": feature_id,
            "unit": unit,
            "output_dtype": "DECIMAL",
        }
        if feature_id in missing_values:
            row["missing_reason"] = missing_values[feature_id]
        else:
            row["value"] = normalized_values.get(feature_id, default_value)
        payload["feature_values"].append(row)
    for feature_id, value in (extra_features or {}).items():
        payload["feature_values"].append(
            {
                "feature_id": feature_id,
                "unit": "fraction",
                "output_dtype": "DECIMAL",
                "value": value,
            }
        )
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash("FeatureSnapshot", payload)
    validate_contract("FeatureSnapshot", payload)
    verify_content_hash("FeatureSnapshot", payload)
    return payload


def _manifest(
    kind: BaselineKind,
    *,
    parameter_values: dict[str, int] | None = None,
    seeds: tuple[str, ...] | None = None,
    environment_namespace: str = "test",
) -> dict:
    calibration_key = {
        BaselineKind.RELATIVE_VOLUME: "volume",
        BaselineKind.BREAKOUT_PROXIMITY: "breakout",
        BaselineKind.TRANSPARENT_COMPOSITE: "composite",
    }.get(kind)
    if calibration_key is None:
        parameter_refs = ()
    else:
        configuration, _ = _CALIBRATION_FIXTURES[calibration_key]
        parameter_refs = (
            {
                "target_schema_name": (
                    "qc2.integrity_build.ConfigurationManifest.v1"
                ),
                "target_id": configuration["id"],
                "content_hash": configuration["content_hash"],
            },
        )
    return materialize_baseline_manifest(
        kind,
        feature_registry_ref=_REGISTRY_REF,
        parameter_refs=parameter_refs,
        parameter_values=parameter_values,
        seed_values=seeds,
        manifest_id=new_uuidv7(),
        created_at=_CUTOFF,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace=environment_namespace,
    )


def _complete_snapshots(instrument_ids: list[str]) -> list[dict]:
    return [_snapshot(instrument_id) for instrument_id in instrument_ids]


def _rank_projection(run) -> tuple[tuple[str, int | None, Decimal | None], ...]:
    return tuple((row.instrument_id, row.rank, row.score) for row in run.rows)


def test_identical_universe_and_cutoff_produce_deterministic_ranks() -> None:
    instrument_ids = sorted(new_uuidv7() for _ in range(4))
    universe = _universe(instrument_ids)
    snapshots = _complete_snapshots(instrument_ids)
    manifest = _manifest(BaselineKind.MOMENTUM_5)

    first = evaluate_baseline_manifest(manifest, universe, snapshots).runs[0]
    reordered_universe = copy.deepcopy(universe)
    reordered_universe["eligible_instrument_refs"].reverse()
    second = evaluate_baseline_manifest(
        manifest,
        reordered_universe,
        list(reversed(snapshots)),
    ).runs[0]

    assert first == second
    assert first.session_id == _SESSION
    assert first.decision_cutoff.isoformat().replace("+00:00", "Z") == _CUTOFF
    assert first.scoreable_count == len(instrument_ids)
    assert first.unscorable_count == 0


def test_zero_denominator_and_missing_snapshot_keep_reason_coded_rows() -> None:
    instrument_ids = sorted(new_uuidv7() for _ in range(3))
    universe = _universe(instrument_ids)
    snapshots = [
        _snapshot(instrument_ids[0], {"relative_volume": "1.5"}),
        _snapshot(
            instrument_ids[1],
            missing={"relative_volume": "DIVISION_BY_ZERO"},
        ),
    ]
    run = evaluate_baseline_manifest(
        _manifest(
            BaselineKind.RELATIVE_VOLUME,
            parameter_values=_VOLUME_CALIBRATION,
        ),
        universe,
        snapshots,
    ).runs[0]

    rows = {row.instrument_id: row for row in run.rows}
    assert set(rows) == set(instrument_ids)
    assert run.scoreable_count == 1
    assert run.unscorable_count == 2
    assert rows[instrument_ids[1]].reason_codes == (
        "FEATURE_UNSCORABLE:relative_volume:DIVISION_BY_ZERO",
    )
    assert rows[instrument_ids[2]].reason_codes == ("FEATURE_SNAPSHOT_MISSING",)
    assert select_top_k(run, 1)[0].instrument_id == instrument_ids[0]
    with pytest.raises(InsufficientScoreableRows):
        select_top_k(run, 2)


def test_composite_uses_five_equal_midrank_percentiles_and_oriented_breakout() -> None:
    instrument_ids = sorted(new_uuidv7() for _ in range(3))
    universe = _universe(instrument_ids)
    rows = [
        {
            "return_1": "0",
            "return_5": "3",
            "return_20": "0",
            "relative_volume": "1",
            "breakout_proximity": "0.01",
        },
        {
            "return_1": "1",
            "return_5": "2",
            "return_20": "0",
            "relative_volume": "2",
            "breakout_proximity": "0",
        },
        {
            "return_1": "2",
            "return_5": "1",
            "return_20": "0",
            "relative_volume": "3",
            "breakout_proximity": "-0.01",
        },
    ]
    snapshots = [
        _snapshot(instrument_id, values)
        for instrument_id, values in zip(instrument_ids, rows, strict=True)
    ]
    manifest = _manifest(
        BaselineKind.TRANSPARENT_COMPOSITE,
        parameter_values=_COMPOSITE_CALIBRATION,
    )
    run = evaluate_baseline_manifest(manifest, universe, snapshots).runs[0]
    by_id = {row.instrument_id: row for row in run.rows}

    assert "each weight is 1/5" in manifest["algorithm"]
    assert (
        'Calibration parameters: {"breakout_proximity_lookback_sessions":20,'
        '"relative_volume_lookback_sessions":20}'
    ) in manifest["algorithm"]
    assert run.rows[0].instrument_id == instrument_ids[2]
    assert by_id[instrument_ids[2]].component_percentiles[-1][0] == "breakout_proximity"
    assert (
        by_id[instrument_ids[2]].component_percentiles[-1][1].quantize(
            Decimal("0.000001")
        )
        == Decimal("0.833333")
    )
    assert by_id[instrument_ids[0]].component_percentiles[-1][0] == "breakout_proximity"
    assert (
        by_id[instrument_ids[0]].component_percentiles[-1][1].quantize(
            Decimal("0.000001")
        )
        == Decimal("0.166667")
    )
    for row in run.rows:
        with localcontext() as context:
            context.prec = 64
            expected_score = sum(
                (percentile for _, percentile in row.component_percentiles),
                Decimal(0),
            ) / Decimal(5)
        assert row.score == expected_score


def test_all_ties_use_average_percentiles_and_stable_id_top_k() -> None:
    instrument_ids = sorted(new_uuidv7() for _ in range(4))
    universe = _universe(instrument_ids)
    snapshots = _complete_snapshots(instrument_ids)
    manifest = _manifest(
        BaselineKind.TRANSPARENT_COMPOSITE,
        parameter_values=_COMPOSITE_CALIBRATION,
    )
    old_symbols = {
        instrument_id: f"OLD{index}"
        for index, instrument_id in enumerate(instrument_ids)
    }
    new_symbols = {
        instrument_id: f"NEW{index}"
        for index, instrument_id in enumerate(instrument_ids)
    }

    old_run = evaluate_baseline_manifest(
        manifest,
        universe,
        snapshots,
        display_symbols_by_instrument_id=old_symbols,
    ).runs[0]
    renamed_run = evaluate_baseline_manifest(
        manifest,
        universe,
        snapshots,
        display_symbols_by_instrument_id=new_symbols,
    ).runs[0]

    assert [row.instrument_id for row in old_run.rows] == instrument_ids
    assert [row.instrument_id for row in renamed_run.rows] == instrument_ids
    assert _rank_projection(old_run) == _rank_projection(renamed_run)
    assert [row.display_symbol for row in renamed_run.rows] == [
        new_symbols[instrument_id] for instrument_id in instrument_ids
    ]
    assert {row.score for row in old_run.rows} == {Decimal("0.5")}
    assert {row.percentile for row in old_run.rows} == {Decimal("0.5")}
    assert PRIMARY_REPORTING_K == 10
    assert SECONDARY_REPORTING_K == (1, 5)
    assert [row.instrument_id for row in select_top_k(old_run, 2)] == instrument_ids[:2]
    assert len(select_top_percentile(old_run, Decimal("0.5"))) == len(instrument_ids)
    assert select_top_percentile(old_run, Decimal("0.6")) == ()
    with pytest.raises(InsufficientScoreableRows):
        select_top_k(old_run, 10)


def test_random_seed_set_is_preregistered_deterministic_and_never_selects_one_seed() -> None:
    instrument_ids = sorted(new_uuidv7() for _ in range(5))
    universe = _universe(instrument_ids)
    epoch_id = new_uuidv7()
    seeds = ("seed-c", "seed-a", "seed-b")
    manifest = _manifest(BaselineKind.RANDOM, seeds=seeds)
    snapshots = [
        _snapshot(
            instrument_id,
            extra_features={"future_outcome": "0.99"},
        )
        for instrument_id in instrument_ids
    ]

    execution = evaluate_baseline_manifest(
        manifest,
        universe,
        snapshots,
        seed_values=seeds,
        epoch_id=epoch_id,
    )
    reordered = evaluate_baseline_manifest(
        manifest,
        universe,
        list(reversed(snapshots)),
        seed_values=tuple(reversed(seeds)),
        epoch_id=epoch_id,
    )
    assert execution == reordered
    assert len(execution.runs) == len(seeds)
    assert execution.seed_set_hash == manifest["seed_hash"]
    assert not hasattr(execution, "best_seed")

    expected_by_seed_digest = {}
    for seed in seeds:
        expected_by_seed_digest[hashlib.sha256(seed.encode("utf-8")).hexdigest()] = sorted(
            instrument_ids,
            key=lambda instrument_id: (
                hashlib.sha256(
                    canonical_json_bytes(
                        [seed, epoch_id, _SESSION, instrument_id]
                    )
                ).hexdigest(),
                instrument_id,
            ),
        )
    for run in execution.runs:
        assert [row.instrument_id for row in run.rows] == expected_by_seed_digest[
            run.seed_digest
        ]

    changed_outcome_snapshots = [
        _snapshot(
            instrument_id,
            extra_features={"future_outcome": "-999"},
        )
        for instrument_id in instrument_ids
    ]
    changed_outcome_execution = evaluate_baseline_manifest(
        manifest,
        universe,
        changed_outcome_snapshots,
        seed_values=seeds,
        epoch_id=epoch_id,
    )
    assert [
        _rank_projection(run) for run in execution.runs
    ] == [_rank_projection(run) for run in changed_outcome_execution.runs]
    assert "outcomes" not in inspect.signature(evaluate_baseline_manifest).parameters

    with pytest.raises(BaselineError, match="differs from the frozen baseline manifest"):
        evaluate_baseline_manifest(
            manifest,
            universe,
            snapshots,
            seed_values=("post-outcome-seed",),
            epoch_id=epoch_id,
        )


def test_calibration_parameters_are_explicit_and_fixture_values_cannot_target_production() -> None:
    with pytest.raises(BaselineError, match="requires exactly these pinned parameters"):
        _manifest(BaselineKind.RELATIVE_VOLUME)
    with pytest.raises(BaselineError, match="positive integer"):
        _manifest(
            BaselineKind.BREAKOUT_PROXIMITY,
            parameter_values={"breakout_proximity_lookback_sessions": 0},
        )
    with pytest.raises(BaselineError, match="no production activation path"):
        _manifest(
            BaselineKind.MOMENTUM_1,
            environment_namespace="production",
        )


def test_fixture_lookbacks_match_content_addressed_configuration_and_feature_registry() -> None:
    cases = (
        (
            BaselineKind.RELATIVE_VOLUME,
            "volume",
            _VOLUME_CALIBRATION,
            "relative_volume",
        ),
        (
            BaselineKind.BREAKOUT_PROXIMITY,
            "breakout",
            _BREAKOUT_CALIBRATION,
            "breakout_proximity",
        ),
        (
            BaselineKind.TRANSPARENT_COMPOSITE,
            "composite",
            _COMPOSITE_CALIBRATION,
            None,
        ),
    )
    for kind, fixture_key, values, feature_id in cases:
        configuration, settings = _CALIBRATION_FIXTURES[fixture_key]
        manifest = _manifest(kind, parameter_values=values)
        reference = manifest["parameter_refs"][0]

        assert reference == {
            "target_schema_name": "qc2.integrity_build.ConfigurationManifest.v1",
            "target_id": configuration["id"],
            "content_hash": configuration["content_hash"],
        }
        assert configuration["fixture_only"] is True
        assert configuration["environment_namespace"] == "test"
        assert configuration["required_setting_keys"] == sorted(values)
        assert len(settings) == len(configuration["setting_refs"]) == len(values)
        settings_by_key = {setting["setting_key"]: setting for setting in settings}
        for setting_key, value in values.items():
            setting = settings_by_key[setting_key]
            assert setting["fixture_only"] is True
            assert setting["value_class"] == "EMPIRICAL_CALIBRATION_REQUIRED"
            assert setting["value_hash"] == hashlib.sha256(
                canonical_json_bytes(
                    {
                        "setting_key": setting_key,
                        "value": value,
                        "unit": "sessions",
                    }
                )
            ).hexdigest()
            if feature_id is not None:
                assert (
                    _FEATURE_REGISTRY_BUNDLE.definition_contracts[feature_id][
                        "lookback_sessions"
                    ]
                    == value
                )
        assert canonical_json_bytes(values).decode("utf-8") in manifest["algorithm"]


def test_intersection_is_secondary_and_does_not_shrink_each_baseline() -> None:
    instrument_ids = sorted(new_uuidv7() for _ in range(3))
    universe = _universe(instrument_ids)
    snapshots = [
        _snapshot(
            instrument_ids[0],
            missing={"relative_volume": "DIVISION_BY_ZERO"},
        ),
        _snapshot(instrument_ids[1]),
        _snapshot(instrument_ids[2]),
    ]
    volume_run = evaluate_baseline_manifest(
        _manifest(
            BaselineKind.RELATIVE_VOLUME,
            parameter_values=_VOLUME_CALIBRATION,
        ),
        universe,
        snapshots,
    ).runs[0]
    composite_run = evaluate_baseline_manifest(
        _manifest(
            BaselineKind.TRANSPARENT_COMPOSITE,
            parameter_values=_COMPOSITE_CALIBRATION,
        ),
        universe,
        snapshots,
    ).runs[0]

    assert len(volume_run.rows) == len(composite_run.rows) == len(instrument_ids)
    assert volume_run.unscorable_count == 1
    assert composite_run.unscorable_count == 1
    assert scoreable_intersection(volume_run, composite_run) == tuple(instrument_ids[1:])
