# QC2 Canonical Contract Catalog

**Status:** generated, version 1.0. **Objects:** 124. **Aliases:** none.

`packages/contracts/src/qc2_contracts/catalog.py` is the source catalog. Every object named in `GEN2_MASTER_SPEC.md` §12 is represented by its exact name and a strict JSON Schema in `packages/contracts/schemas/v1/`.

The catalog defines contracts and boundary rules only. It does not add a persistence service, choose empirical thresholds, activate fixture values, or grant runtime roles. Owner/reader entries are documentation inputs for each authority's later enforcement.

## Serialization rules

- Draft 2020-12 JSON Schema; unknown fields are rejected at every object depth.
- `schema_name`, `schema_version`, authority, enums, references, and UUIDv7 IDs are exact; no coercion is performed.
- Operational instants require RFC 3339 with explicit zero-offset UTC. Exchange session dates are separate `YYYY-MM-DD` strings.
- Exact decimals are JSON strings without exponent notation. Probabilities and registered continuous scientific values use exactly 12 decimal places with round-half-even; QuantraScore uses 6. Prices and quantities preserve exact input precision. Negative zero is canonicalized to positive zero; non-finite values and JSON floats are rejected.
- Canonical JSON v1 uses UTF-8 without a BOM, NFC Unicode scalar strings, object keys sorted by normalized UTF-8 bytes, preserved array order, and compact JSON escaping. Only exact integers within the JavaScript safe-integer range are allowed; scientific decimals are strings with no exponent or locale formatting. Fixed-precision values are quantized before hashing (12 places for continuous/probability values; 6 for QuantraScore); serialization never rounds, and signed zero loses its minus sign.
- QC2-HASH-V1 hashes ASCII `QC2-HASH-V1`, one NUL byte, a lowercase ASCII domain, one NUL byte, then the payload bytes. Contract content domains are `qc2.contract-content.v1/<lowercase schema name>/<schema_version>`. Content hashes exclude schema fields, UUIDv7 ID, creation time, their own hash, and declared mutable state. Artifact inventories use `qc2.artifact-inventory.v1` and sort records by normalized relative-path UTF-8 bytes; ArtifactManifest content hashes include that inventory hash and exclude detached signature and transport hash.
- ScientificPredictionPayload hashes exactly its listed scientific fields; schema/identity/creation/provenance envelope fields are excluded. Every generated schema and the catalog list included and excluded content-hash fields explicitly.
- A foreign reference carries the exact target schema name and UUIDv7 object ID. The hash is required when the referenced contract is content-addressed. Schemas validate target shape; the owning authority resolves existence and transactional consistency.
- Missing measurements are represented by a typed missingness reason or an explicitly nullable field with per-field validity; missing is never encoded as zero.

## Authority and identity map

| Contract | Schema | Writer role | Reader roles | Identity fields | Content addressed | State / mutable field |
|---|---|---|---|---|---|---|
| `CalendarManifest` | `qc2.time_operation.CalendarManifest.v1` | `calendar` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id`, `calendar_version` | yes | immutable record |
| `CalendarRevision` | `qc2.time_operation.CalendarRevision.v1` | `calendar` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id` | no | immutable record |
| `MarketSession` | `qc2.time_operation.MarketSession.v1` | `calendar` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id`, `session_id`, `calendar_revision_ref` | no | immutable record |
| `ClockAssessment` | `qc2.time_operation.ClockAssessment.v1` | `calendar` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id` | no | immutable record |
| `JobDefinition` | `qc2.time_operation.JobDefinition.v1` | `durable_job_service` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id`, `logical_key` | no | `state` (only mutable field) |
| `JobLease` | `qc2.time_operation.JobLease.v1` | `durable_job_service` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id`, `job_ref`, `fencing_generation` | no | immutable record |
| `JobAttempt` | `qc2.time_operation.JobAttempt.v1` | `durable_job_service` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id`, `job_ref`, `attempt_number` | no | `attempt_state` (only mutable field) |
| `OutboxMessage` | `qc2.time_operation.OutboxMessage.v1` | `durable_job_service` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id`, `logical_operation_id` | no | `status` (only mutable field) |
| `ReadinessAssessment` | `qc2.time_operation.ReadinessAssessment.v1` | `safety` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id` | no | immutable record |
| `DeploymentCapabilityManifest` | `qc2.time_operation.DeploymentCapabilityManifest.v1` | `configuration` | calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation | `id` | no | immutable record |
| `Instrument` | `qc2.identity_market.Instrument.v1` | `instrument_universe` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id`, `stable_instrument_key` | no | immutable record |
| `SymbolAssignment` | `qc2.identity_market.SymbolAssignment.v1` | `instrument_universe` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id`, `instrument_ref`, `symbol`, `effective_from`, `known_from` | no | immutable record |
| `InstrumentClassification` | `qc2.identity_market.InstrumentClassification.v1` | `instrument_universe` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `CorporateActionRecord` | `qc2.identity_market.CorporateActionRecord.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `AdjustmentManifest` | `qc2.identity_market.AdjustmentManifest.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `CandidateCensus` | `qc2.identity_market.CandidateCensus.v1` | `instrument_universe` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id`, `session_id`, `membership_hash` | no | immutable record |
| `DailyBar` | `qc2.identity_market.DailyBar.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id`, `instrument_ref`, `session_id`, `feed` | no | immutable record |
| `RawReceipt` | `qc2.identity_market.RawReceipt.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id`, `raw_sha256` | no | immutable record |
| `RequestManifest` | `qc2.identity_market.RequestManifest.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id`, `sanitized_request_hash` | no | immutable record |
| `DataCapabilityManifest` | `qc2.identity_market.DataCapabilityManifest.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `BarSemanticsManifest` | `qc2.identity_market.BarSemanticsManifest.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `DataBundle` | `qc2.identity_market.DataBundle.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `UniverseManifest` | `qc2.identity_market.UniverseManifest.v1` | `instrument_universe` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `MarketSnapshot` | `qc2.identity_market.MarketSnapshot.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `MarketSnapshotRevision` | `qc2.identity_market.MarketSnapshotRevision.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `QuarantineCase` | `qc2.identity_market.QuarantineCase.v1` | `market_data` | apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation | `id` | no | immutable record |
| `FeatureDefinition` | `qc2.scientific_definitions.FeatureDefinition.v1` | `feature` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id`, `stable_key`, `version` | yes | immutable record |
| `FeatureRegistry` | `qc2.scientific_definitions.FeatureRegistry.v1` | `feature` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id` | yes | immutable record |
| `FeatureSnapshot` | `qc2.scientific_definitions.FeatureSnapshot.v1` | `feature` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id` | yes | immutable record |
| `RunnerProtocolDefinition` | `qc2.scientific_definitions.RunnerProtocolDefinition.v1` | `runner_protocol` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id`, `protocol_namespace`, `protocol_id`, `version` | yes | immutable record |
| `RunnerProtocolRegistry` | `qc2.scientific_definitions.RunnerProtocolRegistry.v1` | `runner_protocol` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id` | yes | immutable record |
| `RunnerProtocolResult` | `qc2.scientific_definitions.RunnerProtocolResult.v1` | `runner_protocol` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id` | no | immutable record |
| `SafetyProtocolDefinition` | `qc2.scientific_definitions.SafetyProtocolDefinition.v1` | `safety` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id`, `protocol_key`, `version` | yes | immutable record |
| `SafetyProtocolResult` | `qc2.scientific_definitions.SafetyProtocolResult.v1` | `safety` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id` | yes | immutable record |
| `LabelDefinition` | `qc2.scientific_definitions.LabelDefinition.v1` | `label` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id`, `stable_key`, `version` | yes | immutable record |
| `LabelRegistry` | `qc2.scientific_definitions.LabelRegistry.v1` | `label` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id` | yes | immutable record |
| `ScoreDefinition` | `qc2.scientific_definitions.ScoreDefinition.v1` | `quantscore` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id`, `stable_key`, `version` | yes | immutable record |
| `ScoreManifest` | `qc2.scientific_definitions.ScoreManifest.v1` | `quantscore` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id` | yes | immutable record |
| `BaselineManifest` | `qc2.scientific_definitions.BaselineManifest.v1` | `validation` | apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation | `id` | yes | immutable record |
| `ModelManifest` | `qc2.models_prediction.ModelManifest.v1` | `model_registry` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | yes | `lifecycle_state` (only mutable field) |
| `ModelHeadDefinition` | `qc2.models_prediction.ModelHeadDefinition.v1` | `model_registry` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id`, `model_ref`, `head_name` | no | immutable record |
| `ModelHeadOutput` | `qc2.models_prediction.ModelHeadOutput.v1` | `inference` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | no | immutable record |
| `InferenceReceipt` | `qc2.models_prediction.InferenceReceipt.v1` | `inference` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | no | immutable record |
| `PredictionRun` | `qc2.models_prediction.PredictionRun.v1` | `prediction` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | no | `run_state` (only mutable field) |
| `Prediction` | `qc2.models_prediction.Prediction.v1` | `prediction` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id`, `run_ref`, `instrument_ref` | yes | immutable record |
| `ScientificPredictionPayload` | `qc2.models_prediction.ScientificPredictionPayload.v1` | `prediction` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | yes | immutable record |
| `PredictionSeal` | `qc2.models_prediction.PredictionSeal.v1` | `prediction` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | yes | immutable record |
| `RunDisposition` | `qc2.models_prediction.RunDisposition.v1` | `prediction` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | no | immutable record |
| `ShadowPredictionSet` | `qc2.models_prediction.ShadowPredictionSet.v1` | `prediction` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | yes | immutable record |
| `ReplayRequest` | `qc2.models_prediction.ReplayRequest.v1` | `validation` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | no | immutable record |
| `ReplayReceipt` | `qc2.models_prediction.ReplayReceipt.v1` | `validation` | apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation | `id` | no | immutable record |
| `Outcome` | `qc2.outcomes_research.Outcome.v1` | `ground_truth` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id`, `instrument_ref`, `session_id`, `label_ref`, `horizon_sessions` | yes | immutable record |
| `OutcomeRevision` | `qc2.outcomes_research.OutcomeRevision.v1` | `ground_truth` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | no | immutable record |
| `RunnerEvent` | `qc2.outcomes_research.RunnerEvent.v1` | `ground_truth` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | no | immutable record |
| `RunnerGenome` | `qc2.outcomes_research.RunnerGenome.v1` | `apexlab` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | yes | immutable record |
| `FailureGenome` | `qc2.outcomes_research.FailureGenome.v1` | `apexlab` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | yes | immutable record |
| `MemoryIndexManifest` | `qc2.outcomes_research.MemoryIndexManifest.v1` | `apexlab` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | yes | immutable record |
| `MatchedDecoySet` | `qc2.outcomes_research.MatchedDecoySet.v1` | `apexlab` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | yes | immutable record |
| `ReviewCase` | `qc2.outcomes_research.ReviewCase.v1` | `apexlab` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | no | immutable record |
| `DatasetManifest` | `qc2.outcomes_research.DatasetManifest.v1` | `apexlab` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | yes | immutable record |
| `DatasetRowLineage` | `qc2.outcomes_research.DatasetRowLineage.v1` | `apexlab` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | yes | immutable record |
| `SplitManifest` | `qc2.outcomes_research.SplitManifest.v1` | `apexlab` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | yes | immutable record |
| `HoldoutAccessReceipt` | `qc2.outcomes_research.HoldoutAccessReceipt.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | no | immutable record |
| `Experiment` | `qc2.outcomes_research.Experiment.v1` | `apexlab` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | yes | immutable record |
| `CandidateEvaluation` | `qc2.outcomes_research.CandidateEvaluation.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | no | immutable record |
| `ChallengerEvaluation` | `qc2.outcomes_research.ChallengerEvaluation.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | no | immutable record |
| `DriftAssessment` | `qc2.outcomes_research.DriftAssessment.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation | `id` | no | immutable record |
| `ValidationEpoch` | `qc2.validation.ValidationEpoch.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id`, `epoch_key`, `regime` | yes | `epoch_state` (only mutable field) |
| `EpochManifest` | `qc2.validation.EpochManifest.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id` | yes | immutable record |
| `ScheduledAttempt` | `qc2.validation.ScheduledAttempt.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id` | no | immutable record |
| `ValidationSession` | `qc2.validation.ValidationSession.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id` | no | immutable record |
| `QualificationReceipt` | `qc2.validation.QualificationReceipt.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id` | yes | immutable record |
| `MetricDefinition` | `qc2.validation.MetricDefinition.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id`, `metric_key`, `version` | no | immutable record |
| `MetricResult` | `qc2.validation.MetricResult.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id` | no | immutable record |
| `StatisticalAnalysisPlan` | `qc2.validation.StatisticalAnalysisPlan.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id` | yes | immutable record |
| `ValidationReport` | `qc2.validation.ValidationReport.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id` | yes | immutable record |
| `ReportAmendment` | `qc2.validation.ReportAmendment.v1` | `validation` | apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation | `id` | no | immutable record |
| `StrategyManifest` | `qc2.execution.StrategyManifest.v1` | `strategy` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | yes | immutable record |
| `CapitalPolicy` | `qc2.execution.CapitalPolicy.v1` | `configuration` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | yes | immutable record |
| `PaperOrderIntent` | `qc2.execution.PaperOrderIntent.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id`, `idempotency_key` | yes | `intent_state` (only mutable field) |
| `IntentDecision` | `qc2.execution.IntentDecision.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | no | immutable record |
| `SubmissionAttempt` | `qc2.execution.SubmissionAttempt.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | no | immutable record |
| `BrokerOrder` | `qc2.execution.BrokerOrder.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id`, `paper_account_fingerprint`, `client_order_key` | no | `order_state` (only mutable field) |
| `BrokerOrderEvent` | `qc2.execution.BrokerOrderEvent.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | no | immutable record |
| `Fill` | `qc2.execution.Fill.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id`, `broker_order_ref`, `provider_fill_id` | no | immutable record |
| `FillCorrection` | `qc2.execution.FillCorrection.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | no | immutable record |
| `Position` | `qc2.execution.Position.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | no | immutable record |
| `CashLedgerEntry` | `qc2.execution.CashLedgerEntry.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | no | immutable record |
| `Reservation` | `qc2.execution.Reservation.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | no | immutable record |
| `ReconciliationReport` | `qc2.execution.ReconciliationReport.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | no | immutable record |
| `ExecutionEpisode` | `qc2.execution.ExecutionEpisode.v1` | `execution` | alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy | `id` | yes | immutable record |
| `PromotionPolicy` | `qc2.governance_owner.PromotionPolicy.v1` | `promotion` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | yes | immutable record |
| `PromotionBundleManifest` | `qc2.governance_owner.PromotionBundleManifest.v1` | `promotion` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | yes | immutable record |
| `PromotionRequest` | `qc2.governance_owner.PromotionRequest.v1` | `promotion` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | immutable record |
| `PromotionChallenge` | `qc2.governance_owner.PromotionChallenge.v1` | `promotion` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | yes | immutable record |
| `PromotionDecision` | `qc2.governance_owner.PromotionDecision.v1` | `promotion` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | yes | immutable record |
| `PromotionReceipt` | `qc2.governance_owner.PromotionReceipt.v1` | `promotion` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | immutable record |
| `ChampionPointer` | `qc2.governance_owner.ChampionPointer.v1` | `promotion` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | immutable record |
| `EpochActivationChallenge` | `qc2.governance_owner.EpochActivationChallenge.v1` | `validation` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | yes | immutable record |
| `EpochActivationDecision` | `qc2.governance_owner.EpochActivationDecision.v1` | `validation` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | yes | immutable record |
| `EpochActivationReceipt` | `qc2.governance_owner.EpochActivationReceipt.v1` | `validation` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | immutable record |
| `OwnerDevice` | `qc2.governance_owner.OwnerDevice.v1` | `identity` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | `revocation_state` (only mutable field) |
| `OwnerSession` | `qc2.governance_owner.OwnerSession.v1` | `identity` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | immutable record |
| `EnrollmentChallenge` | `qc2.governance_owner.EnrollmentChallenge.v1` | `identity` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | immutable record |
| `RecoveryEvent` | `qc2.governance_owner.RecoveryEvent.v1` | `identity` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | immutable record |
| `OwnerCommand` | `qc2.governance_owner.OwnerCommand.v1` | `owner_api` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id`, `command_id`, `idempotency_key` | yes | immutable record |
| `OwnerCommandReceipt` | `qc2.governance_owner.OwnerCommandReceipt.v1` | `owner_api` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | immutable record |
| `Alert` | `qc2.governance_owner.Alert.v1` | `alert` | alert, evidence, execution, identity, model_registry, owner_api, promotion, validation | `id` | no | immutable record |
| `EvidenceEvent` | `qc2.integrity_build.EvidenceEvent.v1` | `evidence` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id`, `installation_id`, `stream_id`, `sequence` | yes | immutable record |
| `Checkpoint` | `qc2.integrity_build.Checkpoint.v1` | `evidence` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | yes | immutable record |
| `AnchorReceipt` | `qc2.integrity_build.AnchorReceipt.v1` | `evidence` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | no | immutable record |
| `ArtifactManifest` | `qc2.integrity_build.ArtifactManifest.v1` | `model_registry` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | yes | immutable record |
| `ArtifactDependency` | `qc2.integrity_build.ArtifactDependency.v1` | `model_registry` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | no | immutable record |
| `BackupManifest` | `qc2.integrity_build.BackupManifest.v1` | `evidence` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | yes | immutable record |
| `RestoreReceipt` | `qc2.integrity_build.RestoreReceipt.v1` | `evidence` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | no | immutable record |
| `ConfigurationManifest` | `qc2.integrity_build.ConfigurationManifest.v1` | `configuration` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `configuration_domain`, `environment_namespace`, `version` | yes | immutable record |
| `ConfigurationSetting` | `qc2.integrity_build.ConfigurationSetting.v1` | `configuration` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `configuration_domain`, `environment_namespace`, `setting_key`, `version` | yes | immutable record |
| `SecretReference` | `qc2.integrity_build.SecretReference.v1` | `configuration` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `environment_namespace`, `secret_key_name`, `version` | yes | immutable record |
| `ResourceBudget` | `qc2.integrity_build.ResourceBudget.v1` | `configuration` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `configuration_domain`, `environment_namespace`, `budget_key`, `version` | yes | immutable record |
| `UnknownDecision` | `qc2.integrity_build.UnknownDecision.v1` | `configuration` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | no | immutable record |
| `ChangeRequest` | `qc2.integrity_build.ChangeRequest.v1` | `build_governance` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | yes | immutable record |
| `ReferenceIntake` | `qc2.integrity_build.ReferenceIntake.v1` | `build_governance` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | yes | immutable record |
| `BuildTask` | `qc2.integrity_build.BuildTask.v1` | `build_governance` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | yes | immutable record |
| `TaskAcceptanceReceipt` | `qc2.integrity_build.TaskAcceptanceReceipt.v1` | `build_governance` | apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation | `id` | yes | immutable record |

## Content-hash field partitions

| Contract | Included fields | Excluded envelope / mutable fields |
|---|---|---|
| `ArtifactManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `manifest_version`, `files`, `inventory_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash`, `detached_signature`, `transport_hash` |
| `BackupManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `recovery_point_at`, `database_snapshot_ref`, `artifact_inventory_refs`, `configuration_refs`, `key_inventory_hash`, `evidence_root_ref`, `anchor_receipt_refs`, `encryption_key_id`, `inventory_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `BaselineManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `baseline_kind`, `version`, `algorithm`, `parameter_refs`, `seed_hash`, `comparator_role`, `tie_break_rule` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `BuildTask` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `task_id`, `task_name`, `objective`, `dependency_task_ids`, `authorized_legacy_refs`, `deliverable_refs`, `required_test_refs`, `acceptance_gate`, `evidence_requirement`, `calibration_dependency`, `task_state`, `blocker_refs` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `CalendarManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `calendar_version`, `timezone`, `valid_from`, `valid_through`, `sessions` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `CapitalPolicy` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `paper_starting_capital`, `currency`, `maximum_position_cost`, `maximum_position_fraction`, `maximum_gross_exposure`, `cash_reserve`, `maximum_concurrent_positions`, `daily_loss_limit`, `drawdown_response`, `participation_limit`, `external_activity_policy`, `owner_approval_ref` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ChangeRequest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `change_class`, `requirements_changed`, `reason`, `impact_analysis`, `migration_plan`, `test_refs`, `effective_boundary`, `is_restrictive_only`, `owner_approval_ref`, `status` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `Checkpoint` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `stream_id`, `head_sequence`, `head_hash`, `event_count`, `artifact_root_hash`, `checkpoint_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ConfigurationManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `configuration_domain`, `version`, `effective_from`, `capability_scope`, `required_setting_keys`, `setting_refs`, `resource_budget_refs`, `policy_hash`, `unresolved_decision_refs`, `fixture_only`, `signed_by_owner` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ConfigurationSetting` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `setting_key`, `configuration_domain`, `version`, `effective_from`, `value_hash`, `value_class`, `value_authority`, `required_capabilities`, `production_required`, `fixture_only`, `secret_reference_ref`, `resource_budget_ref`, `owner_approval_ref` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `DatasetManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `universe_fidelity`, `snapshot_refs`, `raw_receipt_refs`, `action_refs`, `registry_refs`, `memory_cutoff`, `availability_policy`, `row_lineage_hash`, `membership_hash`, `time_start`, `time_end`, `symbol_count`, `missingness_counts`, `revision_refs`, `split_assignment_hash`, `normalization_ref`, `sampling_policy`, `artifact_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `DatasetRowLineage` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `dataset_ref`, `row_key`, `instrument_ref`, `session_id`, `horizon_sessions`, `target_ref`, `lineage_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `EpochActivationChallenge` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_manifest_ref`, `prospective_start_session`, `account_identity_hash`, `strategy_hash`, `nonce`, `issued_at`, `expires_at`, `device_ref`, `key_id` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `EpochActivationDecision` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `challenge_ref`, `epoch_manifest_hash`, `decision`, `device_ref`, `key_id`, `signature`, `signed_at` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `EpochManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_key`, `regime`, `mode`, `calendar_ref`, `universe_ref`, `registry_refs`, `model_ref`, `reference_model_ref`, `strategy_ref`, `configuration_ref`, `effective_session` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `EvidenceEvent` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `installation_id`, `stream_id`, `sequence`, `event_type`, `actor_identity`, `authorized_command_ref`, `correlation_id`, `payload_hash`, `dependency_refs`, `previous_event_hash`, `event_hash`, `wall_clock_at`, `monotonic_generation` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ExecutionEpisode` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `paper_account_fingerprint`, `account_mode`, `opened_at`, `opening_cash`, `currency`, `opening_position_refs`, `opening_order_refs`, `strategy_ref`, `capital_policy_ref`, `sealed_at`, `episode_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `Experiment` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `hypothesis`, `search_space_hash`, `code_hash`, `environment_fingerprint`, `dataset_ref`, `split_ref`, `candidate_refs`, `algorithm`, `seed`, `configuration_ref`, `budget_ref`, `compute_cost`, `evaluation_access`, `result_ref`, `rejection_reason`, `artifact_refs` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `FailureGenome` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `event_ref`, `failure_type`, `pre_event_snapshot_refs`, `prediction_refs`, `outcome_refs`, `provenance_refs`, `curation_version`, `event_time`, `available_for_learning_at`, `temporal_dependency_refs` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `FeatureDefinition` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `stable_key`, `version`, `research_family`, `equation`, `input_refs`, `input_units`, `output_unit`, `output_dtype`, `lookback_sessions`, `warmup_sessions`, `alignment`, `split_treatment`, `precision`, `normalization`, `parameter_profile`, `missingness_policy`, `zero_denominator_policy`, `supported_regime`, `dependency_refs`, `implementation_hash`, `invariance_properties` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `FeatureRegistry` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `registry_version`, `definition_refs`, `ordered_feature_ids`, `effective_from` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `FeatureSnapshot` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `session_id`, `instrument_ref`, `registry_ref`, `feature_values`, `input_hashes`, `transform_refs`, `decision_cutoff`, `code_hash`, `environment_fingerprint` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `LabelDefinition` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `stable_key`, `version`, `horizon_sessions`, `price_reference`, `target_event`, `maturity_rule`, `release_policy`, `threshold`, `threshold_unit` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `LabelRegistry` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `registry_version`, `definition_refs`, `primary_label_ref`, `effective_from` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `MatchedDecoySet` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `positive_event_refs`, `decoy_instrument_refs`, `matching_procedure_hash`, `pre_outcome_variable_ids`, `strata`, `calipers`, `unmatched_cases`, `outcome_membership_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `MemoryIndexManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `index_kind`, `member_refs`, `member_inventory_hash`, `cutoff`, `available_for_learning_at`, `embedding_artifact_ref` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ModelManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `artifact_manifest_ref`, `safe_format`, `algorithm`, `algorithm_version`, `target_label_refs`, `feature_registry_ref`, `ordered_feature_ids`, `protocol_registry_ref`, `training_start`, `training_cutoff`, `validation_window`, `qualification_window`, `dataset_ref`, `split_ref`, `seed`, `hyperparameter_refs`, `calibration_ref`, `package_lock_hash`, `environment_fingerprint`, `learned_dependency_refs`, `resource_constraints` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash`, `lifecycle_state` |
| `Outcome` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `instrument_ref`, `session_id`, `label_ref`, `horizon_sessions`, `reference_bar_ref`, `reference_price`, `next_open_bar_ref`, `next_open_reference_price`, `outcome_state`, `endpoint_return`, `max_high_return`, `min_low_return`, `mfe`, `mae`, `max_high_price`, `max_high_session`, `max_high_session_offset`, `min_low_price`, `min_low_session`, `min_low_session_offset`, `extrema_tie_break`, `opening_gap_return`, `next_open_proxy_endpoint_return`, `next_open_proxy_max_high_return`, `next_open_proxy_min_low_return`, `next_open_proxy_mfe`, `next_open_proxy_mae`, `field_validity`, `reason_codes`, `available_for_learning_at` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `OwnerCommand` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `command_id`, `command_type`, `idempotency_key`, `request_body_hash`, `issued_at`, `device_ref`, `signature`, `scope` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `PaperOrderIntent` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `episode_ref`, `paper_account_fingerprint`, `action_kind`, `source_ref`, `instrument_ref`, `symbol_assignment_ref`, `side`, `quantity_whole_shares`, `limit_price`, `stop_price`, `order_type`, `time_in_force`, `session_restriction`, `strategy_ref`, `capital_policy_ref`, `predicted_session`, `target_execution_session`, `target_window`, `expires_at`, `reason_code`, `safety_assessment_refs`, `reservation_ref`, `idempotency_key`, `account_mode`, `extended_hours` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash`, `intent_state` |
| `Prediction` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `run_ref`, `session_id`, `instrument_ref`, `reference_kind`, `reference_price`, `horizon_label_refs`, `head_output_refs`, `feature_snapshot_ref`, `protocol_result_refs`, `score_manifest_ref`, `score`, `rank`, `disposition`, `unscorable_reason`, `model_ref`, `learned_memory_refs`, `epoch_ref` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `PredictionSeal` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `run_ref`, `session_id`, `role`, `ordered_prediction_refs`, `disposition_counts`, `payload_inventory_hash`, `deadline`, `sealed_at`, `evidence_refs` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `PromotionBundleManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `candidate_model_ref`, `prior_champion_ref`, `epoch_ref`, `mode`, `registry_refs`, `dataset_ref`, `split_ref`, `holdout_receipt_refs`, `replay_report_ref`, `evaluation_refs`, `shadow_seal_refs`, `policy_ref`, `gate_results`, `environment_fingerprint`, `expires_at`, `transition_intent`, `inventory_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `PromotionChallenge` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `request_ref`, `bundle_hash`, `candidate_hash`, `expected_champion_hash`, `expected_generation`, `epoch_ref`, `registry_refs`, `policy_ref`, `nonce`, `issued_at`, `expires_at`, `device_ref`, `key_id` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `PromotionDecision` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `challenge_ref`, `decision`, `signed_by_device_ref`, `key_id`, `signature`, `signed_at`, `request_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `PromotionPolicy` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `policy_key`, `version`, `prospective_sessions`, `minimum_events`, `uncertainty_requirements`, `calibration_bounds`, `coverage_limits`, `stability_limits`, `regression_gates`, `maximum_attempts`, `cooldown_sessions`, `permitted_artifact_types`, `compatibility_envelope`, `epoch_modes`, `frozen_at` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `QualificationReceipt` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_ref`, `session_id`, `prediction_seal_ref`, `prediction_integrity`, `denominator_status`, `on_time_seal`, `on_time_anchor`, `comparator_available`, `protocol_conformity`, `sealed_at`, `checkpoint_ref` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ReferenceIntake` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `repository_identity`, `revision`, `file_path`, `file_sha256`, `inspected_symbol`, `relevant_test_refs`, `reason_for_inspection`, `source_supported_meaning`, `useful_concepts`, `conflicts`, `license`, `provenance_limits`, `disposition` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ResourceBudget` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `budget_key`, `configuration_domain`, `version`, `max_experiments`, `max_concurrent_jobs`, `max_elapsed_seconds`, `max_cpu_seconds`, `max_memory_bytes`, `max_artifact_bytes`, `authorized_cost_minor_units`, `currency`, `owner_approval_ref`, `effective_from`, `fixture_only` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `RunnerGenome` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `event_ref`, `pre_event_snapshot_refs`, `prediction_refs`, `outcome_refs`, `provenance_refs`, `curation_version`, `event_time`, `available_for_learning_at`, `temporal_dependency_refs` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `RunnerProtocolDefinition` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `protocol_namespace`, `protocol_id`, `version`, `hypothesis`, `direction`, `input_refs`, `parameter_refs`, `implementation_hash`, `regime` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `RunnerProtocolRegistry` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `registry_version`, `definition_refs`, `active_protocol_ids`, `effective_from` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `SafetyProtocolDefinition` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `protocol_key`, `version`, `action`, `rule`, `required_evidence`, `warning_policy`, `implementation_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `SafetyProtocolResult` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `protocol_ref`, `action`, `result`, `reason_codes`, `observed_versions`, `evaluated_at`, `freshness_deadline` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ScientificPredictionPayload` | `session_id`, `reference_kind`, `reference_price`, `instrument_ref`, `horizon_label_refs`, `head_output_refs`, `dependency_refs`, `score`, `rank`, `disposition`, `model_hash`, `epoch_ref`, `regime` | `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash` |
| `ScoreDefinition` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `stable_key`, `version`, `coefficients`, `transforms`, `clipping_policy`, `missing_head_policy`, `tie_break_rule`, `input_refs` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ScoreManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `definition_ref`, `score_precision`, `score_unit`, `frozen_at` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `SecretReference` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `secret_key_name`, `provider`, `version`, `required_capabilities`, `rotation_due_at`, `last_verified_at` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ShadowPredictionSet` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `model_ref`, `eligible_at`, `target_label_refs`, `comparison_window_sessions`, `comparator_refs`, `registration_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `SplitManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `dataset_ref`, `split_unit`, `training_intervals`, `validation_intervals`, `qualification_interval`, `purge_sessions`, `embargo_sessions`, `cutoff_policy`, `split_hash` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `StatisticalAnalysisPlan` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_ref`, `primary_metric_ref`, `comparator_ref`, `interval_method`, `alpha`, `practical_minimum_effect`, `minimum_event_clusters`, `minimum_effective_blocks`, `resample_count`, `missingness_method`, `stopping_rule`, `frozen_at` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `StrategyManifest` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `strategy_key`, `version`, `selection_k`, `rank_rule`, `entry_window`, `allocation_order`, `price_cap_rule`, `quantity_rounding`, `stop_rule`, `target_rule`, `trailing_rule`, `maximum_holding_sessions`, `reentry_policy`, `reservation_policy`, `cancellation_policy`, `gap_no_fill_policy`, `competing_action_rule`, `configuration_ref` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `TaskAcceptanceReceipt` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `task_ref`, `task_spec_version`, `source_commit`, `changed_paths`, `executed_commands`, `test_counts`, `artifact_hashes`, `legacy_intake_refs`, `unresolved_decisions`, `gate_verdict`, `agent_identity`, `reviewer_identity`, `checked_at` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |
| `ValidationEpoch` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_key`, `regime`, `mode`, `start_session`, `manifest_ref`, `champion_ref`, `reference_model_ref`, `activated_at` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash`, `epoch_state` |
| `ValidationReport` | `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_ref`, `verdict`, `scheduled_attempt_refs`, `qualification_refs`, `metric_refs`, `missingness_bounds`, `limitation_codes`, `report_hash`, `sealed_at` | `schema_name`, `schema_version`, `id`, `created_at`, `content_hash` |

## Time and operation

### CalendarManifest

Schema: `qc2.time_operation.CalendarManifest.v1`. Writer: `calendar`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`, `calendar_version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `calendar_version`, `timezone`, `valid_from`, `valid_through`, `sessions`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `calendar_version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `timezone` | yes | `timezone_id` | IANA timezone identifier | — |
| `valid_from` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `valid_through` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `sessions` | yes | `session_list` | ordered array; item unit/type is stated by the field | — |

### CalendarRevision

Schema: `qc2.time_operation.CalendarRevision.v1`. Writer: `calendar`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `calendar_ref`, `revision_number`, `effective_session`, `reason`, `source_evidence_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `calendar_ref` | yes | `ref<CalendarManifest>` | typed foreign reference to the listed contract | CalendarManifest |
| `revision_number` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `effective_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `reason` | yes | `text` | text | — |
| `source_evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |

### MarketSession

Schema: `qc2.time_operation.MarketSession.v1`. Writer: `calendar`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`, `session_id`, `calendar_revision_ref`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `session_id`, `phase`, `opens_at`, `closes_at`, `calendar_revision_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `phase` | yes | `enum<MarketPhase>` | enumerated state/dimension; see the named enum | — |
| `opens_at` | yes | `utc_instant` | UTC instant | — |
| `closes_at` | yes | `utc_instant` | UTC instant | — |
| `calendar_revision_ref` | yes | `ref<CalendarRevision>` | typed foreign reference to the listed contract | CalendarRevision |

Invariants:
- opens_at < closes_at

### ClockAssessment

Schema: `qc2.time_operation.ClockAssessment.v1`. Writer: `calendar`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `observed_at`, `trusted_time_at`, `wall_clock_at`, `monotonic_elapsed_ms`, `uncertainty_ms`, `status`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `observed_at` | yes | `utc_instant` | UTC instant | — |
| `trusted_time_at` | yes | `utc_instant` | UTC instant | — |
| `wall_clock_at` | yes | `utc_instant` | UTC instant | — |
| `monotonic_elapsed_ms` | yes | `nonnegative_int` | milliseconds | — |
| `uncertainty_ms` | yes | `nonnegative_int` | milliseconds | — |
| `status` | yes | `enum<ClockStatus>` | enumerated state/dimension; see the named enum | — |

### JobDefinition

Schema: `qc2.time_operation.JobDefinition.v1`. Writer: `durable_job_service`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`, `logical_key`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `logical_key`, `dependency_refs`, `deadline`, `resource_budget_ref`, `checkpoint_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `logical_key` | yes | `slug` | lowercase identifier | — |
| `dependency_refs` | yes | `refs<JobDefinition>` | typed foreign reference to the listed contract | JobDefinition |
| `deadline` | yes | `utc_instant` | UTC instant | — |
| `resource_budget_ref` | yes | `ref<ResourceBudget>` | typed foreign reference to the listed contract | ResourceBudget |
| `checkpoint_ref` | yes | `nullable_ref<Checkpoint>` | typed foreign reference to the listed contract | — |
| `state` | yes | `enum<JobState>` | enumerated state/dimension; see the named enum | — |

State field: `state`. Guard: Claim/renew/commit must recheck lease expiry and monotonically increasing fencing generation.

| From | Allowed next states |
|---|---|
| `QUEUED` | `CLAIMED`, `CANCELLED` |
| `CLAIMED` | `RUNNING`, `RETRYABLE_FAILURE`, `TERMINAL_FAILURE`, `CANCELLED` |
| `RUNNING` | `WAITING_EXTERNAL`, `RETRYABLE_FAILURE`, `COMPLETED`, `TERMINAL_FAILURE`, `CANCELLED` |
| `WAITING_EXTERNAL` | `QUEUED`, `RETRYABLE_FAILURE`, `COMPLETED`, `TERMINAL_FAILURE`, `CANCELLED` |
| `RETRYABLE_FAILURE` | `QUEUED`, `CANCELLED`, `TERMINAL_FAILURE` |

### JobLease

Schema: `qc2.time_operation.JobLease.v1`. Writer: `durable_job_service`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`, `job_ref`, `fencing_generation`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `job_ref`, `lease_owner`, `lease_expires_at`, `fencing_generation`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `job_ref` | yes | `ref<JobDefinition>` | typed foreign reference to the listed contract | JobDefinition |
| `lease_owner` | yes | `text` | text | — |
| `lease_expires_at` | yes | `utc_instant` | UTC instant | — |
| `fencing_generation` | yes | `positive_int` | ordinal/count (unit is named by the field) | — |

### JobAttempt

Schema: `qc2.time_operation.JobAttempt.v1`. Writer: `durable_job_service`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`, `job_ref`, `attempt_number`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `job_ref`, `attempt_number`, `fencing_generation`, `started_at`, `finished_at`, `reason_code`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `job_ref` | yes | `ref<JobDefinition>` | typed foreign reference to the listed contract | JobDefinition |
| `attempt_number` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `fencing_generation` | yes | `positive_int` | ordinal/count (unit is named by the field) | — |
| `started_at` | yes | `utc_instant` | UTC instant | — |
| `finished_at` | yes | `nullable_utc_instant` | UTC instant | — |
| `attempt_state` | yes | `enum<JobAttemptState>` | enumerated state/dimension; see the named enum | — |
| `reason_code` | yes | `nullable_text` | text | — |

State field: `attempt_state`. Guard: Attempt records are append-only; a later attempt never rewrites a prior attempt result.

| From | Allowed next states |
|---|---|
| `STARTED` | `SUCCEEDED`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`, `CANCELLED` |

### OutboxMessage

Schema: `qc2.time_operation.OutboxMessage.v1`. Writer: `durable_job_service`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`, `logical_operation_id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `logical_operation_id`, `message_type`, `payload_hash`, `attempt_count`, `next_attempt_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `logical_operation_id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `message_type` | yes | `slug` | lowercase identifier | — |
| `payload_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `status` | yes | `enum<OutboxState>` | enumerated state/dimension; see the named enum | — |
| `attempt_count` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `next_attempt_at` | yes | `nullable_utc_instant` | UTC instant | — |

State field: `status`. Guard: Delivery is duplicate-tolerant and keyed by logical_operation_id; network delivery is not exactly-once.

| From | Allowed next states |
|---|---|
| `PENDING` | `PUBLISHING`, `FAILED` |
| `PUBLISHING` | `DELIVERED`, `UNKNOWN`, `FAILED` |
| `UNKNOWN` | `PUBLISHING`, `DELIVERED`, `FAILED` |

### ReadinessAssessment

Schema: `qc2.time_operation.ReadinessAssessment.v1`. Writer: `safety`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `action`, `status`, `gate_results`, `input_generation`, `freshness_deadline`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `action` | yes | `enum<ReadinessAction>` | enumerated state/dimension; see the named enum | — |
| `status` | yes | `enum<ReadinessStatus>` | enumerated state/dimension; see the named enum | — |
| `gate_results` | yes | `gate_result_list` | ordered array; item unit/type is stated by the field | — |
| `input_generation` | yes | `positive_int` | ordinal/count (unit is named by the field) | — |
| `freshness_deadline` | yes | `utc_instant` | UTC instant | — |

### DeploymentCapabilityManifest

Schema: `qc2.time_operation.DeploymentCapabilityManifest.v1`. Writer: `configuration`. Readers: calendar, configuration, core, durable_job_service, evidence, owner_api, prediction, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `deployment_fingerprint`, `observed_at`, `capability_results`, `configuration_ref`, `resource_limits_ref`, `revalidation_due_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `deployment_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `observed_at` | yes | `utc_instant` | UTC instant | — |
| `capability_results` | yes | `gate_result_list` | ordered array; item unit/type is stated by the field | — |
| `configuration_ref` | yes | `ref<ConfigurationManifest>` | typed foreign reference to the listed contract | ConfigurationManifest |
| `resource_limits_ref` | yes | `ref<ResourceBudget>` | typed foreign reference to the listed contract | ResourceBudget |
| `revalidation_due_at` | yes | `utc_instant` | UTC instant | — |


## Identity and market

### Instrument

Schema: `qc2.identity_market.Instrument.v1`. Writer: `instrument_universe`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`, `stable_instrument_key`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `stable_instrument_key`, `first_known_at`, `identity_status`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `stable_instrument_key` | yes | `slug` | lowercase identifier | — |
| `first_known_at` | yes | `utc_instant` | UTC instant | — |
| `identity_status` | yes | `enum<IdentityStatus>` | enumerated state/dimension; see the named enum | — |

### SymbolAssignment

Schema: `qc2.identity_market.SymbolAssignment.v1`. Writer: `instrument_universe`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`, `instrument_ref`, `symbol`, `effective_from`, `known_from`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `instrument_ref`, `symbol`, `exchange`, `currency`, `effective_from`, `effective_to`, `known_from`, `known_to`, `source_evidence_ref`, `mapping_confidence`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `symbol` | yes | `symbol` | provider symbol | — |
| `exchange` | yes | `text` | text | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `effective_from` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `effective_to` | yes | `nullable_session` | exchange session date (YYYY-MM-DD) | — |
| `known_from` | yes | `utc_instant` | UTC instant | — |
| `known_to` | yes | `nullable_utc_instant` | UTC instant | — |
| `source_evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |
| `mapping_confidence` | yes | `probability` | probability, fraction in [0, 1] | — |

Invariants:
- effective_from <= effective_to when effective_to is present
- known_from <= known_to when known_to is present
- overlapping known assignments for one symbol cannot resolve to multiple instruments

### InstrumentClassification

Schema: `qc2.identity_market.InstrumentClassification.v1`. Writer: `instrument_universe`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `instrument_ref`, `classification`, `verified`, `valid_from`, `valid_to`, `source_evidence_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `classification` | yes | `enum<InstrumentClass>` | enumerated state/dimension; see the named enum | — |
| `verified` | yes | `boolean` | not applicable | — |
| `valid_from` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `valid_to` | yes | `nullable_session` | exchange session date (YYYY-MM-DD) | — |
| `source_evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |

### CorporateActionRecord

Schema: `qc2.identity_market.CorporateActionRecord.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `instrument_ref`, `action_type`, `effective_session`, `observed_at`, `processing_session`, `terms_hash`, `uncertainty`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `action_type` | yes | `enum<CorporateActionType>` | enumerated state/dimension; see the named enum | — |
| `effective_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `observed_at` | yes | `utc_instant` | UTC instant | — |
| `processing_session` | yes | `nullable_session` | exchange session date (YYYY-MM-DD) | — |
| `terms_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `uncertainty` | yes | `enum<ActionUncertainty>` | enumerated state/dimension; see the named enum | — |

### AdjustmentManifest

Schema: `qc2.identity_market.AdjustmentManifest.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `basis_session`, `action_refs`, `price_factor`, `volume_factor`, `methodology_version`, `available_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `basis_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `action_refs` | yes | `refs<CorporateActionRecord>` | typed foreign reference to the listed contract | CorporateActionRecord |
| `price_factor` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `volume_factor` | yes | `positive_decimal` | provider-reported shares; feed semantics are bound separately | — |
| `methodology_version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `available_at` | yes | `utc_instant` | UTC instant | — |

### CandidateCensus

Schema: `qc2.identity_market.CandidateCensus.v1`. Writer: `instrument_universe`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`, `session_id`, `membership_hash`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `session_id`, `instrument_refs`, `cutoff`, `source_manifest_refs`, `membership_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `instrument_refs` | yes | `refs<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `cutoff` | yes | `utc_instant` | UTC instant | — |
| `source_manifest_refs` | yes | `refs<RequestManifest|DataCapabilityManifest|InstrumentClassification>` | typed foreign reference to the listed contract | RequestManifest, DataCapabilityManifest, InstrumentClassification |
| `membership_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### DailyBar

Schema: `qc2.identity_market.DailyBar.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`, `instrument_ref`, `session_id`, `feed`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `instrument_ref`, `session_id`, `feed`, `currency`, `open_price`, `high_price`, `low_price`, `close_price`, `volume`, `observed_at`, `finalized_at`, `bar_status`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `feed` | yes | `enum<MarketFeed>` | enumerated state/dimension; see the named enum | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `open_price` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `high_price` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `low_price` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `close_price` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `volume` | yes | `nonnegative_decimal` | provider-reported shares; feed semantics are bound separately | — |
| `observed_at` | yes | `utc_instant` | UTC instant | — |
| `finalized_at` | yes | `nullable_utc_instant` | UTC instant | — |
| `bar_status` | yes | `enum<BarStatus>` | enumerated state/dimension; see the named enum | — |

Invariants:
- low_price <= min(open_price, close_price)
- high_price >= max(open_price, close_price)
- low_price <= high_price

### RawReceipt

Schema: `qc2.identity_market.RawReceipt.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`, `raw_sha256`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `request_ref`, `provider`, `received_at`, `media_type`, `byte_length`, `raw_sha256`, `storage_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `request_ref` | yes | `ref<RequestManifest>` | typed foreign reference to the listed contract | RequestManifest |
| `provider` | yes | `text` | text | — |
| `received_at` | yes | `utc_instant` | UTC instant | — |
| `media_type` | yes | `text` | text | — |
| `byte_length` | yes | `nonnegative_int` | bytes | — |
| `raw_sha256` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `storage_ref` | yes | `text` | text | — |

### RequestManifest

Schema: `qc2.identity_market.RequestManifest.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`, `sanitized_request_hash`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `provider`, `feed`, `adjustment`, `timeframe`, `currency`, `calendar_ref`, `bar_semantics_ref`, `cutoff`, `sanitized_request_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `provider` | yes | `text` | text | — |
| `feed` | yes | `enum<MarketFeed>` | enumerated state/dimension; see the named enum | — |
| `adjustment` | yes | `enum<AdjustmentMode>` | enumerated state/dimension; see the named enum | — |
| `timeframe` | yes | `enum<BarTimeframe>` | enumerated state/dimension; see the named enum | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `calendar_ref` | yes | `ref<CalendarManifest>` | typed foreign reference to the listed contract | CalendarManifest |
| `bar_semantics_ref` | yes | `ref<BarSemanticsManifest>` | typed foreign reference to the listed contract | BarSemanticsManifest |
| `cutoff` | yes | `utc_instant` | UTC instant | — |
| `sanitized_request_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### DataCapabilityManifest

Schema: `qc2.identity_market.DataCapabilityManifest.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `deployment_fingerprint`, `account_fingerprint`, `capability`, `observed_result`, `feed`, `tested_at`, `earliest_tested_session`, `effective_delay_ms`, `evidence_refs`, `expires_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `deployment_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `account_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `capability` | yes | `enum<DataCapability>` | enumerated state/dimension; see the named enum | — |
| `observed_result` | yes | `enum<CapabilityResult>` | enumerated state/dimension; see the named enum | — |
| `feed` | yes | `enum<MarketFeed>` | enumerated state/dimension; see the named enum | — |
| `tested_at` | yes | `utc_instant` | UTC instant | — |
| `earliest_tested_session` | yes | `nullable_session` | exchange session date (YYYY-MM-DD) | — |
| `effective_delay_ms` | yes | `nullable_nonnegative_int` | milliseconds | — |
| `evidence_refs` | yes | `refs<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |
| `expires_at` | yes | `utc_instant` | UTC instant | — |

### BarSemanticsManifest

Schema: `qc2.identity_market.BarSemanticsManifest.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `provider`, `feed`, `timeframe`, `interval_timezone`, `field_meanings`, `revision_policy`, `finalization_rule`, `tested_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `provider` | yes | `text` | text | — |
| `feed` | yes | `enum<MarketFeed>` | enumerated state/dimension; see the named enum | — |
| `timeframe` | yes | `enum<BarTimeframe>` | enumerated state/dimension; see the named enum | — |
| `interval_timezone` | yes | `timezone_id` | IANA timezone identifier | — |
| `field_meanings` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `revision_policy` | yes | `text` | text | — |
| `finalization_rule` | yes | `text` | text | — |
| `tested_at` | yes | `utc_instant` | UTC instant | — |

### DataBundle

Schema: `qc2.identity_market.DataBundle.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `census_ref`, `request_refs`, `raw_receipt_refs`, `bar_refs`, `history_start`, `history_end`, `coverage`, `completeness`, `content_inventory_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `census_ref` | yes | `ref<CandidateCensus>` | typed foreign reference to the listed contract | CandidateCensus |
| `request_refs` | yes | `refs<RequestManifest>` | typed foreign reference to the listed contract | RequestManifest |
| `raw_receipt_refs` | yes | `refs<RawReceipt>` | typed foreign reference to the listed contract | RawReceipt |
| `bar_refs` | yes | `refs<DailyBar>` | typed foreign reference to the listed contract | DailyBar |
| `history_start` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `history_end` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `coverage` | yes | `probability` | probability, fraction in [0, 1] | — |
| `completeness` | yes | `enum<CompletenessState>` | enumerated state/dimension; see the named enum | — |
| `content_inventory_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### UniverseManifest

Schema: `qc2.identity_market.UniverseManifest.v1`. Writer: `instrument_universe`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `session_id`, `census_ref`, `data_bundle_ref`, `eligibility_rule_hash`, `eligible_instrument_refs`, `unscorable_instrument_refs`, `reason_counts`, `cutoff`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `census_ref` | yes | `ref<CandidateCensus>` | typed foreign reference to the listed contract | CandidateCensus |
| `data_bundle_ref` | yes | `ref<DataBundle>` | typed foreign reference to the listed contract | DataBundle |
| `eligibility_rule_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `eligible_instrument_refs` | yes | `refs<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `unscorable_instrument_refs` | yes | `refs<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `reason_counts` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `cutoff` | yes | `utc_instant` | UTC instant | — |

### MarketSnapshot

Schema: `qc2.identity_market.MarketSnapshot.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `session_id`, `calendar_ref`, `census_ref`, `data_bundle_ref`, `universe_ref`, `provider`, `feed`, `decision_cutoff`, `sealed_at`, `row_count`, `coverage`, `dependency_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `calendar_ref` | yes | `ref<CalendarManifest>` | typed foreign reference to the listed contract | CalendarManifest |
| `census_ref` | yes | `ref<CandidateCensus>` | typed foreign reference to the listed contract | CandidateCensus |
| `data_bundle_ref` | yes | `ref<DataBundle>` | typed foreign reference to the listed contract | DataBundle |
| `universe_ref` | yes | `ref<UniverseManifest>` | typed foreign reference to the listed contract | UniverseManifest |
| `provider` | yes | `text` | text | — |
| `feed` | yes | `enum<MarketFeed>` | enumerated state/dimension; see the named enum | — |
| `decision_cutoff` | yes | `utc_instant` | UTC instant | — |
| `sealed_at` | yes | `utc_instant` | UTC instant | — |
| `row_count` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `coverage` | yes | `fraction` | fraction in [0, 1], not a probability claim | — |
| `dependency_refs` | yes | `refs<CalendarManifest|CandidateCensus|DataBundle|UniverseManifest|RequestManifest|BarSemanticsManifest|AdjustmentManifest>` | typed foreign reference to the listed contract | CalendarManifest, CandidateCensus, DataBundle, UniverseManifest, RequestManifest, BarSemanticsManifest, AdjustmentManifest |

### MarketSnapshotRevision

Schema: `qc2.identity_market.MarketSnapshotRevision.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `prior_snapshot_ref`, `changed_observation_refs`, `discovered_at`, `reason_code`, `source_evidence_ref`, `replacement_content_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `prior_snapshot_ref` | yes | `ref<MarketSnapshot>` | typed foreign reference to the listed contract | MarketSnapshot |
| `changed_observation_refs` | yes | `refs<DailyBar|CorporateActionRecord|SymbolAssignment>` | typed foreign reference to the listed contract | DailyBar, CorporateActionRecord, SymbolAssignment |
| `discovered_at` | yes | `utc_instant` | UTC instant | — |
| `reason_code` | yes | `slug` | lowercase identifier | — |
| `source_evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |
| `replacement_content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### QuarantineCase

Schema: `qc2.identity_market.QuarantineCase.v1`. Writer: `market_data`. Readers: apexlab, core, evidence, feature, ground_truth, instrument_universe, market_data, prediction, universe, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `instrument_ref`, `observation_ref`, `rule_id`, `reason_code`, `observed_at`, `disposition`, `evidence_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `observation_ref` | yes | `ref<DailyBar>` | typed foreign reference to the listed contract | DailyBar |
| `rule_id` | yes | `slug` | lowercase identifier | — |
| `reason_code` | yes | `slug` | lowercase identifier | — |
| `observed_at` | yes | `utc_instant` | UTC instant | — |
| `disposition` | yes | `enum<QuarantineDisposition>` | enumerated state/dimension; see the named enum | — |
| `evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |


## Scientific definitions

### FeatureDefinition

Schema: `qc2.scientific_definitions.FeatureDefinition.v1`. Writer: `feature`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`, `stable_key`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `stable_key`, `version`, `research_family`, `equation`, `input_refs`, `input_units`, `output_unit`, `output_dtype`, `lookback_sessions`, `warmup_sessions`, `alignment`, `split_treatment`, `precision`, `normalization`, `parameter_profile`, `missingness_policy`, `zero_denominator_policy`, `supported_regime`, `dependency_refs`, `implementation_hash`, `invariance_properties`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `stable_key` | yes | `slug` | lowercase identifier | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `research_family` | yes | `slug` | lowercase identifier | — |
| `equation` | yes | `text` | text | — |
| `input_refs` | yes | `refs<FeatureDefinition|DailyBar|InstrumentClassification|AdjustmentManifest|CalendarManifest|MarketSession>` | typed foreign reference to the listed contract | FeatureDefinition, DailyBar, InstrumentClassification, AdjustmentManifest, CalendarManifest, MarketSession |
| `input_units` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `output_unit` | yes | `text` | text | — |
| `output_dtype` | yes | `enum<FeatureDataType>` | enumerated state/dimension; see the named enum | — |
| `lookback_sessions` | yes | `nonnegative_int` | exchange sessions | — |
| `warmup_sessions` | yes | `nonnegative_int` | exchange sessions | — |
| `alignment` | yes | `text` | text | — |
| `split_treatment` | yes | `enum<FeatureSplitTreatment>` | enumerated state/dimension; see the named enum | — |
| `precision` | yes | `nonnegative_int` | decimal places | — |
| `normalization` | yes | `enum<FeatureNormalization>` | enumerated state/dimension; see the named enum | — |
| `parameter_profile` | yes | `slug` | lowercase identifier | — |
| `missingness_policy` | yes | `enum<MissingnessPolicy>` | enumerated state/dimension; see the named enum | — |
| `zero_denominator_policy` | yes | `enum<ZeroDenominatorPolicy>` | enumerated state/dimension; see the named enum | — |
| `supported_regime` | yes | `slug` | lowercase identifier | — |
| `dependency_refs` | yes | `refs<FeatureDefinition>` | typed foreign reference to the listed contract | FeatureDefinition |
| `implementation_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `invariance_properties` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |

### FeatureRegistry

Schema: `qc2.scientific_definitions.FeatureRegistry.v1`. Writer: `feature`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `registry_version`, `definition_refs`, `ordered_feature_ids`, `effective_from`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `registry_version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `definition_refs` | yes | `refs<FeatureDefinition>` | typed foreign reference to the listed contract | FeatureDefinition |
| `ordered_feature_ids` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `effective_from` | yes | `session` | exchange session date (YYYY-MM-DD) | — |

### FeatureSnapshot

Schema: `qc2.scientific_definitions.FeatureSnapshot.v1`. Writer: `feature`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `session_id`, `instrument_ref`, `registry_ref`, `feature_values`, `input_hashes`, `transform_refs`, `decision_cutoff`, `code_hash`, `environment_fingerprint`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `registry_ref` | yes | `ref<FeatureRegistry>` | typed foreign reference to the listed contract | FeatureRegistry |
| `feature_values` | yes | `feature_value_list` | ordered array; item unit/type is stated by the field | — |
| `input_hashes` | yes | `hash_list` | ordered array; item unit/type is stated by the field | — |
| `transform_refs` | yes | `refs<ArtifactManifest|FeatureDefinition>` | typed foreign reference to the listed contract | ArtifactManifest, FeatureDefinition |
| `decision_cutoff` | yes | `utc_instant` | UTC instant | — |
| `code_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `environment_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### RunnerProtocolDefinition

Schema: `qc2.scientific_definitions.RunnerProtocolDefinition.v1`. Writer: `runner_protocol`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`, `protocol_namespace`, `protocol_id`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `protocol_namespace`, `protocol_id`, `version`, `hypothesis`, `direction`, `input_refs`, `parameter_refs`, `implementation_hash`, `regime`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `protocol_namespace` | yes | `slug` | lowercase identifier | — |
| `protocol_id` | yes | `slug` | lowercase identifier | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `hypothesis` | yes | `text` | text | — |
| `direction` | yes | `enum<SignalDirection>` | enumerated state/dimension; see the named enum | — |
| `input_refs` | yes | `refs<FeatureDefinition|FeatureSnapshot|DailyBar>` | typed foreign reference to the listed contract | FeatureDefinition, FeatureSnapshot, DailyBar |
| `parameter_refs` | yes | `refs<ConfigurationManifest>` | typed foreign reference to the listed contract | ConfigurationManifest |
| `implementation_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `regime` | yes | `slug` | lowercase identifier | — |

### RunnerProtocolRegistry

Schema: `qc2.scientific_definitions.RunnerProtocolRegistry.v1`. Writer: `runner_protocol`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `registry_version`, `definition_refs`, `active_protocol_ids`, `effective_from`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `registry_version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `definition_refs` | yes | `refs<RunnerProtocolDefinition>` | typed foreign reference to the listed contract | RunnerProtocolDefinition |
| `active_protocol_ids` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `effective_from` | yes | `session` | exchange session date (YYYY-MM-DD) | — |

### RunnerProtocolResult

Schema: `qc2.scientific_definitions.RunnerProtocolResult.v1`. Writer: `runner_protocol`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `protocol_ref`, `session_id`, `instrument_ref`, `result`, `hypothesis`, `direction`, `evidence_values`, `uncertainty`, `missingness`, `parameter_hash`, `implementation_hash`, `cutoff`, `input_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `protocol_ref` | yes | `ref<RunnerProtocolDefinition>` | typed foreign reference to the listed contract | RunnerProtocolDefinition |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `result` | yes | `enum<RunnerProtocolResultState>` | enumerated state/dimension; see the named enum | — |
| `hypothesis` | yes | `text` | text | — |
| `direction` | yes | `enum<SignalDirection>` | enumerated state/dimension; see the named enum | — |
| `evidence_values` | yes | `evidence_value_list` | ordered array; item unit/type is stated by the field | — |
| `uncertainty` | yes | `nullable_continuous_decimal` | exact decimal; semantic unit is declared in the owning field definition | — |
| `missingness` | yes | `enum<MissingnessStatus>` | enumerated state/dimension; see the named enum | — |
| `parameter_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `implementation_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `cutoff` | yes | `utc_instant` | UTC instant | — |
| `input_refs` | yes | `refs<FeatureSnapshot|MarketSnapshot|DailyBar|RunnerProtocolResult>` | typed foreign reference to the listed contract | FeatureSnapshot, MarketSnapshot, DailyBar, RunnerProtocolResult |

### SafetyProtocolDefinition

Schema: `qc2.scientific_definitions.SafetyProtocolDefinition.v1`. Writer: `safety`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`, `protocol_key`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `protocol_key`, `version`, `action`, `rule`, `required_evidence`, `warning_policy`, `implementation_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `protocol_key` | yes | `slug` | lowercase identifier | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `action` | yes | `enum<ReadinessAction>` | enumerated state/dimension; see the named enum | — |
| `rule` | yes | `text` | text | — |
| `required_evidence` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `warning_policy` | yes | `enum<WarningPolicy>` | enumerated state/dimension; see the named enum | — |
| `implementation_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### SafetyProtocolResult

Schema: `qc2.scientific_definitions.SafetyProtocolResult.v1`. Writer: `safety`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `protocol_ref`, `action`, `result`, `reason_codes`, `observed_versions`, `evaluated_at`, `freshness_deadline`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `protocol_ref` | yes | `ref<SafetyProtocolDefinition>` | typed foreign reference to the listed contract | SafetyProtocolDefinition |
| `action` | yes | `enum<ReadinessAction>` | enumerated state/dimension; see the named enum | — |
| `result` | yes | `enum<SafetyResultState>` | enumerated state/dimension; see the named enum | — |
| `reason_codes` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `observed_versions` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `evaluated_at` | yes | `utc_instant` | UTC instant | — |
| `freshness_deadline` | yes | `utc_instant` | UTC instant | — |

### LabelDefinition

Schema: `qc2.scientific_definitions.LabelDefinition.v1`. Writer: `label`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`, `stable_key`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `stable_key`, `version`, `horizon_sessions`, `price_reference`, `target_event`, `maturity_rule`, `release_policy`, `threshold`, `threshold_unit`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `stable_key` | yes | `slug` | lowercase identifier | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `horizon_sessions` | yes | `positive_int` | exchange sessions | — |
| `price_reference` | yes | `enum<PriceReference>` | enumerated state/dimension; see the named enum | — |
| `target_event` | yes | `enum<LabelTarget>` | enumerated state/dimension; see the named enum | — |
| `maturity_rule` | yes | `text` | text | — |
| `release_policy` | yes | `text` | text | — |
| `threshold` | yes | `nullable_continuous_decimal` | exact decimal; semantic unit is declared in the owning field definition | — |
| `threshold_unit` | yes | `nullable_text` | text | — |

### LabelRegistry

Schema: `qc2.scientific_definitions.LabelRegistry.v1`. Writer: `label`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `registry_version`, `definition_refs`, `primary_label_ref`, `effective_from`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `registry_version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `definition_refs` | yes | `refs<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `primary_label_ref` | yes | `ref<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `effective_from` | yes | `session` | exchange session date (YYYY-MM-DD) | — |

### ScoreDefinition

Schema: `qc2.scientific_definitions.ScoreDefinition.v1`. Writer: `quantscore`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`, `stable_key`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `stable_key`, `version`, `coefficients`, `transforms`, `clipping_policy`, `missing_head_policy`, `tie_break_rule`, `input_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `stable_key` | yes | `slug` | lowercase identifier | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `coefficients` | yes | `continuous_decimal_list` | ordered dimensionless coefficients; each uses 12 decimal places | — |
| `transforms` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `clipping_policy` | yes | `text` | text | — |
| `missing_head_policy` | yes | `enum<MissingHeadPolicy>` | enumerated state/dimension; see the named enum | — |
| `tie_break_rule` | yes | `text` | text | — |
| `input_refs` | yes | `refs<ModelHeadDefinition|RunnerProtocolResult|FeatureDefinition|FeatureSnapshot>` | typed foreign reference to the listed contract | ModelHeadDefinition, RunnerProtocolResult, FeatureDefinition, FeatureSnapshot |

Invariants:
- coefficient values are dimensionless signed decimals with exactly 12 places and round-half-even serialization

### ScoreManifest

Schema: `qc2.scientific_definitions.ScoreManifest.v1`. Writer: `quantscore`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `definition_ref`, `score_precision`, `score_unit`, `frozen_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `definition_ref` | yes | `ref<ScoreDefinition>` | typed foreign reference to the listed contract | ScoreDefinition |
| `score_precision` | yes | `positive_int` | decimal places | — |
| `score_unit` | yes | `text` | text | — |
| `frozen_at` | yes | `utc_instant` | UTC instant | — |

Invariants:
- QuantraScore uses exactly 6 decimal places

### BaselineManifest

Schema: `qc2.scientific_definitions.BaselineManifest.v1`. Writer: `validation`. Readers: apexlab, feature, inference, label, model_registry, owner_api, prediction, quantscore, runner_protocol, safety, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `baseline_kind`, `version`, `algorithm`, `parameter_refs`, `seed_hash`, `comparator_role`, `tie_break_rule`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `baseline_kind` | yes | `enum<BaselineKind>` | enumerated state/dimension; see the named enum | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `algorithm` | yes | `text` | text | — |
| `parameter_refs` | yes | `refs<ConfigurationManifest>` | typed foreign reference to the listed contract | ConfigurationManifest |
| `seed_hash` | yes | `nullable_sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `comparator_role` | yes | `enum<ComparatorRole>` | enumerated state/dimension; see the named enum | — |
| `tie_break_rule` | yes | `text` | text | — |


## Models and prediction

### ModelManifest

Schema: `qc2.models_prediction.ModelManifest.v1`. Writer: `model_registry`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `artifact_manifest_ref`, `safe_format`, `algorithm`, `algorithm_version`, `target_label_refs`, `feature_registry_ref`, `ordered_feature_ids`, `protocol_registry_ref`, `training_start`, `training_cutoff`, `validation_window`, `qualification_window`, `dataset_ref`, `split_ref`, `seed`, `hyperparameter_refs`, `calibration_ref`, `package_lock_hash`, `environment_fingerprint`, `learned_dependency_refs`, `resource_constraints`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `artifact_manifest_ref` | yes | `ref<ArtifactManifest>` | typed foreign reference to the listed contract | ArtifactManifest |
| `safe_format` | yes | `slug` | lowercase identifier | — |
| `algorithm` | yes | `slug` | lowercase identifier | — |
| `algorithm_version` | yes | `text` | text | — |
| `target_label_refs` | yes | `refs<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `feature_registry_ref` | yes | `ref<FeatureRegistry>` | typed foreign reference to the listed contract | FeatureRegistry |
| `ordered_feature_ids` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `protocol_registry_ref` | yes | `ref<RunnerProtocolRegistry>` | typed foreign reference to the listed contract | RunnerProtocolRegistry |
| `training_start` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `training_cutoff` | yes | `utc_instant` | UTC instant | — |
| `validation_window` | yes | `text` | text | — |
| `qualification_window` | yes | `text` | text | — |
| `dataset_ref` | yes | `ref<DatasetManifest>` | typed foreign reference to the listed contract | DatasetManifest |
| `split_ref` | yes | `ref<SplitManifest>` | typed foreign reference to the listed contract | SplitManifest |
| `seed` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `hyperparameter_refs` | yes | `refs<ConfigurationManifest|ArtifactManifest>` | typed foreign reference to the listed contract | ConfigurationManifest, ArtifactManifest |
| `calibration_ref` | yes | `nullable_ref<ArtifactManifest>` | typed foreign reference to the listed contract | — |
| `package_lock_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `environment_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `learned_dependency_refs` | yes | `refs<RunnerGenome|FailureGenome|MemoryIndexManifest|ArtifactManifest|FeatureDefinition|DatasetManifest>` | typed foreign reference to the listed contract | RunnerGenome, FailureGenome, MemoryIndexManifest, ArtifactManifest, FeatureDefinition, DatasetManifest |
| `resource_constraints` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `lifecycle_state` | yes | `enum<ModelLifecycle>` | enumerated state/dimension; see the named enum | — |

State field: `lifecycle_state`. Guard: Artifact bytes are immutable; lifecycle facts advance without overwriting the artifact.

| From | Allowed next states |
|---|---|
| `RESEARCH` | `CANDIDATE`, `REJECTED` |
| `CANDIDATE` | `CHALLENGER`, `REJECTED` |
| `CHALLENGER` | `SHADOW`, `REJECTED` |
| `SHADOW` | `PROMOTION_ELIGIBLE`, `REJECTED`, `RETIRED` |
| `PROMOTION_ELIGIBLE` | `CHAMPION`, `REJECTED`, `RETIRED` |
| `CHAMPION` | `RETIRED` |

### ModelHeadDefinition

Schema: `qc2.models_prediction.ModelHeadDefinition.v1`. Writer: `model_registry`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`, `model_ref`, `head_name`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `model_ref`, `head_name`, `output_kind`, `label_ref`, `horizon_sessions`, `availability`, `output_precision`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `head_name` | yes | `slug` | lowercase identifier | — |
| `output_kind` | yes | `enum<ModelHeadKind>` | enumerated state/dimension; see the named enum | — |
| `label_ref` | yes | `ref<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `horizon_sessions` | yes | `positive_int` | exchange sessions | — |
| `availability` | yes | `enum<HeadAvailability>` | enumerated state/dimension; see the named enum | — |
| `output_precision` | yes | `positive_int` | decimal places | — |

Invariants:
- SCORE outputs declare 6 decimal places; every other continuous model-head kind declares 12

### ModelHeadOutput

Schema: `qc2.models_prediction.ModelHeadOutput.v1`. Writer: `inference`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `head_ref`, `instrument_ref`, `session_id`, `output_value`, `output_unit`, `availability`, `reason_code`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `head_ref` | yes | `ref<ModelHeadDefinition>` | typed foreign reference to the listed contract | ModelHeadDefinition |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `output_value` | yes | `nullable_decimal` | exact decimal; semantic unit is declared in the owning field definition | — |
| `output_unit` | yes | `text` | text | — |
| `availability` | yes | `enum<HeadAvailability>` | enumerated state/dimension; see the named enum | — |
| `reason_code` | yes | `nullable_text` | text | — |

Invariants:
- AVAILABLE requires a decimal output and no reason; unavailable or invalid heads require null plus an explicit reason
- output_value uses exactly the output_precision registered by its referenced ModelHeadDefinition

### InferenceReceipt

Schema: `qc2.models_prediction.InferenceReceipt.v1`. Writer: `inference`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `model_ref`, `loaded_artifact_hash`, `generation`, `environment_fingerprint`, `probe_set_hash`, `output_hash`, `evaluated_at`, `deterministic`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `loaded_artifact_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `generation` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `environment_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `probe_set_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `output_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `evaluated_at` | yes | `utc_instant` | UTC instant | — |
| `deterministic` | yes | `boolean` | not applicable | — |

### PredictionRun

Schema: `qc2.models_prediction.PredictionRun.v1`. Writer: `prediction`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_ref`, `session_id`, `snapshot_ref`, `dependency_refs`, `decision_deadline`, `seal_deadline`, `generation`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `snapshot_ref` | yes | `ref<MarketSnapshot>` | typed foreign reference to the listed contract | MarketSnapshot |
| `dependency_refs` | yes | `refs<CalendarManifest|FeatureRegistry|RunnerProtocolRegistry|LabelRegistry|ScoreManifest|ModelManifest|ChampionPointer|ShadowPredictionSet|BaselineManifest|MemoryIndexManifest>` | typed foreign reference to the listed contract | CalendarManifest, FeatureRegistry, RunnerProtocolRegistry, LabelRegistry, ScoreManifest, ModelManifest, ChampionPointer, ShadowPredictionSet, BaselineManifest, MemoryIndexManifest |
| `decision_deadline` | yes | `utc_instant` | UTC instant | — |
| `seal_deadline` | yes | `utc_instant` | UTC instant | — |
| `run_state` | yes | `enum<PredictionRunState>` | enumerated state/dimension; see the named enum | — |
| `generation` | yes | `positive_int` | integer count (unit is named by the field) | — |

State field: `run_state`. Guard: SEALED is terminal; all bindings precede feature work and a sealed payload is never edited.

| From | Allowed next states |
|---|---|
| `CREATED` | `INPUTS_BOUND`, `ABORTED`, `FAILED_BEFORE_SEAL` |
| `INPUTS_BOUND` | `FEATURES_COMPLETE`, `ABORTED`, `FAILED_BEFORE_SEAL` |
| `FEATURES_COMPLETE` | `SCORED`, `ABORTED`, `FAILED_BEFORE_SEAL` |
| `SCORED` | `RANKED`, `ABORTED`, `FAILED_BEFORE_SEAL` |
| `RANKED` | `SEALED`, `ABORTED`, `FAILED_BEFORE_SEAL` |

### Prediction

Schema: `qc2.models_prediction.Prediction.v1`. Writer: `prediction`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`, `run_ref`, `instrument_ref`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `run_ref`, `session_id`, `instrument_ref`, `reference_kind`, `reference_price`, `horizon_label_refs`, `head_output_refs`, `feature_snapshot_ref`, `protocol_result_refs`, `score_manifest_ref`, `score`, `rank`, `disposition`, `unscorable_reason`, `model_ref`, `learned_memory_refs`, `epoch_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `run_ref` | yes | `ref<PredictionRun>` | typed foreign reference to the listed contract | PredictionRun |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `reference_kind` | yes | `enum<PriceReference>` | enumerated state/dimension; see the named enum | — |
| `reference_price` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `horizon_label_refs` | yes | `refs<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `head_output_refs` | yes | `refs<ModelHeadOutput>` | typed foreign reference to the listed contract | ModelHeadOutput |
| `feature_snapshot_ref` | yes | `ref<FeatureSnapshot>` | typed foreign reference to the listed contract | FeatureSnapshot |
| `protocol_result_refs` | yes | `refs<RunnerProtocolResult>` | typed foreign reference to the listed contract | RunnerProtocolResult |
| `score_manifest_ref` | yes | `ref<ScoreManifest>` | typed foreign reference to the listed contract | ScoreManifest |
| `score` | yes | `nullable_score` | QuantraScore points on [0, 100] | — |
| `rank` | yes | `nullable_positive_int` | ordinal/count (unit is named by the field) | — |
| `disposition` | yes | `enum<PredictionRowDisposition>` | enumerated state/dimension; see the named enum | — |
| `unscorable_reason` | yes | `nullable_slug` | lowercase identifier | — |
| `model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `learned_memory_refs` | yes | `refs<RunnerGenome|FailureGenome|MemoryIndexManifest|MatchedDecoySet>` | typed foreign reference to the listed contract | RunnerGenome, FailureGenome, MemoryIndexManifest, MatchedDecoySet |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |

Invariants:
- SCORED requires score and positive rank and forbids an unscorable reason
- UNSCORABLE requires null score/rank and a reason code

### ScientificPredictionPayload

Schema: `qc2.models_prediction.ScientificPredictionPayload.v1`. Writer: `prediction`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `session_id`, `reference_kind`, `reference_price`, `instrument_ref`, `horizon_label_refs`, `head_output_refs`, `dependency_refs`, `score`, `rank`, `disposition`, `model_hash`, `epoch_ref`, `regime`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `reference_kind` | yes | `enum<PriceReference>` | enumerated state/dimension; see the named enum | — |
| `reference_price` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `horizon_label_refs` | yes | `refs<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `head_output_refs` | yes | `refs<ModelHeadOutput>` | typed foreign reference to the listed contract | ModelHeadOutput |
| `dependency_refs` | yes | `refs<FeatureSnapshot|RunnerProtocolResult|ScoreManifest|ModelManifest|MemoryIndexManifest|ValidationEpoch>` | typed foreign reference to the listed contract | FeatureSnapshot, RunnerProtocolResult, ScoreManifest, ModelManifest, MemoryIndexManifest, ValidationEpoch |
| `score` | yes | `score` | QuantraScore points on [0, 100] | — |
| `rank` | yes | `positive_int` | ordinal/count (unit is named by the field) | — |
| `disposition` | yes | `enum<PredictionRowDisposition>` | enumerated state/dimension; see the named enum | — |
| `model_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `regime` | yes | `slug` | lowercase identifier | — |

### PredictionSeal

Schema: `qc2.models_prediction.PredictionSeal.v1`. Writer: `prediction`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `run_ref`, `session_id`, `role`, `ordered_prediction_refs`, `disposition_counts`, `payload_inventory_hash`, `deadline`, `sealed_at`, `evidence_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `run_ref` | yes | `ref<PredictionRun>` | typed foreign reference to the listed contract | PredictionRun |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `role` | yes | `enum<PredictionRole>` | enumerated state/dimension; see the named enum | — |
| `ordered_prediction_refs` | yes | `refs<Prediction>` | typed foreign reference to the listed contract | Prediction |
| `disposition_counts` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `payload_inventory_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `deadline` | yes | `utc_instant` | UTC instant | — |
| `sealed_at` | yes | `utc_instant` | UTC instant | — |
| `evidence_refs` | yes | `refs<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |

### RunDisposition

Schema: `qc2.models_prediction.RunDisposition.v1`. Writer: `prediction`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `run_ref`, `instrument_ref`, `disposition`, `reason_code`, `observed_at`, `evidence_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `run_ref` | yes | `ref<PredictionRun>` | typed foreign reference to the listed contract | PredictionRun |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `disposition` | yes | `enum<PredictionDisposition>` | enumerated state/dimension; see the named enum | — |
| `reason_code` | yes | `slug` | lowercase identifier | — |
| `observed_at` | yes | `utc_instant` | UTC instant | — |
| `evidence_refs` | yes | `refs<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |

### ShadowPredictionSet

Schema: `qc2.models_prediction.ShadowPredictionSet.v1`. Writer: `prediction`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `model_ref`, `eligible_at`, `target_label_refs`, `comparison_window_sessions`, `comparator_refs`, `registration_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `eligible_at` | yes | `utc_instant` | UTC instant | — |
| `target_label_refs` | yes | `refs<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `comparison_window_sessions` | yes | `positive_int` | exchange sessions | — |
| `comparator_refs` | yes | `refs<ModelManifest|BaselineManifest|ChampionPointer>` | typed foreign reference to the listed contract | ModelManifest, BaselineManifest, ChampionPointer |
| `registration_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### ReplayRequest

Schema: `qc2.models_prediction.ReplayRequest.v1`. Writer: `validation`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `source_seal_ref`, `requested_at`, `environment_fingerprint`, `reason_code`, `replay_mode`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `source_seal_ref` | yes | `ref<PredictionSeal>` | typed foreign reference to the listed contract | PredictionSeal |
| `requested_at` | yes | `utc_instant` | UTC instant | — |
| `environment_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `reason_code` | yes | `slug` | lowercase identifier | — |
| `replay_mode` | yes | `enum<ReplayMode>` | enumerated state/dimension; see the named enum | — |

### ReplayReceipt

Schema: `qc2.models_prediction.ReplayReceipt.v1`. Writer: `validation`. Readers: apexlab, evidence, execution, inference, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `request_ref`, `expected_hash`, `actual_hash`, `expected_count`, `actual_count`, `environment_fingerprint`, `first_mismatch`, `duration_ms`, `verdict`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `request_ref` | yes | `ref<ReplayRequest>` | typed foreign reference to the listed contract | ReplayRequest |
| `expected_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `actual_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `expected_count` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `actual_count` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `environment_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `first_mismatch` | yes | `nullable_text` | text | — |
| `duration_ms` | yes | `nonnegative_int` | milliseconds | — |
| `verdict` | yes | `enum<ReplayVerdict>` | enumerated state/dimension; see the named enum | — |


## Outcomes and research

### Outcome

Schema: `qc2.outcomes_research.Outcome.v1`. Writer: `ground_truth`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`, `instrument_ref`, `session_id`, `label_ref`, `horizon_sessions`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `instrument_ref`, `session_id`, `label_ref`, `horizon_sessions`, `reference_bar_ref`, `reference_price`, `next_open_bar_ref`, `next_open_reference_price`, `outcome_state`, `endpoint_return`, `max_high_return`, `min_low_return`, `mfe`, `mae`, `max_high_price`, `max_high_session`, `max_high_session_offset`, `min_low_price`, `min_low_session`, `min_low_session_offset`, `extrema_tie_break`, `opening_gap_return`, `next_open_proxy_endpoint_return`, `next_open_proxy_max_high_return`, `next_open_proxy_min_low_return`, `next_open_proxy_mfe`, `next_open_proxy_mae`, `field_validity`, `reason_codes`, `available_for_learning_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `refs<DailyBar|CorporateActionRecord|MarketSnapshotRevision>` | typed foreign reference to the listed contract | DailyBar, CorporateActionRecord, MarketSnapshotRevision |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `label_ref` | yes | `ref<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `horizon_sessions` | yes | `positive_int` | exchange sessions | — |
| `reference_bar_ref` | yes | `ref<DailyBar>` | typed foreign reference to the listed contract | DailyBar |
| `reference_price` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `next_open_bar_ref` | yes | `nullable_ref<DailyBar>` | typed foreign reference to the listed contract | — |
| `next_open_reference_price` | yes | `nullable_positive_decimal` | currency specified by the adjacent currency field per share | — |
| `outcome_state` | yes | `enum<OutcomeState>` | enumerated state/dimension; see the named enum | — |
| `endpoint_return` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `max_high_return` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `min_low_return` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `mfe` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `mae` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `max_high_price` | yes | `nullable_positive_decimal` | currency specified by the adjacent currency field per share | — |
| `max_high_session` | yes | `nullable_session` | exchange session date (YYYY-MM-DD) | — |
| `max_high_session_offset` | yes | `nullable_positive_int` | exchange sessions | — |
| `min_low_price` | yes | `nullable_positive_decimal` | currency specified by the adjacent currency field per share | — |
| `min_low_session` | yes | `nullable_session` | exchange session date (YYYY-MM-DD) | — |
| `min_low_session_offset` | yes | `nullable_positive_int` | exchange sessions | — |
| `extrema_tie_break` | yes | `enum<ExtremaTieBreak>` | enumerated state/dimension; see the named enum | — |
| `opening_gap_return` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `next_open_proxy_endpoint_return` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `next_open_proxy_max_high_return` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `next_open_proxy_min_low_return` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `next_open_proxy_mfe` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `next_open_proxy_mae` | yes | `nullable_continuous_decimal` | fractional return (1.0 = 100%) | — |
| `field_validity` | yes | `outcome_field_validity_list` | ordered array; item unit/type is stated by the field | — |
| `reason_codes` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `available_for_learning_at` | yes | `nullable_utc_instant` | UTC instant | — |

Invariants:
- MFE=max(0,max_high_return) and MAE=min(0,min_low_return)
- next-open-proxy endpoint, extrema, MFE, and MAE use the next-session open denominator and remain separate from close-reference outcomes
- peak/trough price, session, positive session offset, and earliest-session tie-break preserve the observed extrema
- field validity and explicit reason preserve unknown, unavailable, or censored measurements

### OutcomeRevision

Schema: `qc2.outcomes_research.OutcomeRevision.v1`. Writer: `ground_truth`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `prior_outcome_ref`, `replacement_outcome_ref`, `revision_reason`, `discovered_at`, `correction_policy_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `refs<RawReceipt|DailyBar|CorporateActionRecord|EvidenceEvent|DataBundle>` | typed foreign reference to the listed contract | RawReceipt, DailyBar, CorporateActionRecord, EvidenceEvent, DataBundle |
| `prior_outcome_ref` | yes | `ref<Outcome>` | typed foreign reference to the listed contract | Outcome |
| `replacement_outcome_ref` | yes | `ref<Outcome>` | typed foreign reference to the listed contract | Outcome |
| `revision_reason` | yes | `slug` | lowercase identifier | — |
| `discovered_at` | yes | `utc_instant` | UTC instant | — |
| `correction_policy_ref` | yes | `ref<ConfigurationManifest>` | typed foreign reference to the listed contract | ConfigurationManifest |

### RunnerEvent

Schema: `qc2.outcomes_research.RunnerEvent.v1`. Writer: `ground_truth`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `instrument_ref`, `event_type`, `start_session`, `end_session`, `label_ref`, `outcome_ref`, `detected_at`, `evidence_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `event_type` | yes | `enum<RunnerEventType>` | enumerated state/dimension; see the named enum | — |
| `start_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `end_session` | yes | `nullable_session` | exchange session date (YYYY-MM-DD) | — |
| `label_ref` | yes | `ref<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `outcome_ref` | yes | `ref<Outcome>` | typed foreign reference to the listed contract | Outcome |
| `detected_at` | yes | `utc_instant` | UTC instant | — |
| `evidence_refs` | yes | `refs<EvidenceEvent|OutcomeRevision>` | typed foreign reference to the listed contract | EvidenceEvent, OutcomeRevision |

### RunnerGenome

Schema: `qc2.outcomes_research.RunnerGenome.v1`. Writer: `apexlab`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `event_ref`, `pre_event_snapshot_refs`, `prediction_refs`, `outcome_refs`, `provenance_refs`, `curation_version`, `event_time`, `available_for_learning_at`, `temporal_dependency_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `event_ref` | yes | `ref<RunnerEvent>` | typed foreign reference to the listed contract | RunnerEvent |
| `pre_event_snapshot_refs` | yes | `refs<MarketSnapshot|FeatureSnapshot>` | typed foreign reference to the listed contract | MarketSnapshot, FeatureSnapshot |
| `prediction_refs` | yes | `refs<Prediction>` | typed foreign reference to the listed contract | Prediction |
| `outcome_refs` | yes | `refs<Outcome>` | typed foreign reference to the listed contract | Outcome |
| `provenance_refs` | yes | `refs<EvidenceEvent|DataBundle|OutcomeRevision>` | typed foreign reference to the listed contract | EvidenceEvent, DataBundle, OutcomeRevision |
| `curation_version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `event_time` | yes | `utc_instant` | UTC instant | — |
| `available_for_learning_at` | yes | `utc_instant` | UTC instant | — |
| `temporal_dependency_refs` | yes | `refs<MarketSnapshot|FeatureSnapshot|Prediction|Outcome|OutcomeRevision|EvidenceEvent>` | typed foreign reference to the listed contract | MarketSnapshot, FeatureSnapshot, Prediction, Outcome, OutcomeRevision, EvidenceEvent |

### FailureGenome

Schema: `qc2.outcomes_research.FailureGenome.v1`. Writer: `apexlab`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `event_ref`, `failure_type`, `pre_event_snapshot_refs`, `prediction_refs`, `outcome_refs`, `provenance_refs`, `curation_version`, `event_time`, `available_for_learning_at`, `temporal_dependency_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `event_ref` | yes | `ref<RunnerEvent>` | typed foreign reference to the listed contract | RunnerEvent |
| `failure_type` | yes | `enum<FailureType>` | enumerated state/dimension; see the named enum | — |
| `pre_event_snapshot_refs` | yes | `refs<MarketSnapshot|FeatureSnapshot>` | typed foreign reference to the listed contract | MarketSnapshot, FeatureSnapshot |
| `prediction_refs` | yes | `refs<Prediction>` | typed foreign reference to the listed contract | Prediction |
| `outcome_refs` | yes | `refs<Outcome>` | typed foreign reference to the listed contract | Outcome |
| `provenance_refs` | yes | `refs<EvidenceEvent|DataBundle|OutcomeRevision>` | typed foreign reference to the listed contract | EvidenceEvent, DataBundle, OutcomeRevision |
| `curation_version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `event_time` | yes | `utc_instant` | UTC instant | — |
| `available_for_learning_at` | yes | `utc_instant` | UTC instant | — |
| `temporal_dependency_refs` | yes | `refs<MarketSnapshot|FeatureSnapshot|Prediction|Outcome|OutcomeRevision|EvidenceEvent>` | typed foreign reference to the listed contract | MarketSnapshot, FeatureSnapshot, Prediction, Outcome, OutcomeRevision, EvidenceEvent |

### MemoryIndexManifest

Schema: `qc2.outcomes_research.MemoryIndexManifest.v1`. Writer: `apexlab`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `index_kind`, `member_refs`, `member_inventory_hash`, `cutoff`, `available_for_learning_at`, `embedding_artifact_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `index_kind` | yes | `enum<MemoryIndexKind>` | enumerated state/dimension; see the named enum | — |
| `member_refs` | yes | `refs<RunnerGenome|FailureGenome|MatchedDecoySet>` | typed foreign reference to the listed contract | RunnerGenome, FailureGenome, MatchedDecoySet |
| `member_inventory_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `cutoff` | yes | `utc_instant` | UTC instant | — |
| `available_for_learning_at` | yes | `utc_instant` | UTC instant | — |
| `embedding_artifact_ref` | yes | `nullable_ref<ArtifactManifest>` | typed foreign reference to the listed contract | — |

### MatchedDecoySet

Schema: `qc2.outcomes_research.MatchedDecoySet.v1`. Writer: `apexlab`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `positive_event_refs`, `decoy_instrument_refs`, `matching_procedure_hash`, `pre_outcome_variable_ids`, `strata`, `calipers`, `unmatched_cases`, `outcome_membership_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `positive_event_refs` | yes | `refs<RunnerEvent>` | typed foreign reference to the listed contract | RunnerEvent |
| `decoy_instrument_refs` | yes | `refs<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `matching_procedure_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `pre_outcome_variable_ids` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `strata` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `calipers` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `unmatched_cases` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `outcome_membership_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### ReviewCase

Schema: `qc2.outcomes_research.ReviewCase.v1`. Writer: `apexlab`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `review_kind`, `event_ref`, `prediction_ref`, `disposition`, `reason_codes`, `reviewed_at`, `evidence_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `review_kind` | yes | `enum<ReviewKind>` | enumerated state/dimension; see the named enum | — |
| `event_ref` | yes | `ref<RunnerEvent>` | typed foreign reference to the listed contract | RunnerEvent |
| `prediction_ref` | yes | `nullable_ref<Prediction>` | typed foreign reference to the listed contract | — |
| `disposition` | yes | `enum<PredictionDisposition>` | enumerated state/dimension; see the named enum | — |
| `reason_codes` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `reviewed_at` | yes | `utc_instant` | UTC instant | — |
| `evidence_refs` | yes | `refs<EvidenceEvent|Outcome|RunnerEvent>` | typed foreign reference to the listed contract | EvidenceEvent, Outcome, RunnerEvent |

### DatasetManifest

Schema: `qc2.outcomes_research.DatasetManifest.v1`. Writer: `apexlab`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `universe_fidelity`, `snapshot_refs`, `raw_receipt_refs`, `action_refs`, `registry_refs`, `memory_cutoff`, `availability_policy`, `row_lineage_hash`, `membership_hash`, `time_start`, `time_end`, `symbol_count`, `missingness_counts`, `revision_refs`, `split_assignment_hash`, `normalization_ref`, `sampling_policy`, `artifact_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `universe_fidelity` | yes | `enum<UniverseFidelity>` | enumerated state/dimension; see the named enum | — |
| `snapshot_refs` | yes | `refs<MarketSnapshot>` | typed foreign reference to the listed contract | MarketSnapshot |
| `raw_receipt_refs` | yes | `refs<RawReceipt>` | typed foreign reference to the listed contract | RawReceipt |
| `action_refs` | yes | `refs<CorporateActionRecord>` | typed foreign reference to the listed contract | CorporateActionRecord |
| `registry_refs` | yes | `refs<FeatureRegistry|RunnerProtocolRegistry|LabelRegistry|ScoreManifest|BaselineManifest>` | typed foreign reference to the listed contract | FeatureRegistry, RunnerProtocolRegistry, LabelRegistry, ScoreManifest, BaselineManifest |
| `memory_cutoff` | yes | `utc_instant` | UTC instant | — |
| `availability_policy` | yes | `enum<AvailabilityPolicy>` | enumerated state/dimension; see the named enum | — |
| `row_lineage_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `membership_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `time_start` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `time_end` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `symbol_count` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `missingness_counts` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `revision_refs` | yes | `refs<MarketSnapshotRevision|OutcomeRevision>` | typed foreign reference to the listed contract | MarketSnapshotRevision, OutcomeRevision |
| `split_assignment_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `normalization_ref` | yes | `ref<AdjustmentManifest>` | typed foreign reference to the listed contract | AdjustmentManifest |
| `sampling_policy` | yes | `text` | text | — |
| `artifact_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

Invariants:
- dataset and split lineage is immutable and availability-cutoff filtered

### DatasetRowLineage

Schema: `qc2.outcomes_research.DatasetRowLineage.v1`. Writer: `apexlab`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `dataset_ref`, `row_key`, `instrument_ref`, `session_id`, `horizon_sessions`, `target_ref`, `lineage_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `refs<MarketSnapshot|DailyBar|Outcome|FeatureSnapshot|Prediction|EvidenceEvent>` | typed foreign reference to the listed contract | MarketSnapshot, DailyBar, Outcome, FeatureSnapshot, Prediction, EvidenceEvent |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `dataset_ref` | yes | `ref<DatasetManifest>` | typed foreign reference to the listed contract | DatasetManifest |
| `row_key` | yes | `slug` | lowercase identifier | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `horizon_sessions` | yes | `positive_int` | exchange sessions | — |
| `target_ref` | yes | `ref<LabelDefinition>` | typed foreign reference to the listed contract | LabelDefinition |
| `lineage_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### SplitManifest

Schema: `qc2.outcomes_research.SplitManifest.v1`. Writer: `apexlab`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `dataset_ref`, `split_unit`, `training_intervals`, `validation_intervals`, `qualification_interval`, `purge_sessions`, `embargo_sessions`, `cutoff_policy`, `split_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `dataset_ref` | yes | `ref<DatasetManifest>` | typed foreign reference to the listed contract | DatasetManifest |
| `split_unit` | yes | `enum<SplitUnit>` | enumerated state/dimension; see the named enum | — |
| `training_intervals` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `validation_intervals` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `qualification_interval` | yes | `text` | text | — |
| `purge_sessions` | yes | `nonnegative_int` | exchange sessions | — |
| `embargo_sessions` | yes | `nonnegative_int` | exchange sessions | — |
| `cutoff_policy` | yes | `text` | text | — |
| `split_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### HoldoutAccessReceipt

Schema: `qc2.outcomes_research.HoldoutAccessReceipt.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `dataset_ref`, `evaluator_identity`, `access_scope`, `requested_at`, `granted_at`, `consumed_fields`, `released_metrics`, `receipt_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `dataset_ref` | yes | `ref<DatasetManifest>` | typed foreign reference to the listed contract | DatasetManifest |
| `evaluator_identity` | yes | `text` | text | — |
| `access_scope` | yes | `enum<HoldoutAccessScope>` | enumerated state/dimension; see the named enum | — |
| `requested_at` | yes | `utc_instant` | UTC instant | — |
| `granted_at` | yes | `utc_instant` | UTC instant | — |
| `consumed_fields` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `released_metrics` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `receipt_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### Experiment

Schema: `qc2.outcomes_research.Experiment.v1`. Writer: `apexlab`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `hypothesis`, `search_space_hash`, `code_hash`, `environment_fingerprint`, `dataset_ref`, `split_ref`, `candidate_refs`, `algorithm`, `seed`, `configuration_ref`, `budget_ref`, `compute_cost`, `evaluation_access`, `result_ref`, `rejection_reason`, `artifact_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `hypothesis` | yes | `text` | text | — |
| `search_space_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `code_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `environment_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `dataset_ref` | yes | `ref<DatasetManifest>` | typed foreign reference to the listed contract | DatasetManifest |
| `split_ref` | yes | `ref<SplitManifest>` | typed foreign reference to the listed contract | SplitManifest |
| `candidate_refs` | yes | `refs<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `algorithm` | yes | `slug` | lowercase identifier | — |
| `seed` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `configuration_ref` | yes | `ref<ConfigurationManifest>` | typed foreign reference to the listed contract | ConfigurationManifest |
| `budget_ref` | yes | `ref<ResourceBudget>` | typed foreign reference to the listed contract | ResourceBudget |
| `compute_cost` | yes | `decimal` | currency amount in the adjacent currency field | — |
| `evaluation_access` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `result_ref` | yes | `nullable_ref<CandidateEvaluation>` | typed foreign reference to the listed contract | — |
| `rejection_reason` | yes | `nullable_text` | text | — |
| `artifact_refs` | yes | `refs<ArtifactManifest>` | typed foreign reference to the listed contract | ArtifactManifest |

### CandidateEvaluation

Schema: `qc2.outcomes_research.CandidateEvaluation.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `candidate_ref`, `evaluator_identity`, `dataset_ref`, `split_ref`, `gate_results`, `evaluated_at`, `verdict`, `report_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `candidate_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `evaluator_identity` | yes | `text` | text | — |
| `dataset_ref` | yes | `ref<DatasetManifest>` | typed foreign reference to the listed contract | DatasetManifest |
| `split_ref` | yes | `ref<SplitManifest>` | typed foreign reference to the listed contract | SplitManifest |
| `gate_results` | yes | `gate_result_list` | ordered array; item unit/type is stated by the field | — |
| `evaluated_at` | yes | `utc_instant` | UTC instant | — |
| `verdict` | yes | `enum<EvaluationVerdict>` | enumerated state/dimension; see the named enum | — |
| `report_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### ChallengerEvaluation

Schema: `qc2.outcomes_research.ChallengerEvaluation.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `challenger_ref`, `reference_model_ref`, `evaluator_identity`, `comparison_window`, `gate_results`, `evaluated_at`, `verdict`, `report_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `challenger_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `reference_model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `evaluator_identity` | yes | `text` | text | — |
| `comparison_window` | yes | `text` | text | — |
| `gate_results` | yes | `gate_result_list` | ordered array; item unit/type is stated by the field | — |
| `evaluated_at` | yes | `utc_instant` | UTC instant | — |
| `verdict` | yes | `enum<EvaluationVerdict>` | enumerated state/dimension; see the named enum | — |
| `report_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### DriftAssessment

Schema: `qc2.outcomes_research.DriftAssessment.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `model_ref`, `reference_window`, `current_window`, `metric_refs`, `threshold_policy_ref`, `assessed_at`, `status`, `evidence_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `reference_window` | yes | `text` | text | — |
| `current_window` | yes | `text` | text | — |
| `metric_refs` | yes | `refs<MetricDefinition|MetricResult>` | typed foreign reference to the listed contract | MetricDefinition, MetricResult |
| `threshold_policy_ref` | yes | `ref<ConfigurationManifest>` | typed foreign reference to the listed contract | ConfigurationManifest |
| `assessed_at` | yes | `utc_instant` | UTC instant | — |
| `status` | yes | `enum<DriftState>` | enumerated state/dimension; see the named enum | — |
| `evidence_refs` | yes | `refs<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |


## Validation

### ValidationEpoch

Schema: `qc2.validation.ValidationEpoch.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`, `epoch_key`, `regime`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `epoch_key`, `regime`, `mode`, `start_session`, `manifest_ref`, `champion_ref`, `reference_model_ref`, `activated_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `epoch_key` | yes | `slug` | lowercase identifier | — |
| `regime` | yes | `slug` | lowercase identifier | — |
| `mode` | yes | `enum<OperatingMode>` | enumerated state/dimension; see the named enum | — |
| `epoch_state` | yes | `enum<EpochState>` | enumerated state/dimension; see the named enum | — |
| `start_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `manifest_ref` | yes | `nullable_ref<EpochManifest>` | typed foreign reference to the listed contract | — |
| `champion_ref` | yes | `nullable_ref<ChampionPointer>` | typed foreign reference to the listed contract | — |
| `reference_model_ref` | yes | `nullable_ref<ModelManifest>` | typed foreign reference to the listed contract | — |
| `activated_at` | yes | `nullable_utc_instant` | UTC instant | — |

State field: `epoch_state`. Guard: Activation requires exact signed owner decision and every machine gate; closure is immutable.

| From | Allowed next states |
|---|---|
| `DRAFT` | `READY`, `HELD`, `ABORTED` |
| `READY` | `ACTIVE`, `HELD`, `ABORTED` |
| `ACTIVE` | `OUTCOME_MATURATION`, `HELD`, `ABORTED` |
| `OUTCOME_MATURATION` | `CLOSED_PASS`, `CLOSED_FAIL`, `INSUFFICIENT_EVIDENCE` |
| `HELD` | `READY`, `ABORTED` |

### EpochManifest

Schema: `qc2.validation.EpochManifest.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `epoch_key`, `regime`, `mode`, `calendar_ref`, `universe_ref`, `registry_refs`, `model_ref`, `reference_model_ref`, `strategy_ref`, `configuration_ref`, `effective_session`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `epoch_key` | yes | `slug` | lowercase identifier | — |
| `regime` | yes | `slug` | lowercase identifier | — |
| `mode` | yes | `enum<OperatingMode>` | enumerated state/dimension; see the named enum | — |
| `calendar_ref` | yes | `ref<CalendarManifest>` | typed foreign reference to the listed contract | CalendarManifest |
| `universe_ref` | yes | `ref<UniverseManifest>` | typed foreign reference to the listed contract | UniverseManifest |
| `registry_refs` | yes | `refs<FeatureRegistry|RunnerProtocolRegistry|LabelRegistry|ScoreManifest|BaselineManifest>` | typed foreign reference to the listed contract | FeatureRegistry, RunnerProtocolRegistry, LabelRegistry, ScoreManifest, BaselineManifest |
| `model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `reference_model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `strategy_ref` | yes | `ref<StrategyManifest>` | typed foreign reference to the listed contract | StrategyManifest |
| `configuration_ref` | yes | `ref<ConfigurationManifest>` | typed foreign reference to the listed contract | ConfigurationManifest |
| `effective_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |

### ScheduledAttempt

Schema: `qc2.validation.ScheduledAttempt.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_ref`, `session_id`, `schedule_created_at`, `expected_deadline`, `attempt_state`, `run_ref`, `missed_reason`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `schedule_created_at` | yes | `utc_instant` | UTC instant | — |
| `expected_deadline` | yes | `utc_instant` | UTC instant | — |
| `attempt_state` | yes | `enum<ScheduledAttemptState>` | enumerated state/dimension; see the named enum | — |
| `run_ref` | yes | `nullable_ref<PredictionRun>` | typed foreign reference to the listed contract | — |
| `missed_reason` | yes | `nullable_text` | text | — |

### ValidationSession

Schema: `qc2.validation.ValidationSession.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_ref`, `session_id`, `qualification_ref`, `metric_result_refs`, `integrity_status`, `sealed_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `qualification_ref` | yes | `nullable_ref<QualificationReceipt>` | typed foreign reference to the listed contract | — |
| `metric_result_refs` | yes | `refs<MetricResult>` | typed foreign reference to the listed contract | MetricResult |
| `integrity_status` | yes | `enum<IntegrityVerdict>` | enumerated state/dimension; see the named enum | — |
| `sealed_at` | yes | `utc_instant` | UTC instant | — |

### QualificationReceipt

Schema: `qc2.validation.QualificationReceipt.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `epoch_ref`, `session_id`, `prediction_seal_ref`, `prediction_integrity`, `denominator_status`, `on_time_seal`, `on_time_anchor`, `comparator_available`, `protocol_conformity`, `sealed_at`, `checkpoint_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `session_id` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `prediction_seal_ref` | yes | `ref<PredictionSeal>` | typed foreign reference to the listed contract | PredictionSeal |
| `prediction_integrity` | yes | `enum<IntegrityVerdict>` | enumerated state/dimension; see the named enum | — |
| `denominator_status` | yes | `enum<CoverageStatus>` | enumerated state/dimension; see the named enum | — |
| `on_time_seal` | yes | `boolean` | not applicable | — |
| `on_time_anchor` | yes | `boolean` | not applicable | — |
| `comparator_available` | yes | `boolean` | not applicable | — |
| `protocol_conformity` | yes | `boolean` | not applicable | — |
| `sealed_at` | yes | `utc_instant` | UTC instant | — |
| `checkpoint_ref` | yes | `ref<Checkpoint>` | typed foreign reference to the listed contract | Checkpoint |

### MetricDefinition

Schema: `qc2.validation.MetricDefinition.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`, `metric_key`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `metric_key`, `version`, `estimand`, `unit`, `direction`, `missingness_policy`, `tie_handling`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `metric_key` | yes | `slug` | lowercase identifier | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `estimand` | yes | `text` | text | — |
| `unit` | yes | `text` | text | — |
| `direction` | yes | `enum<MetricDirection>` | enumerated state/dimension; see the named enum | — |
| `missingness_policy` | yes | `enum<MissingnessPolicy>` | enumerated state/dimension; see the named enum | — |
| `tie_handling` | yes | `text` | text | — |

### MetricResult

Schema: `qc2.validation.MetricResult.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `definition_ref`, `epoch_ref`, `session_id`, `value`, `lower_bound`, `upper_bound`, `denominator`, `missing_count`, `computed_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `definition_ref` | yes | `ref<MetricDefinition>` | typed foreign reference to the listed contract | MetricDefinition |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `session_id` | yes | `nullable_session` | exchange session date (YYYY-MM-DD) | — |
| `value` | yes | `nullable_continuous_decimal` | exact decimal; semantic unit is declared in the owning field definition | — |
| `lower_bound` | yes | `nullable_continuous_decimal` | exact decimal; semantic unit is declared in the owning field definition | — |
| `upper_bound` | yes | `nullable_continuous_decimal` | exact decimal; semantic unit is declared in the owning field definition | — |
| `denominator` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `missing_count` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `computed_at` | yes | `utc_instant` | UTC instant | — |

### StatisticalAnalysisPlan

Schema: `qc2.validation.StatisticalAnalysisPlan.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `epoch_ref`, `primary_metric_ref`, `comparator_ref`, `interval_method`, `alpha`, `practical_minimum_effect`, `minimum_event_clusters`, `minimum_effective_blocks`, `resample_count`, `missingness_method`, `stopping_rule`, `frozen_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `primary_metric_ref` | yes | `ref<MetricDefinition>` | typed foreign reference to the listed contract | MetricDefinition |
| `comparator_ref` | yes | `ref<BaselineManifest>` | typed foreign reference to the listed contract | BaselineManifest |
| `interval_method` | yes | `slug` | lowercase identifier | — |
| `alpha` | yes | `probability` | probability, fraction in [0, 1] | — |
| `practical_minimum_effect` | yes | `continuous_decimal` | exact decimal; semantic unit is declared in the owning field definition | — |
| `minimum_event_clusters` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `minimum_effective_blocks` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `resample_count` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `missingness_method` | yes | `text` | text | — |
| `stopping_rule` | yes | `text` | text | — |
| `frozen_at` | yes | `utc_instant` | UTC instant | — |

### ValidationReport

Schema: `qc2.validation.ValidationReport.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `epoch_ref`, `verdict`, `scheduled_attempt_refs`, `qualification_refs`, `metric_refs`, `missingness_bounds`, `limitation_codes`, `report_hash`, `sealed_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `verdict` | yes | `enum<ValidationVerdict>` | enumerated state/dimension; see the named enum | — |
| `scheduled_attempt_refs` | yes | `refs<ScheduledAttempt>` | typed foreign reference to the listed contract | ScheduledAttempt |
| `qualification_refs` | yes | `refs<QualificationReceipt>` | typed foreign reference to the listed contract | QualificationReceipt |
| `metric_refs` | yes | `refs<MetricResult|MetricDefinition>` | typed foreign reference to the listed contract | MetricResult, MetricDefinition |
| `missingness_bounds` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `limitation_codes` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `report_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `sealed_at` | yes | `utc_instant` | UTC instant | — |

### ReportAmendment

Schema: `qc2.validation.ReportAmendment.v1`. Writer: `validation`. Readers: apexlab, evidence, ground_truth, model_registry, owner_api, prediction, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `report_ref`, `revision_number`, `reason`, `impact_analysis`, `correction_refs`, `amendment_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `report_ref` | yes | `ref<ValidationReport>` | typed foreign reference to the listed contract | ValidationReport |
| `revision_number` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `reason` | yes | `text` | text | — |
| `impact_analysis` | yes | `text` | text | — |
| `correction_refs` | yes | `refs<OutcomeRevision|MarketSnapshotRevision>` | typed foreign reference to the listed contract | OutcomeRevision, MarketSnapshotRevision |
| `amendment_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |


## Execution

### StrategyManifest

Schema: `qc2.execution.StrategyManifest.v1`. Writer: `strategy`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `strategy_key`, `version`, `selection_k`, `rank_rule`, `entry_window`, `allocation_order`, `price_cap_rule`, `quantity_rounding`, `stop_rule`, `target_rule`, `trailing_rule`, `maximum_holding_sessions`, `reentry_policy`, `reservation_policy`, `cancellation_policy`, `gap_no_fill_policy`, `competing_action_rule`, `configuration_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `strategy_key` | yes | `slug` | lowercase identifier | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `selection_k` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `rank_rule` | yes | `text` | text | — |
| `entry_window` | yes | `text` | text | — |
| `allocation_order` | yes | `text` | text | — |
| `price_cap_rule` | yes | `text` | text | — |
| `quantity_rounding` | yes | `enum<QuantityRounding>` | enumerated state/dimension; see the named enum | — |
| `stop_rule` | yes | `nullable_text` | text | — |
| `target_rule` | yes | `nullable_text` | text | — |
| `trailing_rule` | yes | `nullable_text` | text | — |
| `maximum_holding_sessions` | yes | `positive_int` | exchange sessions | — |
| `reentry_policy` | yes | `text` | text | — |
| `reservation_policy` | yes | `text` | text | — |
| `cancellation_policy` | yes | `text` | text | — |
| `gap_no_fill_policy` | yes | `text` | text | — |
| `competing_action_rule` | yes | `text` | text | — |
| `configuration_ref` | yes | `ref<ConfigurationManifest>` | typed foreign reference to the listed contract | ConfigurationManifest |

### CapitalPolicy

Schema: `qc2.execution.CapitalPolicy.v1`. Writer: `configuration`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `paper_starting_capital`, `currency`, `maximum_position_cost`, `maximum_position_fraction`, `maximum_gross_exposure`, `cash_reserve`, `maximum_concurrent_positions`, `daily_loss_limit`, `drawdown_response`, `participation_limit`, `external_activity_policy`, `owner_approval_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `paper_starting_capital` | yes | `decimal` | currency amount in the adjacent currency field | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `maximum_position_cost` | yes | `decimal` | currency amount in the adjacent currency field | — |
| `maximum_position_fraction` | yes | `probability` | probability, fraction in [0, 1] | — |
| `maximum_gross_exposure` | yes | `decimal` | currency amount in the adjacent currency field | — |
| `cash_reserve` | yes | `decimal` | currency amount in the adjacent currency field | — |
| `maximum_concurrent_positions` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `daily_loss_limit` | yes | `decimal` | exact decimal; semantic unit is declared in the owning field definition | — |
| `drawdown_response` | yes | `text` | text | — |
| `participation_limit` | yes | `probability` | probability, fraction in [0, 1] | — |
| `external_activity_policy` | yes | `text` | text | — |
| `owner_approval_ref` | yes | `ref<OwnerCommandReceipt>` | typed foreign reference to the listed contract | OwnerCommandReceipt |

### PaperOrderIntent

Schema: `qc2.execution.PaperOrderIntent.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`, `idempotency_key`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `episode_ref`, `paper_account_fingerprint`, `action_kind`, `source_ref`, `instrument_ref`, `symbol_assignment_ref`, `side`, `quantity_whole_shares`, `limit_price`, `stop_price`, `order_type`, `time_in_force`, `session_restriction`, `strategy_ref`, `capital_policy_ref`, `predicted_session`, `target_execution_session`, `target_window`, `expires_at`, `reason_code`, `safety_assessment_refs`, `reservation_ref`, `idempotency_key`, `account_mode`, `extended_hours`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `episode_ref` | yes | `ref<ExecutionEpisode>` | typed foreign reference to the listed contract | ExecutionEpisode |
| `paper_account_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `action_kind` | yes | `enum<PaperAction>` | enumerated state/dimension; see the named enum | — |
| `source_ref` | yes | `ref<Prediction|Position|PaperOrderIntent>` | typed foreign reference to the listed contract | Prediction, Position, PaperOrderIntent |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `symbol_assignment_ref` | yes | `ref<SymbolAssignment>` | typed foreign reference to the listed contract | SymbolAssignment |
| `side` | yes | `enum<OrderSide>` | enumerated state/dimension; see the named enum | — |
| `quantity_whole_shares` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `limit_price` | yes | `nullable_decimal` | currency specified by the adjacent currency field per share | — |
| `stop_price` | yes | `nullable_decimal` | currency specified by the adjacent currency field per share | — |
| `order_type` | yes | `enum<OrderType>` | enumerated state/dimension; see the named enum | — |
| `time_in_force` | yes | `enum<TimeInForce>` | enumerated state/dimension; see the named enum | — |
| `session_restriction` | yes | `enum<SessionRestriction>` | enumerated state/dimension; see the named enum | — |
| `strategy_ref` | yes | `ref<StrategyManifest>` | typed foreign reference to the listed contract | StrategyManifest |
| `capital_policy_ref` | yes | `ref<CapitalPolicy>` | typed foreign reference to the listed contract | CapitalPolicy |
| `predicted_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `target_execution_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `target_window` | yes | `text` | text | — |
| `expires_at` | yes | `utc_instant` | UTC instant | — |
| `reason_code` | yes | `slug` | lowercase identifier | — |
| `safety_assessment_refs` | yes | `refs<ReadinessAssessment>` | typed foreign reference to the listed contract | ReadinessAssessment |
| `reservation_ref` | yes | `nullable_ref<Reservation>` | typed foreign reference to the listed contract | — |
| `idempotency_key` | yes | `slug` | lowercase identifier | — |
| `account_mode` | yes | `enum<AccountMode>` | enumerated state/dimension; see the named enum | — |
| `extended_hours` | yes | `false_only` | not applicable | — |
| `intent_state` | yes | `enum<IntentState>` | enumerated state/dimension; see the named enum | — |

State field: `intent_state`. Guard: Intent terms are immutable; any changed quantity or price requires a new intent revision and stable idempotency binding.

| From | Allowed next states |
|---|---|
| `CREATED` | `VERIFIED`, `REJECTED` |
| `VERIFIED` | `RESERVED`, `REJECTED`, `EXPIRED` |
| `RESERVED` | `QUEUED_FOR_SUBMISSION`, `CANCELLED`, `EXPIRED` |
| `QUEUED_FOR_SUBMISSION` | `SUBMISSION_STARTED`, `CANCELLED`, `EXPIRED` |
| `SUBMISSION_STARTED` | `ACKNOWLEDGED`, `SUBMISSION_UNKNOWN`, `REJECTED` |
| `ACKNOWLEDGED` | `PARTIALLY_FILLED`, `FILLED`, `CANCEL_REQUESTED`, `EXPIRED`, `REPLACED` |
| `SUBMISSION_UNKNOWN` | `ACKNOWLEDGED`, `REJECTED`, `CANCEL_REQUESTED` |
| `PARTIALLY_FILLED` | `FILLED`, `CANCEL_REQUESTED`, `CANCELLED`, `EXPIRED`, `REPLACED` |
| `CANCEL_REQUESTED` | `CANCELLED`, `PARTIALLY_FILLED`, `FILLED`, `SUBMISSION_UNKNOWN` |

Invariants:
- one source_ref has exactly one target_schema_name from the action-specific allowlist
- OPEN_LONG references Prediction; reduction/close references Position; cancel/replace references PaperOrderIntent
- F0 account mode is PAPER and extended_hours is false

### IntentDecision

Schema: `qc2.execution.IntentDecision.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `intent_ref`, `decision`, `reason_codes`, `readiness_ref`, `policy_hash`, `decided_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `intent_ref` | yes | `ref<PaperOrderIntent>` | typed foreign reference to the listed contract | PaperOrderIntent |
| `decision` | yes | `enum<IntentDecisionState>` | enumerated state/dimension; see the named enum | — |
| `reason_codes` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `readiness_ref` | yes | `ref<ReadinessAssessment>` | typed foreign reference to the listed contract | ReadinessAssessment |
| `policy_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `decided_at` | yes | `utc_instant` | UTC instant | — |

### SubmissionAttempt

Schema: `qc2.execution.SubmissionAttempt.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `intent_ref`, `client_order_key`, `normalized_request_hash`, `attempt_number`, `started_at`, `outcome`, `broker_order_ref`, `evidence_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `intent_ref` | yes | `ref<PaperOrderIntent>` | typed foreign reference to the listed contract | PaperOrderIntent |
| `client_order_key` | yes | `slug` | lowercase identifier | — |
| `normalized_request_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `attempt_number` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `started_at` | yes | `utc_instant` | UTC instant | — |
| `outcome` | yes | `enum<SubmissionOutcome>` | enumerated state/dimension; see the named enum | — |
| `broker_order_ref` | yes | `nullable_ref<BrokerOrder>` | typed foreign reference to the listed contract | — |
| `evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |

### BrokerOrder

Schema: `qc2.execution.BrokerOrder.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`, `paper_account_fingerprint`, `client_order_key`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `intent_ref`, `paper_account_fingerprint`, `client_order_key`, `broker_order_id`, `request_hash`, `submitted_at`, `updated_at`, `filled_quantity`, `remaining_quantity`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `intent_ref` | yes | `ref<PaperOrderIntent>` | typed foreign reference to the listed contract | PaperOrderIntent |
| `paper_account_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `client_order_key` | yes | `slug` | lowercase identifier | — |
| `broker_order_id` | yes | `text` | text | — |
| `request_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `order_state` | yes | `enum<BrokerOrderState>` | enumerated state/dimension; see the named enum | — |
| `submitted_at` | yes | `utc_instant` | UTC instant | — |
| `updated_at` | yes | `utc_instant` | UTC instant | — |
| `filled_quantity` | yes | `decimal` | shares | — |
| `remaining_quantity` | yes | `decimal` | shares | — |

State field: `order_state`. Guard: Terminal broker state requires definitive provider facts/reconciliation, never a timeout inference.

| From | Allowed next states |
|---|---|
| `SUBMISSION_UNKNOWN` | `ACKNOWLEDGED`, `REJECTED`, `PARTIALLY_FILLED`, `FILLED`, `CANCEL_REQUESTED` |
| `ACKNOWLEDGED` | `PARTIALLY_FILLED`, `FILLED`, `CANCEL_REQUESTED`, `CANCELLED`, `EXPIRED`, `REPLACED` |
| `PARTIALLY_FILLED` | `FILLED`, `CANCEL_REQUESTED`, `CANCELLED`, `EXPIRED`, `REPLACED` |
| `CANCEL_REQUESTED` | `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `SUBMISSION_UNKNOWN` |

### BrokerOrderEvent

Schema: `qc2.execution.BrokerOrderEvent.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `broker_order_ref`, `provider_event_id`, `event_type`, `event_sequence`, `event_at`, `received_at`, `event_payload_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `broker_order_ref` | yes | `ref<BrokerOrder>` | typed foreign reference to the listed contract | BrokerOrder |
| `provider_event_id` | yes | `text` | text | — |
| `event_type` | yes | `enum<BrokerOrderEventType>` | enumerated state/dimension; see the named enum | — |
| `event_sequence` | yes | `nonnegative_int` | ordinal/count (unit is named by the field) | — |
| `event_at` | yes | `utc_instant` | UTC instant | — |
| `received_at` | yes | `utc_instant` | UTC instant | — |
| `event_payload_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### Fill

Schema: `qc2.execution.Fill.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`, `broker_order_ref`, `provider_fill_id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `broker_order_ref`, `provider_fill_id`, `instrument_ref`, `side`, `quantity`, `price`, `currency`, `filled_at`, `received_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `broker_order_ref` | yes | `ref<BrokerOrder>` | typed foreign reference to the listed contract | BrokerOrder |
| `provider_fill_id` | yes | `text` | text | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `side` | yes | `enum<OrderSide>` | enumerated state/dimension; see the named enum | — |
| `quantity` | yes | `positive_decimal` | shares | — |
| `price` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `filled_at` | yes | `utc_instant` | UTC instant | — |
| `received_at` | yes | `utc_instant` | UTC instant | — |

### FillCorrection

Schema: `qc2.execution.FillCorrection.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `original_fill_ref`, `correction_kind`, `quantity_delta`, `price_delta`, `reason_code`, `source_event_ref`, `corrected_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `original_fill_ref` | yes | `ref<Fill>` | typed foreign reference to the listed contract | Fill |
| `correction_kind` | yes | `enum<FillCorrectionKind>` | enumerated state/dimension; see the named enum | — |
| `quantity_delta` | yes | `decimal` | shares | — |
| `price_delta` | yes | `decimal` | currency specified by the adjacent currency field per share | — |
| `reason_code` | yes | `slug` | lowercase identifier | — |
| `source_event_ref` | yes | `ref<BrokerOrderEvent>` | typed foreign reference to the listed contract | BrokerOrderEvent |
| `corrected_at` | yes | `utc_instant` | UTC instant | — |

### Position

Schema: `qc2.execution.Position.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `episode_ref`, `instrument_ref`, `quantity`, `average_cost`, `currency`, `as_of`, `source_fill_refs`, `corporate_action_refs`, `reconciliation_status`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `episode_ref` | yes | `ref<ExecutionEpisode>` | typed foreign reference to the listed contract | ExecutionEpisode |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `quantity` | yes | `positive_decimal` | shares | — |
| `average_cost` | yes | `positive_decimal` | currency specified by the adjacent currency field per share | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `as_of` | yes | `utc_instant` | UTC instant | — |
| `source_fill_refs` | yes | `refs<Fill>` | typed foreign reference to the listed contract | Fill |
| `corporate_action_refs` | yes | `refs<CorporateActionRecord>` | typed foreign reference to the listed contract | CorporateActionRecord |
| `reconciliation_status` | yes | `enum<ReconciliationStatus>` | enumerated state/dimension; see the named enum | — |

### CashLedgerEntry

Schema: `qc2.execution.CashLedgerEntry.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `episode_ref`, `entry_kind`, `amount`, `currency`, `effective_at`, `source_ref`, `balance_after`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `episode_ref` | yes | `ref<ExecutionEpisode>` | typed foreign reference to the listed contract | ExecutionEpisode |
| `entry_kind` | yes | `enum<CashEntryKind>` | enumerated state/dimension; see the named enum | — |
| `amount` | yes | `decimal` | currency amount in the adjacent currency field | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `effective_at` | yes | `utc_instant` | UTC instant | — |
| `source_ref` | yes | `ref<PaperOrderIntent>` | typed foreign reference to the listed contract | PaperOrderIntent |
| `balance_after` | yes | `decimal` | exact decimal; semantic unit is declared in the owning field definition | — |

### Reservation

Schema: `qc2.execution.Reservation.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `episode_ref`, `intent_ref`, `reservation_kind`, `instrument_ref`, `reserved_quantity`, `reserved_cash`, `currency`, `state`, `released_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `episode_ref` | yes | `ref<ExecutionEpisode>` | typed foreign reference to the listed contract | ExecutionEpisode |
| `intent_ref` | yes | `ref<PaperOrderIntent>` | typed foreign reference to the listed contract | PaperOrderIntent |
| `reservation_kind` | yes | `enum<ReservationKind>` | enumerated state/dimension; see the named enum | — |
| `instrument_ref` | yes | `ref<Instrument>` | typed foreign reference to the listed contract | Instrument |
| `reserved_quantity` | yes | `nonnegative_decimal` | shares | — |
| `reserved_cash` | yes | `nonnegative_decimal` | currency amount in the adjacent currency field | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `state` | yes | `enum<ReservationState>` | enumerated state/dimension; see the named enum | — |
| `released_at` | yes | `nullable_utc_instant` | UTC instant | — |

### ReconciliationReport

Schema: `qc2.execution.ReconciliationReport.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `episode_ref`, `paper_account_fingerprint`, `reconciled_at`, `broker_order_refs`, `position_refs`, `discrepancies`, `status`, `evidence_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `episode_ref` | yes | `ref<ExecutionEpisode>` | typed foreign reference to the listed contract | ExecutionEpisode |
| `paper_account_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `reconciled_at` | yes | `utc_instant` | UTC instant | — |
| `broker_order_refs` | yes | `refs<BrokerOrder>` | typed foreign reference to the listed contract | BrokerOrder |
| `position_refs` | yes | `refs<Position>` | typed foreign reference to the listed contract | Position |
| `discrepancies` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `status` | yes | `enum<ReconciliationStatus>` | enumerated state/dimension; see the named enum | — |
| `evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |

### ExecutionEpisode

Schema: `qc2.execution.ExecutionEpisode.v1`. Writer: `execution`. Readers: alert, configuration, evidence, execution, instrument_universe, market_data, owner_api, prediction, safety, strategy.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `paper_account_fingerprint`, `account_mode`, `opened_at`, `opening_cash`, `currency`, `opening_position_refs`, `opening_order_refs`, `strategy_ref`, `capital_policy_ref`, `sealed_at`, `episode_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `paper_account_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `account_mode` | yes | `enum<AccountMode>` | enumerated state/dimension; see the named enum | — |
| `opened_at` | yes | `utc_instant` | UTC instant | — |
| `opening_cash` | yes | `decimal` | currency amount in the adjacent currency field | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `opening_position_refs` | yes | `refs<Position>` | typed foreign reference to the listed contract | Position |
| `opening_order_refs` | yes | `refs<BrokerOrder>` | typed foreign reference to the listed contract | BrokerOrder |
| `strategy_ref` | yes | `ref<StrategyManifest>` | typed foreign reference to the listed contract | StrategyManifest |
| `capital_policy_ref` | yes | `ref<CapitalPolicy>` | typed foreign reference to the listed contract | CapitalPolicy |
| `sealed_at` | yes | `utc_instant` | UTC instant | — |
| `episode_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

Invariants:
- account_mode is PAPER; a sealed episode is immutable


## Governance and owner

### PromotionPolicy

Schema: `qc2.governance_owner.PromotionPolicy.v1`. Writer: `promotion`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `policy_key`, `version`, `prospective_sessions`, `minimum_events`, `uncertainty_requirements`, `calibration_bounds`, `coverage_limits`, `stability_limits`, `regression_gates`, `maximum_attempts`, `cooldown_sessions`, `permitted_artifact_types`, `compatibility_envelope`, `epoch_modes`, `frozen_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `policy_key` | yes | `slug` | lowercase identifier | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `prospective_sessions` | yes | `positive_int` | exchange sessions | — |
| `minimum_events` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `uncertainty_requirements` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `calibration_bounds` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `coverage_limits` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `stability_limits` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `regression_gates` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `maximum_attempts` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `cooldown_sessions` | yes | `nonnegative_int` | exchange sessions | — |
| `permitted_artifact_types` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `compatibility_envelope` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `epoch_modes` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `frozen_at` | yes | `utc_instant` | UTC instant | — |

### PromotionBundleManifest

Schema: `qc2.governance_owner.PromotionBundleManifest.v1`. Writer: `promotion`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `candidate_model_ref`, `prior_champion_ref`, `epoch_ref`, `mode`, `registry_refs`, `dataset_ref`, `split_ref`, `holdout_receipt_refs`, `replay_report_ref`, `evaluation_refs`, `shadow_seal_refs`, `policy_ref`, `gate_results`, `environment_fingerprint`, `expires_at`, `transition_intent`, `inventory_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `candidate_model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `prior_champion_ref` | yes | `nullable_ref<ChampionPointer>` | typed foreign reference to the listed contract | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `mode` | yes | `enum<OperatingMode>` | enumerated state/dimension; see the named enum | — |
| `registry_refs` | yes | `refs<FeatureRegistry|RunnerProtocolRegistry|LabelRegistry|ScoreManifest|BaselineManifest>` | typed foreign reference to the listed contract | FeatureRegistry, RunnerProtocolRegistry, LabelRegistry, ScoreManifest, BaselineManifest |
| `dataset_ref` | yes | `ref<DatasetManifest>` | typed foreign reference to the listed contract | DatasetManifest |
| `split_ref` | yes | `ref<SplitManifest>` | typed foreign reference to the listed contract | SplitManifest |
| `holdout_receipt_refs` | yes | `refs<HoldoutAccessReceipt>` | typed foreign reference to the listed contract | HoldoutAccessReceipt |
| `replay_report_ref` | yes | `ref<ReplayReceipt>` | typed foreign reference to the listed contract | ReplayReceipt |
| `evaluation_refs` | yes | `refs<CandidateEvaluation|ChallengerEvaluation|ValidationReport>` | typed foreign reference to the listed contract | CandidateEvaluation, ChallengerEvaluation, ValidationReport |
| `shadow_seal_refs` | yes | `refs<PredictionSeal>` | typed foreign reference to the listed contract | PredictionSeal |
| `policy_ref` | yes | `ref<PromotionPolicy>` | typed foreign reference to the listed contract | PromotionPolicy |
| `gate_results` | yes | `gate_result_list` | ordered array; item unit/type is stated by the field | — |
| `environment_fingerprint` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `expires_at` | yes | `utc_instant` | UTC instant | — |
| `transition_intent` | yes | `slug` | lowercase identifier | — |
| `inventory_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### PromotionRequest

Schema: `qc2.governance_owner.PromotionRequest.v1`. Writer: `promotion`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `bundle_ref`, `candidate_model_ref`, `expected_champion_ref`, `epoch_ref`, `requested_at`, `expires_at`, `request_state`, `request_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `bundle_ref` | yes | `ref<PromotionBundleManifest>` | typed foreign reference to the listed contract | PromotionBundleManifest |
| `candidate_model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `expected_champion_ref` | yes | `nullable_ref<ChampionPointer>` | typed foreign reference to the listed contract | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `requested_at` | yes | `utc_instant` | UTC instant | — |
| `expires_at` | yes | `utc_instant` | UTC instant | — |
| `request_state` | yes | `enum<PromotionRequestState>` | enumerated state/dimension; see the named enum | — |
| `request_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### PromotionChallenge

Schema: `qc2.governance_owner.PromotionChallenge.v1`. Writer: `promotion`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `request_ref`, `bundle_hash`, `candidate_hash`, `expected_champion_hash`, `expected_generation`, `epoch_ref`, `registry_refs`, `policy_ref`, `nonce`, `issued_at`, `expires_at`, `device_ref`, `key_id`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `request_ref` | yes | `ref<PromotionRequest>` | typed foreign reference to the listed contract | PromotionRequest |
| `bundle_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `candidate_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `expected_champion_hash` | yes | `nullable_sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `expected_generation` | yes | `nonnegative_int` | ordinal/count (unit is named by the field) | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `registry_refs` | yes | `refs<FeatureRegistry|RunnerProtocolRegistry|LabelRegistry|ScoreManifest|BaselineManifest>` | typed foreign reference to the listed contract | FeatureRegistry, RunnerProtocolRegistry, LabelRegistry, ScoreManifest, BaselineManifest |
| `policy_ref` | yes | `ref<PromotionPolicy>` | typed foreign reference to the listed contract | PromotionPolicy |
| `nonce` | yes | `slug` | lowercase identifier | — |
| `issued_at` | yes | `utc_instant` | UTC instant | — |
| `expires_at` | yes | `utc_instant` | UTC instant | — |
| `device_ref` | yes | `ref<OwnerDevice>` | typed foreign reference to the listed contract | OwnerDevice |
| `key_id` | yes | `slug` | lowercase identifier | — |

### PromotionDecision

Schema: `qc2.governance_owner.PromotionDecision.v1`. Writer: `promotion`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `challenge_ref`, `decision`, `signed_by_device_ref`, `key_id`, `signature`, `signed_at`, `request_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `challenge_ref` | yes | `ref<PromotionChallenge>` | typed foreign reference to the listed contract | PromotionChallenge |
| `decision` | yes | `enum<OwnerDecision>` | enumerated state/dimension; see the named enum | — |
| `signed_by_device_ref` | yes | `ref<OwnerDevice>` | typed foreign reference to the listed contract | OwnerDevice |
| `key_id` | yes | `slug` | lowercase identifier | — |
| `signature` | yes | `base64url` | unpadded base64url-encoded key or signature bytes | — |
| `signed_at` | yes | `utc_instant` | UTC instant | — |
| `request_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### PromotionReceipt

Schema: `qc2.governance_owner.PromotionReceipt.v1`. Writer: `promotion`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `request_ref`, `decision_ref`, `transition_state`, `prior_generation`, `new_generation`, `committed_at`, `evidence_ref`, `pointer_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `request_ref` | yes | `ref<PromotionRequest>` | typed foreign reference to the listed contract | PromotionRequest |
| `decision_ref` | yes | `ref<PromotionDecision>` | typed foreign reference to the listed contract | PromotionDecision |
| `transition_state` | yes | `enum<PromotionReceiptState>` | enumerated state/dimension; see the named enum | — |
| `prior_generation` | yes | `nonnegative_int` | ordinal/count (unit is named by the field) | — |
| `new_generation` | yes | `positive_int` | ordinal/count (unit is named by the field) | — |
| `committed_at` | yes | `utc_instant` | UTC instant | — |
| `evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |
| `pointer_hash` | yes | `nullable_sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### ChampionPointer

Schema: `qc2.governance_owner.ChampionPointer.v1`. Writer: `promotion`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `epoch_ref`, `role`, `model_ref`, `generation`, `transitioned_at`, `transition_receipt_ref`, `pointer_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `role` | yes | `enum<ChampionRole>` | enumerated state/dimension; see the named enum | — |
| `model_ref` | yes | `ref<ModelManifest>` | typed foreign reference to the listed contract | ModelManifest |
| `generation` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `transitioned_at` | yes | `utc_instant` | UTC instant | — |
| `transition_receipt_ref` | yes | `ref<PromotionReceipt>` | typed foreign reference to the listed contract | PromotionReceipt |
| `pointer_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### EpochActivationChallenge

Schema: `qc2.governance_owner.EpochActivationChallenge.v1`. Writer: `validation`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `epoch_manifest_ref`, `prospective_start_session`, `account_identity_hash`, `strategy_hash`, `nonce`, `issued_at`, `expires_at`, `device_ref`, `key_id`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `epoch_manifest_ref` | yes | `ref<EpochManifest>` | typed foreign reference to the listed contract | EpochManifest |
| `prospective_start_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `account_identity_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `strategy_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `nonce` | yes | `slug` | lowercase identifier | — |
| `issued_at` | yes | `utc_instant` | UTC instant | — |
| `expires_at` | yes | `utc_instant` | UTC instant | — |
| `device_ref` | yes | `ref<OwnerDevice>` | typed foreign reference to the listed contract | OwnerDevice |
| `key_id` | yes | `slug` | lowercase identifier | — |

### EpochActivationDecision

Schema: `qc2.governance_owner.EpochActivationDecision.v1`. Writer: `validation`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `challenge_ref`, `epoch_manifest_hash`, `decision`, `device_ref`, `key_id`, `signature`, `signed_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `challenge_ref` | yes | `ref<EpochActivationChallenge>` | typed foreign reference to the listed contract | EpochActivationChallenge |
| `epoch_manifest_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `decision` | yes | `enum<EpochActivationChoice>` | enumerated state/dimension; see the named enum | — |
| `device_ref` | yes | `ref<OwnerDevice>` | typed foreign reference to the listed contract | OwnerDevice |
| `key_id` | yes | `slug` | lowercase identifier | — |
| `signature` | yes | `base64url` | unpadded base64url-encoded key or signature bytes | — |
| `signed_at` | yes | `utc_instant` | UTC instant | — |

### EpochActivationReceipt

Schema: `qc2.governance_owner.EpochActivationReceipt.v1`. Writer: `validation`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `decision_ref`, `epoch_ref`, `epoch_manifest_hash`, `start_session`, `activation_state`, `gate_results`, `activated_at`, `evidence_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `decision_ref` | yes | `ref<EpochActivationDecision>` | typed foreign reference to the listed contract | EpochActivationDecision |
| `epoch_ref` | yes | `ref<ValidationEpoch>` | typed foreign reference to the listed contract | ValidationEpoch |
| `epoch_manifest_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `start_session` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `activation_state` | yes | `enum<ActivationState>` | enumerated state/dimension; see the named enum | — |
| `gate_results` | yes | `gate_result_list` | ordered array; item unit/type is stated by the field | — |
| `activated_at` | yes | `utc_instant` | UTC instant | — |
| `evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |

### OwnerDevice

Schema: `qc2.governance_owner.OwnerDevice.v1`. Writer: `identity`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `owner_key_id`, `public_key`, `signing_algorithm`, `security_level`, `enrollment_proof_hash`, `owner_binding`, `app_version`, `enrolled_at`, `revoked_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `owner_key_id` | yes | `slug` | lowercase identifier | — |
| `public_key` | yes | `base64url` | unpadded base64url-encoded key or signature bytes | — |
| `signing_algorithm` | yes | `enum<SigningAlgorithm>` | enumerated state/dimension; see the named enum | — |
| `security_level` | yes | `enum<DeviceSecurityLevel>` | enumerated state/dimension; see the named enum | — |
| `enrollment_proof_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `owner_binding` | yes | `slug` | lowercase identifier | — |
| `app_version` | yes | `text` | text | — |
| `revocation_state` | yes | `enum<DeviceRevocationState>` | enumerated state/dimension; see the named enum | — |
| `enrolled_at` | yes | `utc_instant` | UTC instant | — |
| `revoked_at` | yes | `nullable_utc_instant` | UTC instant | — |

State field: `revocation_state`. Guard: Revocation is forward-only and must be rechecked at privileged-command commit.

| From | Allowed next states |
|---|---|
| `ENROLLED` | `REVOKED` |

### OwnerSession

Schema: `qc2.governance_owner.OwnerSession.v1`. Writer: `identity`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `device_ref`, `session_id`, `issued_at`, `expires_at`, `revoked_at`, `scope_refs`, `refresh_generation`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `device_ref` | yes | `ref<OwnerDevice>` | typed foreign reference to the listed contract | OwnerDevice |
| `session_id` | yes | `slug` | lowercase identifier | — |
| `issued_at` | yes | `utc_instant` | UTC instant | — |
| `expires_at` | yes | `utc_instant` | UTC instant | — |
| `revoked_at` | yes | `nullable_utc_instant` | UTC instant | — |
| `scope_refs` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `refresh_generation` | yes | `positive_int` | ordinal/count (unit is named by the field) | — |

### EnrollmentChallenge

Schema: `qc2.governance_owner.EnrollmentChallenge.v1`. Writer: `identity`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `owner_binding`, `bootstrap_verifier_hash`, `nonce`, `issued_at`, `expires_at`, `single_use`, `consumed_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `owner_binding` | yes | `slug` | lowercase identifier | — |
| `bootstrap_verifier_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `nonce` | yes | `slug` | lowercase identifier | — |
| `issued_at` | yes | `utc_instant` | UTC instant | — |
| `expires_at` | yes | `utc_instant` | UTC instant | — |
| `single_use` | yes | `boolean` | not applicable | — |
| `consumed_at` | yes | `nullable_utc_instant` | UTC instant | — |

### RecoveryEvent

Schema: `qc2.governance_owner.RecoveryEvent.v1`. Writer: `identity`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `event_kind`, `prior_device_refs`, `replacement_device_ref`, `effective_at`, `promotion_hold`, `entry_hold`, `reconciliation_required`, `evidence_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `event_kind` | yes | `enum<RecoveryEventKind>` | enumerated state/dimension; see the named enum | — |
| `prior_device_refs` | yes | `refs<OwnerDevice>` | typed foreign reference to the listed contract | OwnerDevice |
| `replacement_device_ref` | yes | `nullable_ref<OwnerDevice>` | typed foreign reference to the listed contract | — |
| `effective_at` | yes | `utc_instant` | UTC instant | — |
| `promotion_hold` | yes | `boolean` | not applicable | — |
| `entry_hold` | yes | `boolean` | not applicable | — |
| `reconciliation_required` | yes | `boolean` | not applicable | — |
| `evidence_ref` | yes | `ref<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |

### OwnerCommand

Schema: `qc2.governance_owner.OwnerCommand.v1`. Writer: `owner_api`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`, `command_id`, `idempotency_key`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `command_id`, `command_type`, `idempotency_key`, `request_body_hash`, `issued_at`, `device_ref`, `signature`, `scope`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `command_id` | yes | `slug` | lowercase identifier | — |
| `command_type` | yes | `enum<OwnerCommandType>` | enumerated state/dimension; see the named enum | — |
| `idempotency_key` | yes | `slug` | lowercase identifier | — |
| `request_body_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `issued_at` | yes | `utc_instant` | UTC instant | — |
| `device_ref` | yes | `ref<OwnerDevice>` | typed foreign reference to the listed contract | OwnerDevice |
| `signature` | yes | `base64url` | unpadded base64url-encoded key or signature bytes | — |
| `scope` | yes | `enum<OwnerCommandScope>` | enumerated state/dimension; see the named enum | — |

### OwnerCommandReceipt

Schema: `qc2.governance_owner.OwnerCommandReceipt.v1`. Writer: `owner_api`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `command_ref`, `state`, `resulting_evidence_ref`, `source_sequence`, `projection_lag_ms`, `received_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `command_ref` | yes | `ref<OwnerCommand>` | typed foreign reference to the listed contract | OwnerCommand |
| `state` | yes | `enum<OwnerCommandReceiptState>` | enumerated state/dimension; see the named enum | — |
| `resulting_evidence_ref` | yes | `nullable_ref<EvidenceEvent>` | typed foreign reference to the listed contract | — |
| `source_sequence` | yes | `nonnegative_int` | ordinal/count (unit is named by the field) | — |
| `projection_lag_ms` | yes | `nonnegative_int` | milliseconds | — |
| `received_at` | yes | `utc_instant` | UTC instant | — |

### Alert

Schema: `qc2.governance_owner.Alert.v1`. Writer: `alert`. Readers: alert, evidence, execution, identity, model_registry, owner_api, promotion, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `alert_type`, `severity`, `trigger_rule`, `dedupe_key`, `escalation_policy`, `action_owner`, `auto_resolution_condition`, `readiness_effect`, `acknowledged_at`, `resolved_at`, `evidence_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `alert_type` | yes | `slug` | lowercase identifier | — |
| `severity` | yes | `enum<AlertSeverity>` | enumerated state/dimension; see the named enum | — |
| `trigger_rule` | yes | `slug` | lowercase identifier | — |
| `dedupe_key` | yes | `slug` | lowercase identifier | — |
| `escalation_policy` | yes | `slug` | lowercase identifier | — |
| `action_owner` | yes | `slug` | lowercase identifier | — |
| `auto_resolution_condition` | yes | `text` | text | — |
| `readiness_effect` | yes | `boolean` | not applicable | — |
| `acknowledged_at` | yes | `nullable_utc_instant` | UTC instant | — |
| `resolved_at` | yes | `nullable_utc_instant` | UTC instant | — |
| `evidence_refs` | yes | `refs<EvidenceEvent>` | typed foreign reference to the listed contract | EvidenceEvent |


## Integrity and build

### EvidenceEvent

Schema: `qc2.integrity_build.EvidenceEvent.v1`. Writer: `evidence`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`, `installation_id`, `stream_id`, `sequence`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `installation_id`, `stream_id`, `sequence`, `event_type`, `actor_identity`, `authorized_command_ref`, `correlation_id`, `payload_hash`, `dependency_refs`, `previous_event_hash`, `event_hash`, `wall_clock_at`, `monotonic_generation`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `installation_id` | yes | `slug` | lowercase identifier | — |
| `stream_id` | yes | `slug` | lowercase identifier | — |
| `sequence` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `event_type` | yes | `slug` | lowercase identifier | — |
| `actor_identity` | yes | `slug` | lowercase identifier | — |
| `authorized_command_ref` | yes | `nullable_ref<OwnerCommand>` | typed foreign reference to the listed contract | — |
| `correlation_id` | yes | `slug` | lowercase identifier | — |
| `payload_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `dependency_refs` | yes | `refs<ArtifactManifest|Checkpoint|AnchorReceipt>` | typed foreign reference to the listed contract | ArtifactManifest, Checkpoint, AnchorReceipt |
| `previous_event_hash` | yes | `nullable_sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `event_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `wall_clock_at` | yes | `utc_instant` | UTC instant | — |
| `monotonic_generation` | yes | `nonnegative_int` | ordinal/count (unit is named by the field) | — |

### Checkpoint

Schema: `qc2.integrity_build.Checkpoint.v1`. Writer: `evidence`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `stream_id`, `head_sequence`, `head_hash`, `event_count`, `artifact_root_hash`, `checkpoint_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `stream_id` | yes | `slug` | lowercase identifier | — |
| `head_sequence` | yes | `nonnegative_int` | ordinal/count (unit is named by the field) | — |
| `head_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `event_count` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `artifact_root_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `checkpoint_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### AnchorReceipt

Schema: `qc2.integrity_build.AnchorReceipt.v1`. Writer: `evidence`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `checkpoint_ref`, `anchor_provider`, `external_receipt_id`, `accepted_at`, `observed_at`, `verification_key_id`, `signature`, `proof_level`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `checkpoint_ref` | yes | `ref<Checkpoint>` | typed foreign reference to the listed contract | Checkpoint |
| `anchor_provider` | yes | `slug` | lowercase identifier | — |
| `external_receipt_id` | yes | `text` | text | — |
| `accepted_at` | yes | `utc_instant` | UTC instant | — |
| `observed_at` | yes | `utc_instant` | UTC instant | — |
| `verification_key_id` | yes | `slug` | lowercase identifier | — |
| `signature` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `proof_level` | yes | `enum<ProofLevel>` | enumerated state/dimension; see the named enum | — |

### ArtifactManifest

Schema: `qc2.integrity_build.ArtifactManifest.v1`. Writer: `model_registry`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `manifest_version`, `files`, `inventory_hash`, `detached_signature`, `transport_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `manifest_version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `files` | yes | `artifact_file_list` | ordered array; item unit/type is stated by the field | — |
| `inventory_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `detached_signature` | yes | `nullable_text` | text | — |
| `transport_hash` | yes | `nullable_sha256` | SHA-256 digest (lowercase hexadecimal) | — |

Invariants:
- paths are normalized, relative, traversal-free, and unique
- the artifact verifier rejects symlinks, hardlinks, decompression bombs, and executable surprises
- content_hash excludes schema metadata, operational id/time, its own hash, detached_signature, and transport_hash
- inventory_hash binds file records sorted by normalized relative-path UTF-8 bytes; detached signature bytes do not hash themselves

### ArtifactDependency

Schema: `qc2.integrity_build.ArtifactDependency.v1`. Writer: `model_registry`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `parent_ref`, `dependency_ref`, `dependency_role`, `required_for_retention`, `discovered_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `parent_ref` | yes | `ref<ArtifactManifest>` | typed foreign reference to the listed contract | ArtifactManifest |
| `dependency_ref` | yes | `ref<ArtifactManifest>` | typed foreign reference to the listed contract | ArtifactManifest |
| `dependency_role` | yes | `slug` | lowercase identifier | — |
| `required_for_retention` | yes | `boolean` | not applicable | — |
| `discovered_at` | yes | `utc_instant` | UTC instant | — |

Invariants:
- retention dependency graph is acyclic

### BackupManifest

Schema: `qc2.integrity_build.BackupManifest.v1`. Writer: `evidence`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `recovery_point_at`, `database_snapshot_ref`, `artifact_inventory_refs`, `configuration_refs`, `key_inventory_hash`, `evidence_root_ref`, `anchor_receipt_refs`, `encryption_key_id`, `inventory_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `recovery_point_at` | yes | `utc_instant` | UTC instant | — |
| `database_snapshot_ref` | yes | `ref<ArtifactManifest>` | typed foreign reference to the listed contract | ArtifactManifest |
| `artifact_inventory_refs` | yes | `refs<ArtifactManifest|DataBundle|DatasetManifest|ModelManifest|PredictionSeal>` | typed foreign reference to the listed contract | ArtifactManifest, DataBundle, DatasetManifest, ModelManifest, PredictionSeal |
| `configuration_refs` | yes | `refs<ConfigurationManifest>` | typed foreign reference to the listed contract | ConfigurationManifest |
| `key_inventory_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `evidence_root_ref` | yes | `ref<Checkpoint>` | typed foreign reference to the listed contract | Checkpoint |
| `anchor_receipt_refs` | yes | `refs<AnchorReceipt>` | typed foreign reference to the listed contract | AnchorReceipt |
| `encryption_key_id` | yes | `slug` | lowercase identifier | — |
| `inventory_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### RestoreReceipt

Schema: `qc2.integrity_build.RestoreReceipt.v1`. Writer: `evidence`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `backup_ref`, `recovery_generation`, `restored_at`, `evidence_verdict`, `artifact_inventory_verdict`, `reconciliation_ref`, `outbound_orders_disabled`, `receipt_hash`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `backup_ref` | yes | `ref<BackupManifest>` | typed foreign reference to the listed contract | BackupManifest |
| `recovery_generation` | yes | `positive_int` | ordinal/count (unit is named by the field) | — |
| `restored_at` | yes | `utc_instant` | UTC instant | — |
| `evidence_verdict` | yes | `enum<IntegrityVerdict>` | enumerated state/dimension; see the named enum | — |
| `artifact_inventory_verdict` | yes | `enum<IntegrityVerdict>` | enumerated state/dimension; see the named enum | — |
| `reconciliation_ref` | yes | `nullable_ref<ReconciliationReport>` | typed foreign reference to the listed contract | — |
| `outbound_orders_disabled` | yes | `boolean` | not applicable | — |
| `receipt_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |

### ConfigurationManifest

Schema: `qc2.integrity_build.ConfigurationManifest.v1`. Writer: `configuration`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `configuration_domain`, `environment_namespace`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `configuration_domain`, `version`, `effective_from`, `capability_scope`, `required_setting_keys`, `setting_refs`, `resource_budget_refs`, `policy_hash`, `unresolved_decision_refs`, `fixture_only`, `signed_by_owner`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `configuration_domain` | yes | `enum<ConfigurationDomain>` | enumerated state/dimension; see the named enum | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `effective_from` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `capability_scope` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `required_setting_keys` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `setting_refs` | yes | `refs<ConfigurationSetting>` | typed foreign reference to the listed contract | ConfigurationSetting |
| `resource_budget_refs` | yes | `refs<ResourceBudget>` | typed foreign reference to the listed contract | ResourceBudget |
| `policy_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `unresolved_decision_refs` | yes | `refs<UnknownDecision>` | typed foreign reference to the listed contract | UnknownDecision |
| `fixture_only` | yes | `boolean` | not applicable | — |
| `signed_by_owner` | yes | `boolean` | not applicable | — |

Invariants:
- configuration setting and budget references are typed, hash-pinned, and effective for the manifest environment and session
- required_setting_keys are unique and include every bound production-required setting
- one latest effective manifest exists per configuration domain and capability
- invalid configuration blocks only capabilities in capability_scope

### ConfigurationSetting

Schema: `qc2.integrity_build.ConfigurationSetting.v1`. Writer: `configuration`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `configuration_domain`, `environment_namespace`, `setting_key`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `setting_key`, `configuration_domain`, `version`, `effective_from`, `value_hash`, `value_class`, `value_authority`, `required_capabilities`, `production_required`, `fixture_only`, `secret_reference_ref`, `resource_budget_ref`, `owner_approval_ref`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `setting_key` | yes | `slug` | lowercase identifier | — |
| `configuration_domain` | yes | `enum<ConfigurationDomain>` | enumerated state/dimension; see the named enum | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `effective_from` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `value_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `value_class` | yes | `enum<UnknownDecisionClass>` | enumerated state/dimension; see the named enum | — |
| `value_authority` | yes | `slug` | lowercase identifier | — |
| `required_capabilities` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `production_required` | yes | `boolean` | not applicable | — |
| `fixture_only` | yes | `boolean` | not applicable | — |
| `secret_reference_ref` | yes | `nullable_ref<SecretReference>` | typed foreign reference to the listed contract | — |
| `resource_budget_ref` | yes | `nullable_ref<ResourceBudget>` | typed foreign reference to the listed contract | — |
| `owner_approval_ref` | yes | `nullable_ref<OwnerCommandReceipt>` | typed foreign reference to the listed contract | — |

Invariants:
- at most one authoritative setting definition is effective for a domain, environment, and key at a session
- setting values are represented by value_hash; secret values are never persisted in this contract
- OWNER_POLICY_REQUIRED values carry a typed owner-approval reference

### SecretReference

Schema: `qc2.integrity_build.SecretReference.v1`. Writer: `configuration`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `environment_namespace`, `secret_key_name`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `secret_key_name`, `provider`, `version`, `required_capabilities`, `rotation_due_at`, `last_verified_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `secret_key_name` | yes | `slug` | lowercase identifier | — |
| `provider` | yes | `slug` | lowercase identifier | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `required_capabilities` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `rotation_due_at` | yes | `nullable_utc_instant` | UTC instant | — |
| `last_verified_at` | yes | `nullable_utc_instant` | UTC instant | — |

Invariants:
- the contract contains a symbolic, environment-scoped secret handle and never credential material

### ResourceBudget

Schema: `qc2.integrity_build.ResourceBudget.v1`. Writer: `configuration`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `configuration_domain`, `environment_namespace`, `budget_key`, `version`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `budget_key`, `configuration_domain`, `version`, `max_experiments`, `max_concurrent_jobs`, `max_elapsed_seconds`, `max_cpu_seconds`, `max_memory_bytes`, `max_artifact_bytes`, `authorized_cost_minor_units`, `currency`, `owner_approval_ref`, `effective_from`, `fixture_only`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `budget_key` | yes | `slug` | lowercase identifier | — |
| `configuration_domain` | yes | `enum<ConfigurationDomain>` | enumerated state/dimension; see the named enum | — |
| `version` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `max_experiments` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `max_concurrent_jobs` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `max_elapsed_seconds` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `max_cpu_seconds` | yes | `positive_int` | integer count (unit is named by the field) | — |
| `max_memory_bytes` | yes | `positive_int` | bytes | — |
| `max_artifact_bytes` | yes | `positive_int` | bytes | — |
| `authorized_cost_minor_units` | yes | `nonnegative_int` | integer count (unit is named by the field) | — |
| `currency` | yes | `currency_code` | ISO 4217 currency code | — |
| `owner_approval_ref` | yes | `nullable_ref<OwnerCommandReceipt>` | typed foreign reference to the listed contract | — |
| `effective_from` | yes | `session` | exchange session date (YYYY-MM-DD) | — |
| `fixture_only` | yes | `boolean` | not applicable | — |

Invariants:
- measured usage does not exceed any declared limit
- nonzero authorized_cost_minor_units requires a typed owner-approval reference
- fixture-only budgets are not eligible in production

### UnknownDecision

Schema: `qc2.integrity_build.UnknownDecision.v1`. Writer: `configuration`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `decision_key`, `decision_class`, `reason`, `affected_contract_refs`, `affected_capabilities`, `responsible_authority`, `evidence_needed`, `activation_consequence`, `decision_state`, `resolved_by`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `decision_key` | yes | `slug` | lowercase identifier | — |
| `decision_class` | yes | `enum<UnknownDecisionClass>` | enumerated state/dimension; see the named enum | — |
| `reason` | yes | `text` | text | — |
| `affected_contract_refs` | yes | `refs<ConfigurationManifest|OwnerCommandReceipt|ValidationReport|EvidenceEvent|ArtifactManifest|BuildTask>` | typed foreign reference to the listed contract | ConfigurationManifest, OwnerCommandReceipt, ValidationReport, EvidenceEvent, ArtifactManifest, BuildTask |
| `affected_capabilities` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `responsible_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_needed` | yes | `text` | text | — |
| `activation_consequence` | yes | `text` | text | — |
| `decision_state` | yes | `enum<UnknownDecisionState>` | enumerated state/dimension; see the named enum | — |
| `resolved_by` | yes | `nullable_ref<OwnerCommandReceipt>` | typed foreign reference to the listed contract | — |

Invariants:
- unresolved production decisions block only their affected capabilities
- a decision becomes resolved only with the named authority and required evidence

### ChangeRequest

Schema: `qc2.integrity_build.ChangeRequest.v1`. Writer: `build_governance`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `change_class`, `requirements_changed`, `reason`, `impact_analysis`, `migration_plan`, `test_refs`, `effective_boundary`, `is_restrictive_only`, `owner_approval_ref`, `status`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `change_class` | yes | `enum<ChangeClass>` | enumerated state/dimension; see the named enum | — |
| `requirements_changed` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `reason` | yes | `text` | text | — |
| `impact_analysis` | yes | `text` | text | — |
| `migration_plan` | yes | `text` | text | — |
| `test_refs` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `effective_boundary` | yes | `text` | text | — |
| `is_restrictive_only` | yes | `boolean` | not applicable | — |
| `owner_approval_ref` | yes | `nullable_ref<OwnerCommandReceipt>` | typed foreign reference to the listed contract | — |
| `status` | yes | `enum<ChangeRequestState>` | enumerated state/dimension; see the named enum | — |

Invariants:
- C0/C1 are release-bound, C1 requires equivalence tests, and C2 is bound to a non-past epoch session
- C3 carries the exact owner-approval hash and C4 can only take effect immediately when restrictive

### ReferenceIntake

Schema: `qc2.integrity_build.ReferenceIntake.v1`. Writer: `build_governance`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `repository_identity`, `revision`, `file_path`, `file_sha256`, `inspected_symbol`, `relevant_test_refs`, `reason_for_inspection`, `source_supported_meaning`, `useful_concepts`, `conflicts`, `license`, `provenance_limits`, `disposition`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `repository_identity` | yes | `text` | text | — |
| `revision` | yes | `text` | text | — |
| `file_path` | yes | `text` | text | — |
| `file_sha256` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `inspected_symbol` | yes | `text` | text | — |
| `relevant_test_refs` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `reason_for_inspection` | yes | `text` | text | — |
| `source_supported_meaning` | yes | `text` | text | — |
| `useful_concepts` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `conflicts` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `license` | yes | `text` | text | — |
| `provenance_limits` | yes | `text` | text | — |
| `disposition` | yes | `enum<ReferenceDisposition>` | enumerated state/dimension; see the named enum | — |

### BuildTask

Schema: `qc2.integrity_build.BuildTask.v1`. Writer: `build_governance`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `task_id`, `task_name`, `objective`, `dependency_task_ids`, `authorized_legacy_refs`, `deliverable_refs`, `required_test_refs`, `acceptance_gate`, `evidence_requirement`, `calibration_dependency`, `task_state`, `blocker_refs`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `task_id` | yes | `slug` | lowercase identifier | — |
| `task_name` | yes | `text` | text | — |
| `objective` | yes | `text` | text | — |
| `dependency_task_ids` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `authorized_legacy_refs` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `deliverable_refs` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `required_test_refs` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `acceptance_gate` | yes | `text` | text | — |
| `evidence_requirement` | yes | `slug` | lowercase identifier | — |
| `calibration_dependency` | yes | `enum<CalibrationDependency>` | enumerated state/dimension; see the named enum | — |
| `task_state` | yes | `enum<BuildTaskState>` | enumerated state/dimension; see the named enum | — |
| `blocker_refs` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |

### TaskAcceptanceReceipt

Schema: `qc2.integrity_build.TaskAcceptanceReceipt.v1`. Writer: `build_governance`. Readers: apexlab, build_governance, configuration, core, evidence, governance, model_registry, owner_api, validation.

Identity: `id`. Immutable fields: `schema_name`, `schema_version`, `id`, `created_at`, `owning_authority`, `evidence_class`, `environment_namespace`, `source_refs`, `content_hash`, `task_ref`, `task_spec_version`, `source_commit`, `changed_paths`, `executed_commands`, `test_counts`, `artifact_hashes`, `legacy_intake_refs`, `unresolved_decisions`, `gate_verdict`, `agent_identity`, `reviewer_identity`, `checked_at`.

| Field | Required | Type | Unit | Foreign target |
|---|---:|---|---|---|
| `schema_name` | yes | `text` | text | — |
| `schema_version` | yes | `text` | text | — |
| `id` | yes | `uuidv7` | UUIDv7 identifier | — |
| `created_at` | yes | `utc_instant` | UTC instant | — |
| `owning_authority` | yes | `slug` | lowercase identifier | — |
| `evidence_class` | yes | `enum<EvidenceClass>` | enumerated state/dimension; see the named enum | — |
| `environment_namespace` | yes | `enum<EnvironmentNamespace>` | enumerated state/dimension; see the named enum | — |
| `source_refs` | yes | `ref_list` | ordered array; item unit/type is stated by the field | — |
| `content_hash` | yes | `sha256` | SHA-256 digest (lowercase hexadecimal) | — |
| `task_ref` | yes | `ref<BuildTask>` | typed foreign reference to the listed contract | BuildTask |
| `task_spec_version` | yes | `text` | text | — |
| `source_commit` | yes | `text` | text | — |
| `changed_paths` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `executed_commands` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `test_counts` | yes | `test_count_list` | ordered array; item unit/type is stated by the field | — |
| `artifact_hashes` | yes | `hash_list` | ordered array; item unit/type is stated by the field | — |
| `legacy_intake_refs` | yes | `refs<ReferenceIntake>` | typed foreign reference to the listed contract | ReferenceIntake |
| `unresolved_decisions` | yes | `text_list` | ordered array; item unit/type is stated by the field | — |
| `gate_verdict` | yes | `enum<BuildGateVerdict>` | enumerated state/dimension; see the named enum | — |
| `agent_identity` | yes | `text` | text | — |
| `reviewer_identity` | yes | `nullable_text` | text | — |
| `checked_at` | yes | `utc_instant` | UTC instant | — |

## Android-visible compatibility boundary

24 Android-visible contract models are generated as `packages/contracts/android/Qc2WireContracts.kt`. Shared JSON fixtures also produce `Qc2WireFixtureSmoke.kt`; the pure Kotlin models and fixture constructions compile with `kotlinc`. TypeScript compiles the same JSON fixtures against generated TypeScript interfaces, and Python validates the fixture bytes against JSON Schema and semantic invariants.

The Android app remains a reserved boundary with no serializer/runtime or Android SDK configuration. This is a Kotlin wire-shape compile test, not an Android application instrumentation test or a runtime JSON decoder test. A future Android implementation must select a serializer, keep decimals/time/IDs as strings at the wire boundary, and test actual decoding against these schemas before shipping.

## Fixtures and verification

`fixtures/v1/valid.json` contains one valid synthetic fixture for each of the 124 contracts. `fixtures/v1/invalid.json` contains unknown-field and incompatible-version cases for every object, plus hostile decimal, timezone, temporal, identity/reference, execution, missingness, state-transition, and field-consistency examples. They are test data only and are never activation evidence.

Run `python3 tools/generate_contract_package.py --check`, `python3 -m pytest tests/contracts -q`, the generated Kotlin smoke compile, and `pnpm exec tsc --noEmit --strict --target ES2022 packages/contracts/src/qc2_contracts/generated.ts` to verify generated artifacts and cross-language shapes.
