"""Immutable, deterministic QuantraScore synthesis.

The wire ScoreManifest content-addresses a ScoreDefinition. The definition
freezes ordered inputs, coefficients, transformations, missing-head handling,
clipping, and ranking ties. A score is computed as
``100 * sum(coefficient * transformed_input)``; transforms return dimensionless
values, and the result is quantized to six decimals with ROUND_HALF_EVEN before
ranking. The primary Expansion Runner probability is carried separately at
twelve decimals. It is never inferred from a score, confidence, or readiness.

This framework has no production activation path: fixture parameters are
fixture-only, and every other parameter set is uncalibrated until a separately
qualified calibration authority exists. Safety results are not accepted score
inputs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import Enum
from typing import Any

from qc2_contracts.runtime import (
    canonical_content_hash,
    validate_contract,
    verify_content_hash,
)

from .models import as_decimal

_SCORE_DEFINITION_SCHEMA = "qc2.scientific_definitions.ScoreDefinition.v1"
_SCORE_MANIFEST_SCHEMA = "qc2.scientific_definitions.ScoreManifest.v1"
_MODEL_HEAD_SCHEMA = "qc2.models_prediction.ModelHeadDefinition.v1"
_MODEL_HEAD_OUTPUT_SCHEMA = "qc2.models_prediction.ModelHeadOutput.v1"
_LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
_PROTOCOL_RESULT_SCHEMA = "qc2.scientific_definitions.RunnerProtocolResult.v1"
_PROTOCOL_DEFINITION_SCHEMA = "qc2.scientific_definitions.RunnerProtocolDefinition.v1"
_ALLOWED_PROTOCOL_INPUT_SCHEMAS = frozenset(
    {
        "qc2.scientific_definitions.FeatureDefinition.v1",
        "qc2.scientific_definitions.FeatureSnapshot.v1",
        "qc2.identity_market.DailyBar.v1",
    }
)
_ALLOWED_INPUT_SCHEMAS = frozenset({_MODEL_HEAD_SCHEMA, _PROTOCOL_RESULT_SCHEMA})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_DECIMAL_TEXT = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_TRANSFORM_SPEC = re.compile(
    r"^(?P<selector>HEAD_OUTPUT|PROTOCOL_EVIDENCE:[a-z][a-z0-9_-]{0,95}"
    r"@[A-Za-z][A-Za-z0-9_./%*-]{0,95}|PROTOCOL_UNCERTAINTY:"
    r"[a-z][a-z0-9_-]{0,95}@[A-Za-z][A-Za-z0-9_./%*-]{0,95})"
    r"\|(?P<operation>IDENTITY|COMPLEMENT|NEGATE|SQUARE|RATIONAL_SQUASH"
    r"|DIRECTIONAL_RATIONAL_SQUASH)"
    r"(?:\|MISSING_PENALTY=(?P<penalty>-?(?:0|[1-9][0-9]*)\.[0-9]{12}))?$"
)
_HEAD_OUTPUT_UNITS = {
    "PROBABILITY": "probability",
    "EXPECTED_MFE": "fraction",
    "EXPECTED_MAE": "fraction",
    "CONTINUATION": "probability",
    "FAILURE": "probability",
    "TIME_TO_EXPANSION": "sessions",
}
_OUTPUT_KINDS = frozenset(_HEAD_OUTPUT_UNITS)
_SCORE_QUANTUM = Decimal("0.000001")
_PROBABILITY_QUANTUM = Decimal("0.000000000001")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_SCORE_MAX = Decimal("100")
SCORE_UNIT = "points_0_100"
SCORE_TIE_BREAK_RULE = "SCORE_DESC_STABLE_INSTRUMENT_ID_ASC"


class ScoreError(ValueError):
    """A score definition, input, or deterministic evaluation is invalid."""


class ScoreManifestError(ScoreError):
    """A score manifest or its bound definition cannot be loaded safely."""


class ScoreInputError(ScoreError):
    """A score input is missing, malformed, or not bound to the manifest."""


class ScoreActivationDenied(RuntimeError):
    """The score is not eligible for the requested environment."""


class ScoreInputAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE_LABEL = "UNAVAILABLE_LABEL"
    UNAVAILABLE_MODEL = "UNAVAILABLE_MODEL"
    INVALID = "INVALID"
    MISSING = "MISSING"


class ScoreDisposition(str, Enum):
    SCORED = "SCORED"
    UNSCORABLE = "UNSCORABLE"


class ScoreCalibrationState(str, Enum):
    FIXTURE_ONLY = "FIXTURE_ONLY"
    UNCALIBRATED = "UNCALIBRATED"
    CALIBRATED = "CALIBRATED"


@dataclass(frozen=True, slots=True)
class ScoreInputRef:
    """A typed, stable input identity listed in one immutable definition."""

    target_schema_name: str
    target_id: str
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if self.target_schema_name not in _ALLOWED_INPUT_SCHEMAS:
            raise ScoreManifestError(
                "score inputs must be model heads or runner-protocol results; "
                "safety, feature, and other refs are not accepted by this evaluator"
            )
        if not isinstance(self.target_id, str) or not _UUID7.fullmatch(self.target_id):
            raise ScoreManifestError("score input target_id must be a UUIDv7")
        if self.content_hash is not None:
            raise ScoreManifestError(
                "model-head and runner-protocol-result inputs are not content-addressed"
            )

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> ScoreInputRef:
        if not isinstance(value, Mapping):
            raise ScoreManifestError("each score input reference must be an object")
        if set(value) - {"target_schema_name", "target_id", "content_hash"}:
            raise ScoreManifestError("score input reference has unknown fields")
        return cls(
            target_schema_name=value.get("target_schema_name"),
            target_id=value.get("target_id"),
            content_hash=value.get("content_hash"),
        )

    def to_payload(self) -> dict[str, str]:
        return {
            "target_schema_name": self.target_schema_name,
            "target_id": self.target_id,
        }

    @property
    def key(self) -> tuple[str, str]:
        return self.target_schema_name, self.target_id


class ScoreTransformOperation(str, Enum):
    IDENTITY = "IDENTITY"
    COMPLEMENT = "COMPLEMENT"
    NEGATE = "NEGATE"
    SQUARE = "SQUARE"
    RATIONAL_SQUASH = "RATIONAL_SQUASH"
    DIRECTIONAL_RATIONAL_SQUASH = "DIRECTIONAL_RATIONAL_SQUASH"


@dataclass(frozen=True, slots=True)
class ScoreTransform:
    """One frozen selector/transform and its optional explicit missing value."""

    selector: str
    operation: ScoreTransformOperation
    missing_penalty: Decimal | None


@dataclass(frozen=True, slots=True)
class ScoreParameter:
    """One ordered, calibratable coefficient bound to exactly one input."""

    input_ref: ScoreInputRef
    coefficient: Decimal
    transform: ScoreTransform
    required: bool


@dataclass(frozen=True, slots=True)
class ScoreParameterSet:
    """Immutable typed view of the coefficients stored in ScoreDefinition."""

    schema_version: str
    parameters: tuple[ScoreParameter, ...]
    calibration_state: ScoreCalibrationState
    fixture_only: bool


@dataclass(frozen=True, slots=True)
class ScoreProgram:
    """Validated immutable ScoreManifest + ScoreDefinition bundle."""

    manifest_id: str
    manifest_hash: str
    definition_id: str
    definition_hash: str
    evidence_class: str
    environment_namespace: str
    parameter_set: ScoreParameterSet
    missing_head_policy: str
    clipping_policy: str
    tie_break_rule: str

    @property
    def parameters(self) -> tuple[ScoreParameter, ...]:
        return self.parameter_set.parameters


@dataclass(frozen=True, slots=True)
class PrimaryProbability:
    """The separately preserved primary Expansion Runner probability."""

    head_ref: ScoreInputRef
    instrument_id: str
    session_id: str
    availability: ScoreInputAvailability | str
    value: Decimal | str | int | None
    reason_code: str | None

    def __post_init__(self) -> None:
        if self.head_ref.target_schema_name != _MODEL_HEAD_SCHEMA:
            raise ScoreInputError("primary probability must reference a model head")
        _require_uuid7(self.instrument_id, "primary probability instrument_id")
        _canonical_session(self.session_id, "primary probability session_id")
        availability = _availability(self.availability, "primary probability")
        object.__setattr__(self, "availability", availability)
        if availability is ScoreInputAvailability.AVAILABLE:
            value = _input_decimal(
                self.value,
                "primary probability",
                exact_places=12,
            )
            if not _ZERO <= value <= _ONE:
                raise ScoreInputError("primary probability must be between 0 and 1")
            if self.reason_code is not None:
                raise ScoreInputError("available primary probability cannot have a reason_code")
            object.__setattr__(self, "value", value)
        else:
            if self.value is not None:
                raise ScoreInputError("unavailable primary probability must have null value")
            if not isinstance(self.reason_code, str) or not self.reason_code:
                raise ScoreInputError("unavailable primary probability requires a reason_code")


@dataclass(frozen=True, slots=True)
class ScoreInputValue:
    """One value selected from a manifest-bound model head or protocol result."""

    source_ref: ScoreInputRef
    selector: str
    instrument_id: str
    session_id: str
    availability: ScoreInputAvailability | str
    value: Decimal | str | int | None
    reason_code: str | None
    output_kind: str | None = None
    protocol_direction: str | None = None

    def __post_init__(self) -> None:
        _require_uuid7(self.instrument_id, "score input instrument_id")
        _canonical_session(self.session_id, "score input session_id")
        availability = _availability(self.availability, "score input")
        object.__setattr__(self, "availability", availability)

        if self.source_ref.target_schema_name == _MODEL_HEAD_SCHEMA:
            if self.selector != "HEAD_OUTPUT":
                raise ScoreInputError("model-head inputs must select HEAD_OUTPUT")
            if self.output_kind not in _OUTPUT_KINDS:
                raise ScoreInputError("unsupported model-head output kind")
            if self.protocol_direction is not None:
                raise ScoreInputError("model-head input cannot carry protocol direction")
        else:
            if self.output_kind is not None:
                raise ScoreInputError("protocol input cannot declare a model-head output kind")
            if not (
                self.selector.startswith("PROTOCOL_EVIDENCE:")
                or self.selector.startswith("PROTOCOL_UNCERTAINTY:")
            ):
                raise ScoreInputError("protocol input must select evidence or uncertainty")
            if self.protocol_direction not in {
                None,
                "POSITIVE",
                "NEGATIVE",
                "NEUTRAL",
                "UNKNOWN",
            }:
                raise ScoreInputError("invalid runner-protocol direction")

        if availability is ScoreInputAvailability.AVAILABLE:
            value = _input_decimal(self.value, "score input")
            if self.output_kind in {"PROBABILITY", "CONTINUATION", "FAILURE"} and not (
                _ZERO <= value <= _ONE
            ):
                raise ScoreInputError(
                    f"{self.output_kind.lower()} model-head input must be between 0 and 1"
                )
            if self.reason_code is not None:
                raise ScoreInputError("available score input cannot have a reason_code")
            if (
                self.selector.startswith("PROTOCOL_EVIDENCE:")
                and self.protocol_direction not in {"POSITIVE", "NEGATIVE"}
            ):
                raise ScoreInputError(
                    "available directional protocol evidence requires POSITIVE or NEGATIVE"
                )
            object.__setattr__(self, "value", value)
        else:
            if self.value is not None:
                raise ScoreInputError("unavailable score input must have null value")
            if not isinstance(self.reason_code, str) or not self.reason_code:
                raise ScoreInputError("unavailable score input requires a reason_code")


@dataclass(frozen=True, slots=True)
class MissingScoreComponent:
    input_ref: ScoreInputRef
    selector: str
    availability: ScoreInputAvailability
    reason_code: str
    handling: str


@dataclass(frozen=True, slots=True)
class ScoreEvaluation:
    instrument_id: str
    session_id: str
    disposition: ScoreDisposition
    primary_probability: Decimal | None
    score: Decimal | None
    reason_codes: tuple[str, ...]
    missing_components: tuple[MissingScoreComponent, ...]
    manifest_id: str
    manifest_hash: str
    definition_id: str
    definition_hash: str

    def __post_init__(self) -> None:
        if self.disposition is ScoreDisposition.SCORED:
            if (
                self.score is None
                or not self.score.is_finite()
                or self.score.as_tuple().exponent != -6
                or self.primary_probability is None
                or self.reason_codes
            ):
                raise ScoreInputError("scored result requires quantized score and primary probability")
        elif self.score is not None or not self.reason_codes:
            raise ScoreInputError("unscorable result requires reason codes and no score")


@dataclass(frozen=True, slots=True)
class RankedScoreRow:
    instrument_id: str
    rank: int | None
    disposition: ScoreDisposition
    primary_probability: Decimal | None
    score: Decimal | None
    reason_codes: tuple[str, ...]
    missing_components: tuple[MissingScoreComponent, ...]


@dataclass(frozen=True, slots=True)
class ScoreRanking:
    manifest_id: str
    manifest_hash: str
    definition_id: str
    definition_hash: str
    session_id: str
    rows: tuple[RankedScoreRow, ...]

    @property
    def scoreable_count(self) -> int:
        return sum(row.disposition is ScoreDisposition.SCORED for row in self.rows)

    @property
    def unscorable_count(self) -> int:
        return len(self.rows) - self.scoreable_count


def materialize_score_definition(
    *,
    definition_id: str,
    created_at: str,
    stable_key: str,
    version: int,
    input_refs: Sequence[ScoreInputRef | Mapping[str, Any]],
    coefficients: Sequence[Decimal | str | int],
    transforms: Sequence[str],
    clipping_policy: str,
    missing_head_policy: str,
    tie_break_rule: str,
    evidence_class: str,
    environment_namespace: str,
    source_refs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build and validate a content-addressed ScoreDefinition.

    Coefficients are serialized at the contract's exact twelve-place precision.
    Values with more than twelve fractional places are rejected rather than
    rounded. Callers must explicitly provide evidence and environment classes.
    """
    normalized_refs = [
        _score_input_ref_payload(value).to_payload() for value in input_refs
    ]
    normalized_coefficients = [
        _fixed_decimal_text(value, 12, "score coefficient") for value in coefficients
    ]
    payload: dict[str, Any] = {
        "schema_name": _SCORE_DEFINITION_SCHEMA,
        "schema_version": "1.0",
        "id": definition_id,
        "created_at": created_at,
        "owning_authority": "quantscore",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [_thaw_json(item) for item in source_refs],
        "content_hash": "0" * 64,
        "stable_key": stable_key,
        "version": version,
        "coefficients": normalized_coefficients,
        "transforms": list(transforms),
        "clipping_policy": clipping_policy,
        "missing_head_policy": missing_head_policy,
        "tie_break_rule": tie_break_rule,
        "input_refs": normalized_refs,
    }
    payload["content_hash"] = canonical_content_hash("ScoreDefinition", payload)
    _contract_payload("ScoreDefinition", payload, content_addressed=True)
    return payload


def materialize_score_manifest(
    *,
    manifest_id: str,
    created_at: str,
    frozen_at: str,
    definition: Mapping[str, Any],
    source_refs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a content-addressed ScoreManifest that pins one exact definition."""
    definition_payload = _contract_payload(
        "ScoreDefinition", definition, content_addressed=True
    )
    payload: dict[str, Any] = {
        "schema_name": _SCORE_MANIFEST_SCHEMA,
        "schema_version": "1.0",
        "id": manifest_id,
        "created_at": created_at,
        "owning_authority": "quantscore",
        "evidence_class": definition_payload["evidence_class"],
        "environment_namespace": definition_payload["environment_namespace"],
        "source_refs": [_thaw_json(item) for item in source_refs],
        "content_hash": "0" * 64,
        "definition_ref": {
            "target_schema_name": _SCORE_DEFINITION_SCHEMA,
            "target_id": definition_payload["id"],
            "content_hash": definition_payload["content_hash"],
        },
        "score_precision": 6,
        "score_unit": SCORE_UNIT,
        "frozen_at": frozen_at,
    }
    payload["content_hash"] = canonical_content_hash("ScoreManifest", payload)
    _contract_payload("ScoreManifest", payload, content_addressed=True)
    return payload


def load_score_program(
    manifest: Mapping[str, Any],
    definition: Mapping[str, Any],
    *,
    target_environment_namespace: str,
) -> ScoreProgram:
    """Validate hashes, the manifest binding, and every deterministic score rule."""
    manifest_payload = _contract_payload("ScoreManifest", manifest, content_addressed=True)
    definition_payload = _contract_payload(
        "ScoreDefinition", definition, content_addressed=True
    )
    if target_environment_namespace not in {"development", "test", "research", "production"}:
        raise ScoreActivationDenied("unknown target environment namespace")
    expected_definition_ref = {
        "target_schema_name": _SCORE_DEFINITION_SCHEMA,
        "target_id": definition_payload["id"],
        "content_hash": definition_payload["content_hash"],
    }
    if manifest_payload["definition_ref"] != expected_definition_ref:
        raise ScoreManifestError("ScoreManifest does not bind this exact ScoreDefinition")
    if (
        manifest_payload["evidence_class"] != definition_payload["evidence_class"]
        or manifest_payload["environment_namespace"]
        != definition_payload["environment_namespace"]
    ):
        raise ScoreManifestError("ScoreManifest and ScoreDefinition evidence scopes differ")
    if manifest_payload["score_precision"] != 6:
        raise ScoreManifestError("QuantraScore precision must be exactly six places")
    if manifest_payload["score_unit"] != SCORE_UNIT:
        raise ScoreManifestError(f"score_unit must be {SCORE_UNIT!r}")
    if target_environment_namespace != manifest_payload["environment_namespace"]:
        raise ScoreActivationDenied("score artifact namespace does not match the target environment")

    missing_policy = definition_payload["missing_head_policy"]
    clipping_policy = definition_payload["clipping_policy"]
    tie_break_rule = definition_payload["tie_break_rule"]
    if missing_policy not in {
        "BLOCK_ROW",
        "EXPLICIT_PENALTY",
        "OMIT_WITH_SEPARATE_STATUS",
    }:
        raise ScoreManifestError("unsupported missing-head policy")
    if clipping_policy not in {"CLIP_TO_0_100", "REJECT_OUT_OF_RANGE"}:
        raise ScoreManifestError("unsupported clipping policy")
    if tie_break_rule != SCORE_TIE_BREAK_RULE:
        raise ScoreManifestError("unsupported score tie-break rule")

    refs = tuple(_score_input_ref_payload(item) for item in definition_payload["input_refs"])
    transforms = tuple(
        _parse_transform(value, missing_policy) for value in definition_payload["transforms"]
    )
    coefficients = tuple(
        _input_decimal(value, "score coefficient", exact_places=12)
        for value in definition_payload["coefficients"]
    )
    if not refs or refs[0].target_schema_name != _MODEL_HEAD_SCHEMA:
        raise ScoreManifestError(
            "the first frozen input must be the primary Expansion Runner model head"
        )
    if not (len(refs) == len(transforms) == len(coefficients)):
        raise ScoreManifestError(
            "input_refs, coefficients, and transforms must have identical ordered lengths"
        )
    parameter_keys = tuple(
        (reference.key, transform.selector)
        for reference, transform in zip(refs, transforms, strict=True)
    )
    if len(set(parameter_keys)) != len(parameter_keys):
        raise ScoreManifestError("score definition repeats an input and selector")
    if coefficients[0] < _ZERO:
        raise ScoreManifestError("primary Expansion Runner probability cannot have a negative weight")
        if (
            transforms[0].selector != "HEAD_OUTPUT"
            or transforms[0].missing_penalty is not None
        ):
            raise ScoreManifestError(
                "the required primary probability cannot have a missing penalty"
            )
    for index, (reference, transform, coefficient) in enumerate(
        zip(refs, transforms, coefficients, strict=True)
    ):
        if reference.target_schema_name == _MODEL_HEAD_SCHEMA:
            if transform.selector != "HEAD_OUTPUT":
                raise ScoreManifestError("model-head refs must select HEAD_OUTPUT")
        elif reference.target_schema_name == _PROTOCOL_RESULT_SCHEMA:
            if not transform.selector.startswith(
                ("PROTOCOL_EVIDENCE:", "PROTOCOL_UNCERTAINTY:")
            ):
                raise ScoreManifestError("protocol refs must select a named evidence value")
        if transform.selector.startswith("PROTOCOL_EVIDENCE:") and (
            transform.operation is not ScoreTransformOperation.DIRECTIONAL_RATIONAL_SQUASH
            or coefficient < 0
        ):
            raise ScoreManifestError(
                "directional protocol evidence requires DIRECTIONAL_RATIONAL_SQUASH "
                "and a nonnegative coefficient"
            )
        if transform.selector.startswith("PROTOCOL_UNCERTAINTY:") and (
            transform.operation is not ScoreTransformOperation.RATIONAL_SQUASH
            or coefficient > 0
        ):
            raise ScoreManifestError(
                "uncertainty must use RATIONAL_SQUASH and a nonpositive penalty coefficient"
            )
        if index > 0 and missing_policy == "EXPLICIT_PENALTY":
            if transform.missing_penalty is None:
                raise ScoreManifestError(
                    "EXPLICIT_PENALTY requires one explicit missing penalty per supporting input"
                )
            if coefficient * transform.missing_penalty > _ZERO:
                raise ScoreManifestError("an explicit missing value cannot increase the score")
        elif transform.missing_penalty is not None:
            raise ScoreManifestError(
                "missing penalties are only valid with EXPLICIT_PENALTY"
            )

    parameter_rows = tuple(
        ScoreParameter(
            input_ref=reference,
            coefficient=coefficient,
            transform=transform,
            required=index == 0 or missing_policy == "BLOCK_ROW",
        )
        for index, (reference, coefficient, transform) in enumerate(
            zip(refs, coefficients, transforms, strict=True)
        )
    )
    parameter_set = ScoreParameterSet(
        schema_version="1",
        parameters=parameter_rows,
        calibration_state=(
            ScoreCalibrationState.FIXTURE_ONLY
            if manifest_payload["evidence_class"] == "SYNTHETIC_FIXTURE"
            else ScoreCalibrationState.UNCALIBRATED
        ),
        fixture_only=manifest_payload["evidence_class"] == "SYNTHETIC_FIXTURE",
    )
    if target_environment_namespace == "production":
        if parameter_set.fixture_only:
            raise ScoreActivationDenied("synthetic score parameters are fixture-only")
        raise ScoreActivationDenied(
            "QC2-024 has no calibration-attested production activation path; "
            "uncalibrated scores cannot enter a production epoch"
        )
    return ScoreProgram(
        manifest_id=manifest_payload["id"],
        manifest_hash=manifest_payload["content_hash"],
        definition_id=definition_payload["id"],
        definition_hash=definition_payload["content_hash"],
        evidence_class=manifest_payload["evidence_class"],
        environment_namespace=manifest_payload["environment_namespace"],
        parameter_set=parameter_set,
        missing_head_policy=missing_policy,
        clipping_policy=clipping_policy,
        tie_break_rule=tie_break_rule,
    )


def primary_probability_from_contracts(
    head_definition: Mapping[str, Any],
    label_definition: Mapping[str, Any],
    head_output: Mapping[str, Any],
) -> PrimaryProbability:
    """Bind the separate primary probability to its exact label and head output."""
    head = _contract_payload(
        "ModelHeadDefinition", head_definition, content_addressed=False
    )
    label = _contract_payload("LabelDefinition", label_definition, content_addressed=True)
    output = _contract_payload("ModelHeadOutput", head_output, content_addressed=False)
    if head["output_kind"] != "PROBABILITY":
        raise ScoreInputError("primary head must have output_kind PROBABILITY")
    if label["target_event"] != "EXPANSION_RUNNER":
        raise ScoreInputError("primary probability must target EXPANSION_RUNNER")
    if head["horizon_sessions"] != label["horizon_sessions"]:
        raise ScoreInputError("primary head and label horizons differ")
    if head["label_ref"] != {
        "target_schema_name": _LABEL_SCHEMA,
        "target_id": label["id"],
        "content_hash": label["content_hash"],
    }:
        raise ScoreInputError("primary head does not bind this exact label definition")
    if output["head_ref"] != {
        "target_schema_name": _MODEL_HEAD_SCHEMA,
        "target_id": head["id"],
    }:
        raise ScoreInputError("primary output does not bind this exact model head")
    if output["output_unit"] != "probability" or head["output_precision"] != 12:
        raise ScoreInputError("primary model head must emit a 12-place probability")
    instrument_ref = output["instrument_ref"]
    if instrument_ref["target_schema_name"] != "qc2.identity_market.Instrument.v1":
        raise ScoreInputError("primary output has an invalid instrument reference")
    return PrimaryProbability(
        head_ref=ScoreInputRef(_MODEL_HEAD_SCHEMA, head["id"]),
        instrument_id=instrument_ref["target_id"],
        session_id=output["session_id"],
        availability=output["availability"],
        value=output["output_value"],
        reason_code=output["reason_code"],
    )


def score_input_from_head_output(
    head_definition: Mapping[str, Any],
    head_output: Mapping[str, Any],
) -> ScoreInputValue:
    """Bind a supporting scalar to its exact model-head contract and output."""
    head = _contract_payload(
        "ModelHeadDefinition", head_definition, content_addressed=False
    )
    output = _contract_payload("ModelHeadOutput", head_output, content_addressed=False)
    output_kind = head["output_kind"]
    if output_kind not in _OUTPUT_KINDS:
        raise ScoreInputError("SCORE model-head outputs cannot be nested as score components")
    if output["head_ref"] != {
        "target_schema_name": _MODEL_HEAD_SCHEMA,
        "target_id": head["id"],
    }:
        raise ScoreInputError("supporting output does not bind this exact model head")
    if output["output_unit"] != _HEAD_OUTPUT_UNITS[output_kind]:
        raise ScoreInputError("supporting model-head output unit differs from its definition")
    value: Decimal | None = None
    if output["availability"] == "AVAILABLE":
        value = _input_decimal(
            output["output_value"],
            "supporting model-head output",
            exact_places=head["output_precision"],
        )
    instrument_ref = output["instrument_ref"]
    if instrument_ref["target_schema_name"] != "qc2.identity_market.Instrument.v1":
        raise ScoreInputError("supporting output has an invalid instrument reference")
    return ScoreInputValue(
        source_ref=ScoreInputRef(_MODEL_HEAD_SCHEMA, head["id"]),
        selector="HEAD_OUTPUT",
        instrument_id=instrument_ref["target_id"],
        session_id=output["session_id"],
        availability=output["availability"],
        value=value,
        reason_code=output["reason_code"],
        output_kind=output_kind,
    )


def score_inputs_from_protocol_result(
    program: ScoreProgram,
    protocol_result: Mapping[str, Any],
    *,
    protocol_definition: Mapping[str, Any],
) -> tuple[ScoreInputValue, ...]:
    """Resolve only the named evidence/uncertainty selectors in this program."""
    result = _contract_payload(
        "RunnerProtocolResult", protocol_result, content_addressed=False
    )
    definition = _contract_payload(
        "RunnerProtocolDefinition", protocol_definition, content_addressed=True
    )
    if result["protocol_ref"] != {
        "target_schema_name": _PROTOCOL_DEFINITION_SCHEMA,
        "target_id": definition["id"],
        "content_hash": definition["content_hash"],
    }:
        raise ScoreInputError("runner result does not bind this exact protocol definition")
    if (
        result["evidence_class"] != definition["evidence_class"]
        or result["environment_namespace"] != definition["environment_namespace"]
    ):
        raise ScoreInputError("runner result and protocol definition evidence scopes differ")
    if any(
        reference["target_schema_name"] not in _ALLOWED_PROTOCOL_INPUT_SCHEMAS
        for reference in definition["input_refs"]
    ):
        raise ScoreInputError("safety and non-feature refs cannot supply score protocol inputs")
    source_ref = ScoreInputRef(_PROTOCOL_RESULT_SCHEMA, result["id"])
    parameters = tuple(
        parameter
        for parameter in program.parameters[1:]
        if parameter.input_ref == source_ref
    )
    if not parameters:
        raise ScoreInputError("protocol result is not referenced by the score definition")
    instrument_ref = result["instrument_ref"]
    if instrument_ref["target_schema_name"] != "qc2.identity_market.Instrument.v1":
        raise ScoreInputError("protocol result has an invalid instrument reference")

    resolved: list[ScoreInputValue] = []
    for parameter in parameters:
        selector = parameter.transform.selector
        kind, selection = selector.split(":", maxsplit=1)
        key, expected_unit = selection.rsplit("@", maxsplit=1)
        evidence_rows = [
            row for row in result["evidence_values"] if row["key"] == key
        ]
        if len(evidence_rows) > 1:
            raise ScoreInputError("protocol result repeats a selected evidence key")
        if evidence_rows and evidence_rows[0]["unit"] != expected_unit:
            raise ScoreInputError(
                "protocol evidence unit differs from the unit frozen in the score transform"
            )
        missing_reason: str | None = None
        value: str | None = None
        if result["result"] in {"UNKNOWN", "UNAVAILABLE"}:
            missing_reason = f"PROTOCOL_{result['result']}"
        elif not evidence_rows:
            missing_reason = "PROTOCOL_EVIDENCE_KEY_MISSING"
        elif kind == "PROTOCOL_UNCERTAINTY":
            value = evidence_rows[0]["uncertainty"]
            if value is None:
                missing_reason = "PROTOCOL_UNCERTAINTY_MISSING"
        else:
            value = evidence_rows[0]["value"]
            if result["direction"] not in {"POSITIVE", "NEGATIVE"}:
                value = None
                missing_reason = f"PROTOCOL_DIRECTION_{result['direction']}"
        if missing_reason is not None:
            resolved.append(
                ScoreInputValue(
                    source_ref=source_ref,
                    selector=selector,
                    instrument_id=instrument_ref["target_id"],
                    session_id=result["session_id"],
                    availability=ScoreInputAvailability.MISSING,
                    value=None,
                    reason_code=missing_reason,
                    protocol_direction=result["direction"],
                )
            )
        else:
            resolved.append(
                ScoreInputValue(
                    source_ref=source_ref,
                    selector=selector,
                    instrument_id=instrument_ref["target_id"],
                    session_id=result["session_id"],
                    availability=ScoreInputAvailability.AVAILABLE,
                    value=value,
                    reason_code=None,
                    protocol_direction=result["direction"],
                )
            )
    return tuple(resolved)


def order_score_inputs(
    program: ScoreProgram,
    inputs: Sequence[ScoreInputValue],
) -> tuple[ScoreInputValue, ...]:
    """Return exactly the supplied supporting inputs in frozen definition order."""
    expected = program.parameters[1:]
    by_key: dict[tuple[tuple[str, str], str], ScoreInputValue] = {}
    for value in inputs:
        key = (value.source_ref.key, value.selector)
        if key in by_key:
            raise ScoreInputError("duplicate supporting score input")
        by_key[key] = value
    expected_keys = tuple(
        (parameter.input_ref.key, parameter.transform.selector) for parameter in expected
    )
    if len(by_key) != len(expected_keys) or set(by_key) != set(expected_keys):
        raise ScoreInputError("supporting inputs must exactly match the frozen manifest inputs")
    return tuple(by_key[key] for key in expected_keys)


def evaluate_score_row(
    program: ScoreProgram,
    *,
    instrument_id: str,
    session_id: str,
    primary_probability: PrimaryProbability,
    supporting_inputs: Sequence[ScoreInputValue],
    target_environment_namespace: str,
) -> ScoreEvaluation:
    """Evaluate one instrument without creating confidence or readiness values."""
    _assert_score_environment(program, target_environment_namespace)
    _require_uuid7(instrument_id, "instrument_id")
    _canonical_session(session_id, "session_id")
    if not program.parameters:
        raise ScoreManifestError("score program has no inputs")
    if primary_probability.head_ref != program.parameters[0].input_ref:
        raise ScoreInputError("primary probability does not match the first frozen input")
    if primary_probability.instrument_id != instrument_id:
        raise ScoreInputError("primary probability belongs to a different instrument")
    if primary_probability.session_id != session_id:
        raise ScoreInputError("primary probability belongs to a different session")
    ordered_inputs = order_score_inputs(program, supporting_inputs)
    for value in ordered_inputs:
        if value.instrument_id != instrument_id or value.session_id != session_id:
            raise ScoreInputError("supporting score input belongs to a different row or session")

    primary_value = (
        primary_probability.value
        if primary_probability.availability is ScoreInputAvailability.AVAILABLE
        else None
    )
    if primary_value is None:
        return _unscorable(
            program,
            instrument_id,
            session_id,
            primary_probability=None,
            reasons=(f"PRIMARY_PROBABILITY_{primary_probability.availability.value}",),
        )

    component_values: list[ScoreInputValue | PrimaryProbability] = [
        primary_probability,
        *ordered_inputs,
    ]
    missing_components: list[MissingScoreComponent] = []
    contributions: list[Decimal] = []
    for parameter, value in zip(program.parameters, component_values, strict=True):
        availability = value.availability
        if availability is ScoreInputAvailability.INVALID:
            if isinstance(value, ScoreInputValue):
                missing_components.append(
                    MissingScoreComponent(
                        input_ref=parameter.input_ref,
                        selector=parameter.transform.selector,
                        availability=availability,
                        reason_code=value.reason_code or "INVALID",
                        handling="INVALID_BLOCKED_ROW",
                    )
                )
            return _unscorable(
                program,
                instrument_id,
                session_id,
                primary_probability=primary_value,
                reasons=(f"INVALID_SCORE_INPUT:{parameter.transform.selector}",),
                missing_components=tuple(missing_components),
            )
        if availability is not ScoreInputAvailability.AVAILABLE:
            if isinstance(value, PrimaryProbability):
                return _unscorable(
                    program,
                    instrument_id,
                    session_id,
                    primary_probability=None,
                    reasons=("PRIMARY_PROBABILITY_UNAVAILABLE",),
                )
            if parameter.required or program.missing_head_policy == "BLOCK_ROW":
                missing_components.append(
                    MissingScoreComponent(
                        input_ref=parameter.input_ref,
                        selector=parameter.transform.selector,
                        availability=availability,
                        reason_code=value.reason_code or "MISSING",
                        handling="BLOCKED_ROW",
                    )
                )
                return _unscorable(
                    program,
                    instrument_id,
                    session_id,
                    primary_probability=primary_value,
                    reasons=(f"REQUIRED_SCORE_INPUT_UNAVAILABLE:{parameter.transform.selector}",),
                    missing_components=tuple(missing_components),
                )
            handling = (
                "OMITTED_ZERO_CONTRIBUTION"
                if program.missing_head_policy == "OMIT_WITH_SEPARATE_STATUS"
                else "EXPLICIT_PENALTY"
            )
            missing_components.append(
                MissingScoreComponent(
                    input_ref=parameter.input_ref,
                    selector=parameter.transform.selector,
                    availability=availability,
                    reason_code=value.reason_code or "MISSING",
                    handling=handling,
                )
            )
            if handling == "OMITTED_ZERO_CONTRIBUTION":
                contributions.append(_ZERO)
                continue
            if parameter.transform.missing_penalty is None:
                raise ScoreManifestError(
                    "explicit missing policy lacks its content-addressed penalty"
                )
            contributions.append(
                parameter.coefficient * parameter.transform.missing_penalty
            )
            continue

        assert value.value is not None
        if parameter.transform.selector.startswith("PROTOCOL_UNCERTAINTY:"):
            if value.value < _ZERO or parameter.coefficient > _ZERO:
                return _unscorable(
                    program,
                    instrument_id,
                    session_id,
                    primary_probability=primary_value,
                    reasons=("INVALID_UNCERTAINTY_PENALTY_INPUT",),
                    missing_components=tuple(missing_components),
                )
        if (
            isinstance(value, ScoreInputValue)
            and value.output_kind == "FAILURE"
            and (
                parameter.coefficient > _ZERO
                or parameter.transform.operation
                not in {
                    ScoreTransformOperation.IDENTITY,
                    ScoreTransformOperation.RATIONAL_SQUASH,
                }
            )
        ):
            return _unscorable(
                program,
                instrument_id,
                session_id,
                primary_probability=primary_value,
                reasons=("FAILURE_PROBABILITY_CANNOT_RAISE_SCORE",),
                missing_components=tuple(missing_components),
            )
        try:
            transformed = _transform_value(parameter, value)
        except ScoreInputError:
            return _unscorable(
                program,
                instrument_id,
                session_id,
                primary_probability=primary_value,
                reasons=(f"INPUT_TRANSFORM_DOMAIN_ERROR:{parameter.transform.selector}",),
                missing_components=tuple(missing_components),
            )
        contributions.append(parameter.coefficient * transformed)

    raw_score = _sum_score_points(contributions)
    if program.clipping_policy == "CLIP_TO_0_100":
        raw_score = min(_SCORE_MAX, max(_ZERO, raw_score))
    elif raw_score < _ZERO or raw_score > _SCORE_MAX:
        return _unscorable(
            program,
            instrument_id,
            session_id,
            primary_probability=primary_value,
            reasons=("SCORE_OUT_OF_RANGE",),
            missing_components=tuple(missing_components),
        )
    score = _quantize(raw_score, _SCORE_QUANTUM)
    return ScoreEvaluation(
        instrument_id=instrument_id,
        session_id=session_id,
        disposition=ScoreDisposition.SCORED,
        primary_probability=primary_value,
        score=score,
        reason_codes=(),
        missing_components=tuple(missing_components),
        manifest_id=program.manifest_id,
        manifest_hash=program.manifest_hash,
        definition_id=program.definition_id,
        definition_hash=program.definition_hash,
    )


def rank_score_evaluations(
    program: ScoreProgram,
    evaluations: Sequence[ScoreEvaluation],
    *,
    target_environment_namespace: str,
) -> ScoreRanking:
    """Rank only after score quantization, with stable IDs resolving score ties."""
    _assert_score_environment(program, target_environment_namespace)
    if not evaluations:
        raise ScoreInputError("ranking requires at least one eligible row")
    seen_ids: set[str] = set()
    sessions: set[str] = set()
    for result in evaluations:
        if result.instrument_id in seen_ids:
            raise ScoreInputError("ranking contains a duplicate instrument_id")
        seen_ids.add(result.instrument_id)
        sessions.add(result.session_id)
        if (
            result.manifest_id != program.manifest_id
            or result.manifest_hash != program.manifest_hash
            or result.definition_id != program.definition_id
            or result.definition_hash != program.definition_hash
        ):
            raise ScoreInputError("ranking mixes score manifests or definitions")
    if len(sessions) != 1:
        raise ScoreInputError("ranking rows must belong to exactly one session")

    scored = sorted(
        (row for row in evaluations if row.disposition is ScoreDisposition.SCORED),
        key=lambda row: (-row.score, row.instrument_id),  # type: ignore[operator]
    )
    unscorable = sorted(
        (row for row in evaluations if row.disposition is ScoreDisposition.UNSCORABLE),
        key=lambda row: row.instrument_id,
    )
    ranked_rows: list[RankedScoreRow] = []
    for rank, row in enumerate(scored, start=1):
        ranked_rows.append(
            RankedScoreRow(
                instrument_id=row.instrument_id,
                rank=rank,
                disposition=row.disposition,
                primary_probability=row.primary_probability,
                score=row.score,
                reason_codes=row.reason_codes,
                missing_components=row.missing_components,
            )
        )
    for row in unscorable:
        ranked_rows.append(
            RankedScoreRow(
                instrument_id=row.instrument_id,
                rank=None,
                disposition=row.disposition,
                primary_probability=row.primary_probability,
                score=None,
                reason_codes=row.reason_codes,
                missing_components=row.missing_components,
            )
        )
    return ScoreRanking(
        manifest_id=program.manifest_id,
        manifest_hash=program.manifest_hash,
        definition_id=program.definition_id,
        definition_hash=program.definition_hash,
        session_id=next(iter(sessions)),
        rows=tuple(ranked_rows),
    )


def fixture_score_program() -> ScoreProgram:
    """Return a synthetic arithmetic example; its values are not calibration."""
    primary_ref = ScoreInputRef(
        _MODEL_HEAD_SCHEMA, "018f0000-0000-7000-8000-000000000101"
    )
    protocol_ref = ScoreInputRef(
        _PROTOCOL_RESULT_SCHEMA, "018f0000-0000-7000-8000-000000000102"
    )
    definition = materialize_score_definition(
        definition_id="018f0000-0000-7000-8000-000000000103",
        created_at="2026-10-05T20:00:00Z",
        stable_key="synthetic_fixture",
        version=1,
        input_refs=(primary_ref, protocol_ref),
        coefficients=("0.500000000000", "0.500000000000"),
        transforms=(
            "HEAD_OUTPUT|IDENTITY",
            "PROTOCOL_EVIDENCE:structure_value@fraction|DIRECTIONAL_RATIONAL_SQUASH",
        ),
        clipping_policy="CLIP_TO_0_100",
        missing_head_policy="BLOCK_ROW",
        tie_break_rule=SCORE_TIE_BREAK_RULE,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    manifest = materialize_score_manifest(
        manifest_id="018f0000-0000-7000-8000-000000000104",
        created_at="2026-10-05T20:00:00Z",
        frozen_at="2026-10-05T20:00:00Z",
        definition=definition,
    )
    return load_score_program(
        manifest,
        definition,
        target_environment_namespace="test",
    )


def _assert_score_environment(program: ScoreProgram, target_namespace: str) -> None:
    if target_namespace == "production":
        if program.parameter_set.fixture_only:
            raise ScoreActivationDenied("synthetic score parameters are fixture-only")
        raise ScoreActivationDenied(
            "QC2-024 has no calibration-attested production activation path"
        )
    if target_namespace != program.environment_namespace:
        raise ScoreActivationDenied("score artifact namespace does not match the target environment")


def _unscorable(
    program: ScoreProgram,
    instrument_id: str,
    session_id: str,
    *,
    primary_probability: Decimal | None,
    reasons: tuple[str, ...],
    missing_components: tuple[MissingScoreComponent, ...] = (),
) -> ScoreEvaluation:
    return ScoreEvaluation(
        instrument_id=instrument_id,
        session_id=session_id,
        disposition=ScoreDisposition.UNSCORABLE,
        primary_probability=primary_probability,
        score=None,
        reason_codes=reasons,
        missing_components=missing_components,
        manifest_id=program.manifest_id,
        manifest_hash=program.manifest_hash,
        definition_id=program.definition_id,
        definition_hash=program.definition_hash,
    )


def _transform_value(
    parameter: ScoreParameter,
    value: PrimaryProbability | ScoreInputValue,
) -> Decimal:
    assert value.value is not None
    raw = value.value
    operation = parameter.transform.operation
    if parameter.transform.selector.startswith("PROTOCOL_EVIDENCE:"):
        if value.protocol_direction not in {"POSITIVE", "NEGATIVE"}:
            raise ScoreInputError("directional protocol evidence has no usable direction")
        magnitude = _rational_squash(abs(raw))
        transformed = magnitude if value.protocol_direction == "POSITIVE" else -magnitude
    elif operation is ScoreTransformOperation.IDENTITY:
        if not _ZERO <= raw <= _ONE:
            raise ScoreInputError("IDENTITY requires a value between 0 and 1")
        transformed = raw
    elif operation is ScoreTransformOperation.COMPLEMENT:
        if not _ZERO <= raw <= _ONE:
            raise ScoreInputError("COMPLEMENT requires a value between 0 and 1")
        transformed = _ONE - raw
    elif operation is ScoreTransformOperation.NEGATE:
        if not -_ONE <= raw <= _ONE:
            raise ScoreInputError("NEGATE requires a value between -1 and 1")
        transformed = -raw
    elif operation is ScoreTransformOperation.SQUARE:
        if not -_ONE <= raw <= _ONE:
            raise ScoreInputError("SQUARE requires a value between -1 and 1")
        transformed = raw * raw
    elif operation is ScoreTransformOperation.RATIONAL_SQUASH:
        transformed = _rational_squash(raw)
    else:
        raise ScoreInputError("DIRECTIONAL_RATIONAL_SQUASH requires protocol evidence")
    return _quantize(transformed, _PROBABILITY_QUANTUM)


def _rational_squash(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(64, len(value.as_tuple().digits) + 32)
        context.rounding = ROUND_HALF_EVEN
        return value / (_ONE + abs(value))


def _sum_score_points(contributions: Sequence[Decimal]) -> Decimal:
    precision = max(
        64,
        sum(len(value.as_tuple().digits) for value in contributions) + 32,
    )
    with localcontext() as context:
        context.prec = precision
        context.rounding = ROUND_HALF_EVEN
        total = sum(contributions, _ZERO) * _SCORE_MAX
    return total


def _quantize(value: Decimal, quantum: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(64, len(value.as_tuple().digits) + 32)
        context.rounding = ROUND_HALF_EVEN
        try:
            result = value.quantize(quantum, rounding=ROUND_HALF_EVEN)
        except InvalidOperation as exc:
            raise ScoreInputError("score value cannot be quantized at its registered precision") from exc
    return abs(result) if result.is_zero() else result


def _parse_transform(value: str, missing_policy: str) -> ScoreTransform:
    if not isinstance(value, str):
        raise ScoreManifestError("score transform must be text")
    match = _TRANSFORM_SPEC.fullmatch(value)
    if match is None:
        raise ScoreManifestError(f"unsupported or noncanonical score transform: {value!r}")
    operation = ScoreTransformOperation(match.group("operation"))
    selector = match.group("selector")
    penalty_text = match.group("penalty")
    penalty = (
        _input_decimal(penalty_text, "missing penalty", exact_places=12)
        if penalty_text is not None
        else None
    )
    if penalty is not None and not -_ONE <= penalty <= _ONE:
        raise ScoreManifestError("missing penalty must be an explicit value between -1 and 1")
    if operation is ScoreTransformOperation.DIRECTIONAL_RATIONAL_SQUASH:
        if not selector.startswith("PROTOCOL_EVIDENCE:"):
            raise ScoreManifestError(
                "DIRECTIONAL_RATIONAL_SQUASH applies only to named protocol evidence"
            )
    elif selector.startswith("PROTOCOL_EVIDENCE:"):
        raise ScoreManifestError(
            "protocol evidence must use DIRECTIONAL_RATIONAL_SQUASH"
        )
    if selector.startswith("PROTOCOL_UNCERTAINTY:") and (
        operation is not ScoreTransformOperation.RATIONAL_SQUASH
    ):
        raise ScoreManifestError("protocol uncertainty must use RATIONAL_SQUASH")
    if missing_policy == "EXPLICIT_PENALTY" and selector == "HEAD_OUTPUT" and penalty is not None:
        raise ScoreManifestError("primary head cannot define a missing penalty")
    return ScoreTransform(
        selector=selector,
        operation=operation,
        missing_penalty=penalty,
    )


def _score_input_ref_payload(value: ScoreInputRef | Mapping[str, Any]) -> ScoreInputRef:
    if isinstance(value, ScoreInputRef):
        return value
    return ScoreInputRef.from_payload(value)


def _contract_payload(
    name: str,
    value: Mapping[str, Any],
    *,
    content_addressed: bool,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ScoreError(f"{name} must be a contract object")
    payload = _thaw_json(value)
    try:
        validate_contract(name, payload)
        if content_addressed:
            verify_content_hash(name, payload)
    except (TypeError, ValueError, KeyError) as exc:
        raise ScoreManifestError(f"invalid {name}: {exc}") from exc
    return payload


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _input_decimal(
    value: Decimal | str | int | None,
    field_name: str,
    *,
    exact_places: int | None = None,
) -> Decimal:
    try:
        number = as_decimal(value, field_name)
    except (TypeError, ValueError) as exc:
        raise ScoreInputError(str(exc)) from exc
    if exact_places is not None and number.as_tuple().exponent != -exact_places:
        raise ScoreInputError(f"{field_name} must use exactly {exact_places} decimal places")
    if number.as_tuple().exponent < -12:
        raise ScoreInputError(f"{field_name} cannot exceed twelve decimal places")
    return abs(number) if number.is_zero() else number


def _fixed_decimal_text(
    value: Decimal | str | int,
    places: int,
    field_name: str,
) -> str:
    number = _input_decimal(value, field_name)
    rendered = format(number, "f")
    integer, dot, fraction = rendered.partition(".")
    if len(fraction) > places:
        raise ScoreInputError(f"{field_name} cannot exceed {places} decimal places")
    return f"{integer}.{fraction.ljust(places, '0')}"


def _availability(value: ScoreInputAvailability | str, field_name: str) -> ScoreInputAvailability:
    try:
        return ScoreInputAvailability(value)
    except (TypeError, ValueError) as exc:
        raise ScoreInputError(f"{field_name} has an unsupported availability state") from exc


def _require_uuid7(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _UUID7.fullmatch(value):
        raise ScoreInputError(f"{field_name} must be a UUIDv7")
    return value


def _canonical_session(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ScoreInputError(f"{field_name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ScoreInputError(f"{field_name} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ScoreInputError(f"{field_name} must be canonical YYYY-MM-DD")
    return value
