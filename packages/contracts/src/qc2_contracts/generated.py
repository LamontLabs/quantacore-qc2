"""Generated QC2 v1 TypedDict models. Do not edit by hand."""
from typing import Literal, NotRequired, TypedDict

UuidV7 = str
UtcInstant = str
SessionDate = str
Sha256 = str
DecimalString = str
ContinuousDecimal = str
Probability = str
Fraction = str
Score = str

EvidenceClass = Literal['SYNTHETIC_FIXTURE', 'HISTORICAL_RECONSTRUCTED', 'FORWARD_OPERATIONAL', 'FORWARD_SEALED']
EnvironmentNamespace = Literal['development', 'test', 'research', 'production']
MarketPhase = Literal['PRE_OPEN', 'REGULAR', 'POST_CLOSE', 'CLOSED', 'UNAVAILABLE']
ClockStatus = Literal['TRUSTED', 'UNCERTAIN', 'BACKWARD_JUMP', 'UNAVAILABLE']
JobState = Literal['QUEUED', 'CLAIMED', 'RUNNING', 'WAITING_EXTERNAL', 'RETRYABLE_FAILURE', 'COMPLETED', 'TERMINAL_FAILURE', 'CANCELLED']
JobAttemptState = Literal['STARTED', 'SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_TERMINAL', 'CANCELLED']
OutboxState = Literal['PENDING', 'PUBLISHING', 'DELIVERED', 'UNKNOWN', 'FAILED']
ReadinessAction = Literal['INGESTION_PREFLIGHT', 'SNAPSHOT_READY', 'PREDICT', 'NEW_ENTRY', 'CANCEL_ENTRY', 'EXIT_POSITION', 'PROMOTE', 'RELEASE_TRAINING_DATA', 'RESTORE', 'RESEARCH']
ReadinessStatus = Literal['READY', 'BLOCKED', 'DEGRADED', 'UNKNOWN']
IdentityStatus = Literal['VERIFIED', 'UNRESOLVED', 'RETIRED']
InstrumentClass = Literal['US_COMMON_EQUITY', 'ETF', 'ETN', 'CLOSED_END_FUND', 'PREFERRED', 'WARRANT', 'RIGHT', 'UNIT', 'ADR', 'REIT_COMMON', 'OPTION', 'FUTURE', 'CRYPTO', 'OTC', 'UNKNOWN']
CorporateActionType = Literal['SPLIT', 'REVERSE_SPLIT', 'DIVIDEND', 'CASH_MERGER', 'STOCK_MERGER', 'SPINOFF', 'DISTRIBUTION', 'DELISTING', 'OTHER_REVIEW_REQUIRED']
ActionUncertainty = Literal['VERIFIED', 'UNCERTAIN', 'CONFLICTED', 'UNKNOWN']
MarketFeed = Literal['SIP', 'IEX']
AdjustmentMode = Literal['RAW', 'SPLIT_ADJUSTED']
BarTimeframe = Literal['1DAY']
BarStatus = Literal['PROVISIONAL', 'FINAL', 'REVISED', 'MISSING', 'QUARANTINED']
DataCapability = Literal['MARKET_DATA', 'PAPER_TRADING', 'CALENDAR', 'CORPORATE_ACTIONS', 'CLASSIFICATION']
CapabilityResult = Literal['AVAILABLE', 'UNAVAILABLE', 'PARTIAL', 'UNKNOWN', 'BLOCKED']
CompletenessState = Literal['COMPLETE', 'PARTIAL', 'FAILED']
QuarantineDisposition = Literal['PENDING_REVIEW', 'ACCEPTED', 'REJECTED', 'UNRESOLVED']
MissingnessPolicy = Literal['EXPLICIT_REASON', 'TRAINED_IMPUTER', 'UNSCORABLE', 'NOT_APPLICABLE']
ZeroDenominatorPolicy = Literal['MISSING', 'UNSCORABLE', 'EXPLICIT_ZERO', 'NOT_APPLICABLE']
SignalDirection = Literal['POSITIVE', 'NEGATIVE', 'NEUTRAL', 'UNKNOWN']
RunnerProtocolResultState = Literal['PASS', 'BLOCK', 'OBSERVE', 'UNKNOWN', 'UNAVAILABLE']
SafetyResultState = Literal['PASS', 'WARN', 'BLOCK', 'UNKNOWN']
MissingnessStatus = Literal['PRESENT', 'MISSING', 'UNKNOWN', 'NOT_APPLICABLE']
FeatureMissingReason = Literal['WARMUP_REQUIRED', 'SOURCE_FIELD_MISSING', 'QUARANTINED_INPUT', 'DIVISION_BY_ZERO', 'NOT_APPLICABLE', 'UNKNOWN']
OutcomeFieldStatus = Literal['VALID', 'MISSING', 'UNRESOLVED', 'NOT_APPLICABLE', 'CENSORED']
GateStatus = Literal['PASS', 'WARN', 'BLOCK', 'UNKNOWN', 'UNAVAILABLE']
WarningPolicy = Literal['BLOCK', 'ALLOW_WITH_EVIDENCE', 'NOT_ALLOWED']
PriceReference = Literal['PREDICTION_SESSION_DAILY_CLOSE', 'NEXT_SESSION_DAILY_OPEN_PROXY', 'ACTUAL_PAPER_FILL', 'SPLIT_CONSISTENT_CLOSE', 'SPLIT_CONSISTENT_HIGH', 'SPLIT_CONSISTENT_LOW']
LabelTarget = Literal['EXPANSION_RUNNER', 'SESSION_MONSTER', 'CONTINUATION', 'FAILURE', 'TIME_TO_EXPANSION']
MissingHeadPolicy = Literal['BLOCK_ROW', 'EXPLICIT_PENALTY', 'OMIT_WITH_SEPARATE_STATUS']
BaselineKind = Literal['RANDOM', 'MOMENTUM_1', 'MOMENTUM_5', 'MOMENTUM_20', 'RELATIVE_VOLUME', 'BREAKOUT_PROXIMITY', 'TRANSPARENT_COMPOSITE', 'REFERENCE_CHAMPION']
ComparatorRole = Literal['PRIMARY', 'SECONDARY', 'REFERENCE']
ModelHeadKind = Literal['PROBABILITY', 'EXPECTED_MFE', 'EXPECTED_MAE', 'CONTINUATION', 'FAILURE', 'TIME_TO_EXPANSION', 'SCORE']
HeadAvailability = Literal['AVAILABLE', 'UNAVAILABLE_LABEL', 'UNAVAILABLE_MODEL', 'INVALID']
ModelLifecycle = Literal['RESEARCH', 'CANDIDATE', 'CHALLENGER', 'SHADOW', 'PROMOTION_ELIGIBLE', 'CHAMPION', 'REJECTED', 'RETIRED']
PredictionRunState = Literal['CREATED', 'INPUTS_BOUND', 'FEATURES_COMPLETE', 'SCORED', 'RANKED', 'SEALED', 'ABORTED', 'FAILED_BEFORE_SEAL']
PredictionDisposition = Literal['SCORED', 'UNSCORABLE', 'EXCLUDED', 'PENDING']
PredictionRowDisposition = Literal['SCORED', 'UNSCORABLE']
ExtremaTieBreak = Literal['EARLIEST_SESSION']
PredictionRole = Literal['OPERATING', 'REFERENCE', 'BASELINE', 'SHADOW', 'DIAGNOSTIC']
ReplayMode = Literal['EXACT', 'CORRECTED_DATA_SENSITIVITY', 'COMPATIBILITY_EXPERIMENT']
ReplayVerdict = Literal['MATCH', 'MISMATCH', 'BLOCKED', 'INCOMPLETE']
OutcomeState = Literal['PENDING_MATURITY', 'RESOLVED', 'PARTIALLY_RESOLVABLE', 'UNRESOLVED_DATA', 'CORPORATE_ACTION_REVIEW', 'CENSORED_TERMINAL_EVENT']
RunnerEventType = Literal['EXPANSION_RUNNER', 'SESSION_MONSTER', 'NEAR_RUNNER', 'FAILURE']
FailureType = Literal['FALSE_MONSTER', 'MISSED_RUNNER', 'COLLAPSE', 'TIMING_MISS', 'DATA_ERROR']
MemoryIndexKind = Literal['RUNNER', 'FAILURE', 'DECOY', 'MIXED']
ReviewKind = Literal['MISSED_MONSTER', 'FALSE_MONSTER', 'FAILURE', 'DATA_QUALITY']
UniverseFidelity = Literal['PIT_VERIFIED', 'SURVIVORSHIP_LIMITED', 'UNKNOWN']
AvailabilityPolicy = Literal['FORWARD_OBSERVED', 'HISTORICAL_RECONSTRUCTED']
SplitUnit = Literal['EXCHANGE_SESSION']
HoldoutAccessScope = Literal['METRICS_ONLY', 'AGGREGATES_ONLY', 'ROW_LEVEL_APPROVED']
EvaluationVerdict = Literal['PASS', 'FAIL', 'INSUFFICIENT_EVIDENCE', 'BLOCKED']
DriftState = Literal['STABLE', 'DRIFT', 'INSUFFICIENT_EVIDENCE', 'UNAVAILABLE']
OperatingMode = Literal['FROZEN_CHAMPION', 'PRE_REGISTERED_ADAPTIVE']
EpochState = Literal['DRAFT', 'READY', 'ACTIVE', 'OUTCOME_MATURATION', 'CLOSED_PASS', 'CLOSED_FAIL', 'INSUFFICIENT_EVIDENCE', 'HELD', 'ABORTED']
ScheduledAttemptState = Literal['SCHEDULED', 'STARTED', 'SEALED', 'MISSED_START', 'FAILED', 'NONQUALIFYING']
IntegrityVerdict = Literal['FULL_VERIFIED', 'PARTIAL_SCAN', 'FAILED', 'UNAVAILABLE', 'VALID', 'INVALID']
CoverageStatus = Literal['VALID', 'INSUFFICIENT', 'MISSING', 'UNKNOWN']
MetricDirection = Literal['HIGHER_IS_BETTER', 'LOWER_IS_BETTER', 'DESCRIPTIVE']
ValidationVerdict = Literal['PASS', 'FAIL', 'INSUFFICIENT_EVIDENCE', 'NOT_INTERPRETABLE']
QuantityRounding = Literal['WHOLE_SHARES_FLOOR']
PaperAction = Literal['OPEN_LONG', 'REDUCE_LONG', 'CLOSE_LONG', 'CANCEL_PENDING_ENTRY', 'REPLACE_ORDER']
OrderSide = Literal['BUY', 'SELL']
OrderType = Literal['LIMIT', 'STOP', 'STOP_LIMIT', 'MARKET']
TimeInForce = Literal['DAY', 'GTC']
SessionRestriction = Literal['REGULAR_SESSION_ONLY']
AccountMode = Literal['PAPER']
IntentState = Literal['CREATED', 'VERIFIED', 'RESERVED', 'QUEUED_FOR_SUBMISSION', 'SUBMISSION_STARTED', 'ACKNOWLEDGED', 'SUBMISSION_UNKNOWN', 'REJECTED', 'PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED', 'CANCELLED', 'EXPIRED', 'REPLACED']
IntentDecisionState = Literal['ACCEPTED', 'DENIED', 'STALE', 'EXPIRED', 'BLOCKED']
SubmissionOutcome = Literal['ACKNOWLEDGED', 'SUBMISSION_UNKNOWN', 'REJECTED']
BrokerOrderState = Literal['ACKNOWLEDGED', 'SUBMISSION_UNKNOWN', 'REJECTED', 'PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED', 'CANCELLED', 'EXPIRED', 'REPLACED']
BrokerOrderEventType = Literal['ACCEPTED', 'PARTIAL_FILL', 'FILL', 'CANCEL_REQUEST', 'CANCELLED', 'REJECTED', 'EXPIRED', 'CORRECTION']
FillCorrectionKind = Literal['BUST', 'QUANTITY_ADJUSTMENT', 'PRICE_ADJUSTMENT', 'FEE_ADJUSTMENT']
ReconciliationStatus = Literal['RECONCILED', 'DISCREPANCY', 'UNKNOWN', 'HOLD']
CashEntryKind = Literal['OPENING_BALANCE', 'FILL', 'FEE', 'CORPORATE_ACTION', 'MANUAL_ADJUSTMENT']
ReservationKind = Literal['CASH', 'SHARES']
ReservationState = Literal['ACTIVE', 'PARTIALLY_CONSUMED', 'SETTLED', 'RELEASED', 'HELD']
PromotionRequestState = Literal['SUBMITTED', 'VERIFIED', 'DENIED', 'EXPIRED', 'COMMITTED']
OwnerDecision = Literal['APPROVE', 'HOLD', 'REJECT']
PromotionReceiptState = Literal['COMMITTED', 'FAILED', 'BLOCKED']
ChampionRole = Literal['OPERATING', 'REFERENCE']
EpochActivationChoice = Literal['APPROVE', 'REJECT']
ActivationState = Literal['ACTIVATED', 'REJECTED', 'BLOCKED']
SigningAlgorithm = Literal['ED25519', 'ECDSA_P256_SHA256']
DeviceSecurityLevel = Literal['SOFTWARE', 'TEE', 'STRONGBOX', 'UNKNOWN']
DeviceRevocationState = Literal['ENROLLED', 'REVOKED']
RecoveryEventKind = Literal['DEVICE_LOST', 'REPLACEMENT_ENROLLED', 'KEY_ROTATED', 'SESSION_REVOKED']
OwnerCommandType = Literal['PROMOTION', 'EPOCH_ACTIVATION', 'PAUSE_NEW_ENTRIES', 'RESUME_REQUEST', 'ACKNOWLEDGE_ALERT', 'DEVICE_ACTION']
OwnerCommandScope = Literal['PROMOTION', 'EPOCH_ACTIVATION', 'PAUSE', 'RESUME', 'ALERT', 'DEVICE_ADMIN']
OwnerCommandReceiptState = Literal['ACCEPTED', 'DUPLICATE', 'DENIED', 'STALE', 'EXPIRED', 'EXECUTED']
AlertSeverity = Literal['INFO', 'NOTICE', 'WARNING', 'CRITICAL', 'EMERGENCY']
ProofLevel = Literal['BACKEND_LOCAL_TAMPER_EVIDENT', 'INDEPENDENT_PREOUTCOME_ANCHORED']
ConfigurationDomain = Literal['SYSTEM', 'EPOCH_SCIENTIFIC', 'STRATEGY', 'RESEARCH', 'DEPLOYMENT', 'OWNER_IDENTITY']
UnknownDecisionClass = Literal['ARCHITECTURAL_CONSTANT', 'OWNER_POLICY_REQUIRED', 'CAPABILITY_MEASUREMENT_REQUIRED', 'EMPIRICAL_CALIBRATION_REQUIRED', 'ENGINEERING_LIMIT_REQUIRED']
UnknownDecisionState = Literal['UNRESOLVED', 'RESOLVED', 'SUPERSEDED']
ChangeClass = Literal['C0', 'C1', 'C2', 'C3', 'C4']
ChangeRequestState = Literal['PROPOSED', 'APPROVED', 'REJECTED', 'IMPLEMENTED', 'NEEDS_REVALIDATION']
ReferenceDisposition = Literal['REUSE', 'ADAPT', 'TESTS_ONLY', 'REWRITE', 'IGNORE']
CalibrationDependency = Literal['FRAMEWORK_OR_POLICY_ONLY', 'CALIBRATION_REQUIRED']
BuildTaskState = Literal['TODO', 'IN_PROGRESS', 'PASS', 'BLOCKED']
BuildGateVerdict = Literal['PASS', 'FAIL', 'BLOCKED', 'INCOMPLETE']
TimezoneId = Literal['UTC', 'America/New_York']

class ForeignReference(TypedDict):
    target_schema_name: str
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class FeatureValueRecord(TypedDict):
    feature_id: str
    unit: str
    value: NotRequired[DecimalString]
    missing_reason: NotRequired['FeatureMissingReason']

class GateResultRecord(TypedDict):
    gate_id: str
    status: 'GateStatus'
    reason_codes: list[str]
    evaluated_at: UtcInstant
    source_refs: list[ForeignReference]

class ArtifactFileRecord(TypedDict):
    relative_path: str
    length_bytes: int
    media_type: str
    schema_name: str
    schema_version: str
    sha256: Sha256

class EvidenceValueRecord(TypedDict):
    key: str
    value: ContinuousDecimal
    unit: str
    uncertainty: ContinuousDecimal | None

class OutcomeFieldValidityRecord(TypedDict):
    field_name: str
    status: 'OutcomeFieldStatus'
    reason_code: str | None

class TestCountRecord(TypedDict):
    test_id: str
    passed: int
    failed: int
    skipped: int

class Reference_AdjustmentManifest(TypedDict):
    target_schema_name: Literal['qc2.identity_market.AdjustmentManifest.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_Alert(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.Alert.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_AnchorReceipt(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.AnchorReceipt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ArtifactDependency(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.ArtifactDependency.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ArtifactManifest(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.ArtifactManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_BackupManifest(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.BackupManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_BarSemanticsManifest(TypedDict):
    target_schema_name: Literal['qc2.identity_market.BarSemanticsManifest.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_BaselineManifest(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.BaselineManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_BrokerOrder(TypedDict):
    target_schema_name: Literal['qc2.execution.BrokerOrder.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_BrokerOrderEvent(TypedDict):
    target_schema_name: Literal['qc2.execution.BrokerOrderEvent.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_BuildTask(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.BuildTask.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_CalendarManifest(TypedDict):
    target_schema_name: Literal['qc2.time_operation.CalendarManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_CalendarRevision(TypedDict):
    target_schema_name: Literal['qc2.time_operation.CalendarRevision.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_CandidateCensus(TypedDict):
    target_schema_name: Literal['qc2.identity_market.CandidateCensus.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_CandidateEvaluation(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.CandidateEvaluation.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_CapitalPolicy(TypedDict):
    target_schema_name: Literal['qc2.execution.CapitalPolicy.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_CashLedgerEntry(TypedDict):
    target_schema_name: Literal['qc2.execution.CashLedgerEntry.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ChallengerEvaluation(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.ChallengerEvaluation.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ChampionPointer(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.ChampionPointer.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ChangeRequest(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.ChangeRequest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_Checkpoint(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.Checkpoint.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_ClockAssessment(TypedDict):
    target_schema_name: Literal['qc2.time_operation.ClockAssessment.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ConfigurationManifest(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.ConfigurationManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_CorporateActionRecord(TypedDict):
    target_schema_name: Literal['qc2.identity_market.CorporateActionRecord.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_DailyBar(TypedDict):
    target_schema_name: Literal['qc2.identity_market.DailyBar.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_DataBundle(TypedDict):
    target_schema_name: Literal['qc2.identity_market.DataBundle.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_DataCapabilityManifest(TypedDict):
    target_schema_name: Literal['qc2.identity_market.DataCapabilityManifest.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_DatasetManifest(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.DatasetManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_DatasetRowLineage(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.DatasetRowLineage.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_DeploymentCapabilityManifest(TypedDict):
    target_schema_name: Literal['qc2.time_operation.DeploymentCapabilityManifest.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_DriftAssessment(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.DriftAssessment.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_EnrollmentChallenge(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.EnrollmentChallenge.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_EpochActivationChallenge(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.EpochActivationChallenge.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_EpochActivationDecision(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.EpochActivationDecision.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_EpochActivationReceipt(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.EpochActivationReceipt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_EpochManifest(TypedDict):
    target_schema_name: Literal['qc2.validation.EpochManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_EvidenceEvent(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.EvidenceEvent.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_ExecutionEpisode(TypedDict):
    target_schema_name: Literal['qc2.execution.ExecutionEpisode.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_Experiment(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.Experiment.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_FailureGenome(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.FailureGenome.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_FeatureDefinition(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.FeatureDefinition.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_FeatureRegistry(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.FeatureRegistry.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_FeatureSnapshot(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.FeatureSnapshot.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_Fill(TypedDict):
    target_schema_name: Literal['qc2.execution.Fill.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_FillCorrection(TypedDict):
    target_schema_name: Literal['qc2.execution.FillCorrection.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_HoldoutAccessReceipt(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.HoldoutAccessReceipt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_InferenceReceipt(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.InferenceReceipt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_Instrument(TypedDict):
    target_schema_name: Literal['qc2.identity_market.Instrument.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_InstrumentClassification(TypedDict):
    target_schema_name: Literal['qc2.identity_market.InstrumentClassification.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_IntentDecision(TypedDict):
    target_schema_name: Literal['qc2.execution.IntentDecision.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_JobAttempt(TypedDict):
    target_schema_name: Literal['qc2.time_operation.JobAttempt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_JobDefinition(TypedDict):
    target_schema_name: Literal['qc2.time_operation.JobDefinition.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_JobLease(TypedDict):
    target_schema_name: Literal['qc2.time_operation.JobLease.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_LabelDefinition(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.LabelDefinition.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_LabelRegistry(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.LabelRegistry.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_MarketSession(TypedDict):
    target_schema_name: Literal['qc2.time_operation.MarketSession.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_MarketSnapshot(TypedDict):
    target_schema_name: Literal['qc2.identity_market.MarketSnapshot.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_MarketSnapshotRevision(TypedDict):
    target_schema_name: Literal['qc2.identity_market.MarketSnapshotRevision.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_MatchedDecoySet(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.MatchedDecoySet.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_MemoryIndexManifest(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.MemoryIndexManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_MetricDefinition(TypedDict):
    target_schema_name: Literal['qc2.validation.MetricDefinition.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_MetricResult(TypedDict):
    target_schema_name: Literal['qc2.validation.MetricResult.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ModelHeadDefinition(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.ModelHeadDefinition.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ModelHeadOutput(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.ModelHeadOutput.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ModelManifest(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.ModelManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_OutboxMessage(TypedDict):
    target_schema_name: Literal['qc2.time_operation.OutboxMessage.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_Outcome(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.Outcome.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_OutcomeRevision(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.OutcomeRevision.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_OwnerCommand(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.OwnerCommand.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_OwnerCommandReceipt(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.OwnerCommandReceipt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_OwnerDevice(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.OwnerDevice.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_OwnerSession(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.OwnerSession.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_PaperOrderIntent(TypedDict):
    target_schema_name: Literal['qc2.execution.PaperOrderIntent.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_Position(TypedDict):
    target_schema_name: Literal['qc2.execution.Position.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_Prediction(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.Prediction.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_PredictionRun(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.PredictionRun.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_PredictionSeal(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.PredictionSeal.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_PromotionBundleManifest(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.PromotionBundleManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_PromotionChallenge(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.PromotionChallenge.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_PromotionDecision(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.PromotionDecision.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_PromotionPolicy(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.PromotionPolicy.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_PromotionReceipt(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.PromotionReceipt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_PromotionRequest(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.PromotionRequest.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_QualificationReceipt(TypedDict):
    target_schema_name: Literal['qc2.validation.QualificationReceipt.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_QuarantineCase(TypedDict):
    target_schema_name: Literal['qc2.identity_market.QuarantineCase.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_RawReceipt(TypedDict):
    target_schema_name: Literal['qc2.identity_market.RawReceipt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ReadinessAssessment(TypedDict):
    target_schema_name: Literal['qc2.time_operation.ReadinessAssessment.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ReconciliationReport(TypedDict):
    target_schema_name: Literal['qc2.execution.ReconciliationReport.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_RecoveryEvent(TypedDict):
    target_schema_name: Literal['qc2.governance_owner.RecoveryEvent.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ReferenceIntake(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.ReferenceIntake.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_ReplayReceipt(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.ReplayReceipt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ReplayRequest(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.ReplayRequest.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ReportAmendment(TypedDict):
    target_schema_name: Literal['qc2.validation.ReportAmendment.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_RequestManifest(TypedDict):
    target_schema_name: Literal['qc2.identity_market.RequestManifest.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_Reservation(TypedDict):
    target_schema_name: Literal['qc2.execution.Reservation.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_RestoreReceipt(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.RestoreReceipt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ReviewCase(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.ReviewCase.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_RunDisposition(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.RunDisposition.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_RunnerEvent(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.RunnerEvent.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_RunnerGenome(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.RunnerGenome.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_RunnerProtocolDefinition(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.RunnerProtocolDefinition.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_RunnerProtocolRegistry(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.RunnerProtocolRegistry.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_RunnerProtocolResult(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.RunnerProtocolResult.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_SafetyProtocolDefinition(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.SafetyProtocolDefinition.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_SafetyProtocolResult(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.SafetyProtocolResult.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_ScheduledAttempt(TypedDict):
    target_schema_name: Literal['qc2.validation.ScheduledAttempt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ScientificPredictionPayload(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.ScientificPredictionPayload.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_ScoreDefinition(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.ScoreDefinition.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_ScoreManifest(TypedDict):
    target_schema_name: Literal['qc2.scientific_definitions.ScoreManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_ShadowPredictionSet(TypedDict):
    target_schema_name: Literal['qc2.models_prediction.ShadowPredictionSet.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_SplitManifest(TypedDict):
    target_schema_name: Literal['qc2.outcomes_research.SplitManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_StatisticalAnalysisPlan(TypedDict):
    target_schema_name: Literal['qc2.validation.StatisticalAnalysisPlan.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_StrategyManifest(TypedDict):
    target_schema_name: Literal['qc2.execution.StrategyManifest.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_SubmissionAttempt(TypedDict):
    target_schema_name: Literal['qc2.execution.SubmissionAttempt.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_SymbolAssignment(TypedDict):
    target_schema_name: Literal['qc2.identity_market.SymbolAssignment.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_TaskAcceptanceReceipt(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.TaskAcceptanceReceipt.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_UniverseManifest(TypedDict):
    target_schema_name: Literal['qc2.identity_market.UniverseManifest.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_UnknownDecision(TypedDict):
    target_schema_name: Literal['qc2.integrity_build.UnknownDecision.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class Reference_ValidationEpoch(TypedDict):
    target_schema_name: Literal['qc2.validation.ValidationEpoch.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_ValidationReport(TypedDict):
    target_schema_name: Literal['qc2.validation.ValidationReport.v1']
    target_id: UuidV7
    content_hash: Sha256

class Reference_ValidationSession(TypedDict):
    target_schema_name: Literal['qc2.validation.ValidationSession.v1']
    target_id: UuidV7
    content_hash: NotRequired[Sha256]

class CalendarManifest(TypedDict):
    schema_name: Literal['qc2.time_operation.CalendarManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['calendar']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    calendar_version: int
    timezone: TimezoneId
    valid_from: str
    valid_through: str
    sessions: list[str]

class CalendarRevision(TypedDict):
    schema_name: Literal['qc2.time_operation.CalendarRevision.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['calendar']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    calendar_ref: Reference_CalendarManifest
    revision_number: int
    effective_session: str
    reason: str
    source_evidence_ref: Reference_EvidenceEvent

class MarketSession(TypedDict):
    schema_name: Literal['qc2.time_operation.MarketSession.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['calendar']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    session_id: str
    phase: MarketPhase
    opens_at: str
    closes_at: str
    calendar_revision_ref: Reference_CalendarRevision

class ClockAssessment(TypedDict):
    schema_name: Literal['qc2.time_operation.ClockAssessment.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['calendar']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    observed_at: str
    trusted_time_at: str
    wall_clock_at: str
    monotonic_elapsed_ms: int
    uncertainty_ms: int
    status: ClockStatus

class JobDefinition(TypedDict):
    schema_name: Literal['qc2.time_operation.JobDefinition.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['durable_job_service']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    logical_key: str
    dependency_refs: list[Reference_JobDefinition]
    deadline: str
    resource_budget_ref: Reference_ConfigurationManifest
    checkpoint_ref: Reference_Checkpoint | None
    state: JobState

class JobLease(TypedDict):
    schema_name: Literal['qc2.time_operation.JobLease.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['durable_job_service']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    job_ref: Reference_JobDefinition
    lease_owner: str
    lease_expires_at: str
    fencing_generation: int

class JobAttempt(TypedDict):
    schema_name: Literal['qc2.time_operation.JobAttempt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['durable_job_service']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    job_ref: Reference_JobDefinition
    attempt_number: int
    fencing_generation: int
    started_at: str
    finished_at: str | None
    attempt_state: JobAttemptState
    reason_code: str | None

class OutboxMessage(TypedDict):
    schema_name: Literal['qc2.time_operation.OutboxMessage.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['durable_job_service']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    logical_operation_id: str
    message_type: str
    payload_hash: str
    status: OutboxState
    attempt_count: int
    next_attempt_at: str | None

class ReadinessAssessment(TypedDict):
    schema_name: Literal['qc2.time_operation.ReadinessAssessment.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['safety']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    action: ReadinessAction
    status: ReadinessStatus
    gate_results: list[GateResultRecord]
    input_generation: int
    freshness_deadline: str

class DeploymentCapabilityManifest(TypedDict):
    schema_name: Literal['qc2.time_operation.DeploymentCapabilityManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['configuration']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    deployment_fingerprint: str
    observed_at: str
    capability_results: list[GateResultRecord]
    resource_limits_ref: Reference_ConfigurationManifest
    revalidation_due_at: str

class Instrument(TypedDict):
    schema_name: Literal['qc2.identity_market.Instrument.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['instrument_universe']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    stable_instrument_key: str
    first_known_at: str
    identity_status: IdentityStatus

class SymbolAssignment(TypedDict):
    schema_name: Literal['qc2.identity_market.SymbolAssignment.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['instrument_universe']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    instrument_ref: Reference_Instrument
    symbol: str
    exchange: str
    currency: str
    effective_from: str
    effective_to: str | None
    known_from: str
    known_to: str | None
    source_evidence_ref: Reference_EvidenceEvent
    mapping_confidence: Probability

class InstrumentClassification(TypedDict):
    schema_name: Literal['qc2.identity_market.InstrumentClassification.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['instrument_universe']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    instrument_ref: Reference_Instrument
    classification: InstrumentClass
    verified: bool
    valid_from: str
    valid_to: str | None
    source_evidence_ref: Reference_EvidenceEvent

class CorporateActionRecord(TypedDict):
    schema_name: Literal['qc2.identity_market.CorporateActionRecord.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    instrument_ref: Reference_Instrument
    action_type: CorporateActionType
    effective_session: str
    observed_at: str
    processing_session: str | None
    terms_hash: str
    uncertainty: ActionUncertainty

class AdjustmentManifest(TypedDict):
    schema_name: Literal['qc2.identity_market.AdjustmentManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    basis_session: str
    action_refs: list[Reference_CorporateActionRecord]
    price_factor: str
    volume_factor: str
    methodology_version: int
    available_at: str

class CandidateCensus(TypedDict):
    schema_name: Literal['qc2.identity_market.CandidateCensus.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['instrument_universe']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    session_id: str
    instrument_refs: list[Reference_Instrument]
    cutoff: str
    source_manifest_refs: list[Reference_RequestManifest | Reference_DataCapabilityManifest | Reference_InstrumentClassification]
    membership_hash: str

class DailyBar(TypedDict):
    schema_name: Literal['qc2.identity_market.DailyBar.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    instrument_ref: Reference_Instrument
    session_id: str
    feed: MarketFeed
    currency: str
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    volume: str
    observed_at: str
    finalized_at: str | None
    bar_status: BarStatus

class RawReceipt(TypedDict):
    schema_name: Literal['qc2.identity_market.RawReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    request_ref: Reference_RequestManifest
    provider: str
    received_at: str
    media_type: str
    byte_length: int
    raw_sha256: str
    storage_ref: str

class RequestManifest(TypedDict):
    schema_name: Literal['qc2.identity_market.RequestManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    provider: str
    feed: MarketFeed
    adjustment: AdjustmentMode
    timeframe: BarTimeframe
    currency: str
    calendar_ref: Reference_CalendarManifest
    bar_semantics_ref: Reference_BarSemanticsManifest
    cutoff: str
    sanitized_request_hash: str

class DataCapabilityManifest(TypedDict):
    schema_name: Literal['qc2.identity_market.DataCapabilityManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    deployment_fingerprint: str
    account_fingerprint: str
    capability: DataCapability
    observed_result: CapabilityResult
    feed: MarketFeed
    tested_at: str
    earliest_tested_session: str | None
    effective_delay_ms: int | None
    evidence_refs: list[Reference_EvidenceEvent]
    expires_at: str

class BarSemanticsManifest(TypedDict):
    schema_name: Literal['qc2.identity_market.BarSemanticsManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    provider: str
    feed: MarketFeed
    timeframe: BarTimeframe
    interval_timezone: TimezoneId
    field_meanings: list[str]
    revision_policy: str
    finalization_rule: str
    tested_at: str

class DataBundle(TypedDict):
    schema_name: Literal['qc2.identity_market.DataBundle.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    census_ref: Reference_CandidateCensus
    request_refs: list[Reference_RequestManifest]
    raw_receipt_refs: list[Reference_RawReceipt]
    bar_refs: list[Reference_DailyBar]
    history_start: str
    history_end: str
    coverage: Probability
    completeness: CompletenessState
    content_inventory_hash: str

class UniverseManifest(TypedDict):
    schema_name: Literal['qc2.identity_market.UniverseManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['instrument_universe']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    session_id: str
    census_ref: Reference_CandidateCensus
    data_bundle_ref: Reference_DataBundle
    eligibility_rule_hash: str
    eligible_instrument_refs: list[Reference_Instrument]
    unscorable_instrument_refs: list[Reference_Instrument]
    reason_counts: list[str]
    cutoff: str

class MarketSnapshot(TypedDict):
    schema_name: Literal['qc2.identity_market.MarketSnapshot.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    session_id: str
    calendar_ref: Reference_CalendarManifest
    census_ref: Reference_CandidateCensus
    data_bundle_ref: Reference_DataBundle
    universe_ref: Reference_UniverseManifest
    provider: str
    feed: MarketFeed
    decision_cutoff: str
    sealed_at: str
    row_count: int
    coverage: Fraction
    dependency_refs: list[Reference_CalendarManifest | Reference_CandidateCensus | Reference_DataBundle | Reference_UniverseManifest | Reference_RequestManifest | Reference_BarSemanticsManifest | Reference_AdjustmentManifest]

class MarketSnapshotRevision(TypedDict):
    schema_name: Literal['qc2.identity_market.MarketSnapshotRevision.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    prior_snapshot_ref: Reference_MarketSnapshot
    changed_observation_refs: list[Reference_DailyBar | Reference_CorporateActionRecord | Reference_SymbolAssignment]
    discovered_at: str
    reason_code: str
    source_evidence_ref: Reference_EvidenceEvent
    replacement_content_hash: str

class QuarantineCase(TypedDict):
    schema_name: Literal['qc2.identity_market.QuarantineCase.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['market_data']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    instrument_ref: Reference_Instrument
    observation_ref: Reference_DailyBar
    rule_id: str
    reason_code: str
    observed_at: str
    disposition: QuarantineDisposition
    evidence_ref: Reference_EvidenceEvent

class FeatureDefinition(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.FeatureDefinition.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['feature']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    stable_key: str
    version: int
    equation: str
    input_refs: list[Reference_FeatureDefinition | Reference_DailyBar | Reference_InstrumentClassification | Reference_AdjustmentManifest]
    input_units: list[str]
    lookback_sessions: int
    warmup_sessions: int
    alignment: str
    missingness_policy: MissingnessPolicy
    zero_denominator_policy: ZeroDenominatorPolicy
    supported_regime: str
    dependency_refs: list[Reference_FeatureDefinition]
    implementation_hash: str
    invariance_properties: list[str]

class FeatureRegistry(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.FeatureRegistry.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['feature']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    registry_version: int
    definition_refs: list[Reference_FeatureDefinition]
    ordered_feature_ids: list[str]
    effective_from: str

class FeatureSnapshot(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.FeatureSnapshot.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['feature']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    session_id: str
    instrument_ref: Reference_Instrument
    registry_ref: Reference_FeatureRegistry
    feature_values: list[FeatureValueRecord]
    input_hashes: list[str]
    transform_refs: list[Reference_ArtifactManifest | Reference_FeatureDefinition]
    decision_cutoff: str
    code_hash: str
    environment_fingerprint: str

class RunnerProtocolDefinition(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.RunnerProtocolDefinition.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['runner_protocol']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    protocol_namespace: str
    protocol_id: str
    version: int
    hypothesis: str
    direction: SignalDirection
    input_refs: list[Reference_FeatureDefinition | Reference_FeatureSnapshot | Reference_DailyBar]
    parameter_refs: list[Reference_ConfigurationManifest]
    implementation_hash: str
    regime: str

class RunnerProtocolRegistry(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.RunnerProtocolRegistry.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['runner_protocol']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    registry_version: int
    definition_refs: list[Reference_RunnerProtocolDefinition]
    active_protocol_ids: list[str]
    effective_from: str

class RunnerProtocolResult(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.RunnerProtocolResult.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['runner_protocol']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    protocol_ref: Reference_RunnerProtocolDefinition
    session_id: str
    instrument_ref: Reference_Instrument
    result: RunnerProtocolResultState
    hypothesis: str
    direction: SignalDirection
    evidence_values: list[EvidenceValueRecord]
    uncertainty: ContinuousDecimal | None
    missingness: MissingnessStatus
    parameter_hash: str
    implementation_hash: str
    cutoff: str
    input_refs: list[Reference_FeatureSnapshot | Reference_MarketSnapshot | Reference_DailyBar | Reference_RunnerProtocolResult]

class SafetyProtocolDefinition(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.SafetyProtocolDefinition.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['safety']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    protocol_key: str
    version: int
    action: ReadinessAction
    rule: str
    required_evidence: list[str]
    warning_policy: WarningPolicy
    implementation_hash: str

class SafetyProtocolResult(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.SafetyProtocolResult.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['safety']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    protocol_ref: Reference_SafetyProtocolDefinition
    action: ReadinessAction
    result: SafetyResultState
    reason_codes: list[str]
    observed_versions: list[str]
    evaluated_at: str
    freshness_deadline: str

class LabelDefinition(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.LabelDefinition.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['label']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    stable_key: str
    version: int
    horizon_sessions: int
    price_reference: PriceReference
    target_event: LabelTarget
    maturity_rule: str
    release_policy: str
    threshold: ContinuousDecimal | None
    threshold_unit: str | None

class LabelRegistry(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.LabelRegistry.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['label']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    registry_version: int
    definition_refs: list[Reference_LabelDefinition]
    primary_label_ref: Reference_LabelDefinition
    effective_from: str

class ScoreDefinition(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.ScoreDefinition.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['quantscore']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    stable_key: str
    version: int
    coefficients: list[ContinuousDecimal]
    transforms: list[str]
    clipping_policy: str
    missing_head_policy: MissingHeadPolicy
    tie_break_rule: str
    input_refs: list[Reference_ModelHeadDefinition | Reference_RunnerProtocolResult | Reference_FeatureDefinition | Reference_FeatureSnapshot]

class ScoreManifest(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.ScoreManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['quantscore']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    definition_ref: Reference_ScoreDefinition
    score_precision: int
    score_unit: str
    frozen_at: str

class BaselineManifest(TypedDict):
    schema_name: Literal['qc2.scientific_definitions.BaselineManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    baseline_kind: BaselineKind
    version: int
    algorithm: str
    parameter_refs: list[Reference_ConfigurationManifest]
    seed_hash: str | None
    comparator_role: ComparatorRole
    tie_break_rule: str

class ModelManifest(TypedDict):
    schema_name: Literal['qc2.models_prediction.ModelManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['model_registry']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    artifact_manifest_ref: Reference_ArtifactManifest
    safe_format: str
    algorithm: str
    algorithm_version: str
    target_label_refs: list[Reference_LabelDefinition]
    feature_registry_ref: Reference_FeatureRegistry
    ordered_feature_ids: list[str]
    protocol_registry_ref: Reference_RunnerProtocolRegistry
    training_start: str
    training_cutoff: str
    validation_window: str
    qualification_window: str
    dataset_ref: Reference_DatasetManifest
    split_ref: Reference_SplitManifest
    seed: int
    hyperparameter_refs: list[Reference_ConfigurationManifest | Reference_ArtifactManifest]
    calibration_ref: Reference_ArtifactManifest | None
    package_lock_hash: str
    environment_fingerprint: str
    learned_dependency_refs: list[Reference_RunnerGenome | Reference_FailureGenome | Reference_MemoryIndexManifest | Reference_ArtifactManifest | Reference_FeatureDefinition | Reference_DatasetManifest]
    resource_constraints: list[str]
    lifecycle_state: ModelLifecycle

class ModelHeadDefinition(TypedDict):
    schema_name: Literal['qc2.models_prediction.ModelHeadDefinition.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['model_registry']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    model_ref: Reference_ModelManifest
    head_name: str
    output_kind: ModelHeadKind
    label_ref: Reference_LabelDefinition
    horizon_sessions: int
    availability: HeadAvailability
    output_precision: int

class ModelHeadOutput(TypedDict):
    schema_name: Literal['qc2.models_prediction.ModelHeadOutput.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['inference']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    head_ref: Reference_ModelHeadDefinition
    instrument_ref: Reference_Instrument
    session_id: str
    output_value: str | None
    output_unit: str
    availability: HeadAvailability
    reason_code: str | None

class InferenceReceipt(TypedDict):
    schema_name: Literal['qc2.models_prediction.InferenceReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['inference']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    model_ref: Reference_ModelManifest
    loaded_artifact_hash: str
    generation: int
    environment_fingerprint: str
    probe_set_hash: str
    output_hash: str
    evaluated_at: str
    deterministic: bool

class PredictionRun(TypedDict):
    schema_name: Literal['qc2.models_prediction.PredictionRun.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['prediction']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    epoch_ref: Reference_ValidationEpoch
    session_id: str
    snapshot_ref: Reference_MarketSnapshot
    dependency_refs: list[Reference_CalendarManifest | Reference_FeatureRegistry | Reference_RunnerProtocolRegistry | Reference_LabelRegistry | Reference_ScoreManifest | Reference_ModelManifest | Reference_ChampionPointer | Reference_ShadowPredictionSet | Reference_BaselineManifest | Reference_MemoryIndexManifest]
    decision_deadline: str
    seal_deadline: str
    run_state: PredictionRunState
    generation: int

class Prediction(TypedDict):
    schema_name: Literal['qc2.models_prediction.Prediction.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['prediction']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    run_ref: Reference_PredictionRun
    session_id: str
    instrument_ref: Reference_Instrument
    reference_kind: PriceReference
    reference_price: str
    horizon_label_refs: list[Reference_LabelDefinition]
    head_output_refs: list[Reference_ModelHeadOutput]
    feature_snapshot_ref: Reference_FeatureSnapshot
    protocol_result_refs: list[Reference_RunnerProtocolResult]
    score_manifest_ref: Reference_ScoreManifest
    score: Score | None
    rank: int | None
    disposition: PredictionRowDisposition
    unscorable_reason: str | None
    model_ref: Reference_ModelManifest
    learned_memory_refs: list[Reference_RunnerGenome | Reference_FailureGenome | Reference_MemoryIndexManifest | Reference_MatchedDecoySet]
    epoch_ref: Reference_ValidationEpoch

class ScientificPredictionPayload(TypedDict):
    schema_name: Literal['qc2.models_prediction.ScientificPredictionPayload.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['prediction']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    session_id: str
    reference_kind: PriceReference
    reference_price: str
    instrument_ref: Reference_Instrument
    horizon_label_refs: list[Reference_LabelDefinition]
    head_output_refs: list[Reference_ModelHeadOutput]
    dependency_refs: list[Reference_FeatureSnapshot | Reference_RunnerProtocolResult | Reference_ScoreManifest | Reference_ModelManifest | Reference_MemoryIndexManifest | Reference_ValidationEpoch]
    score: Score
    rank: int
    disposition: PredictionRowDisposition
    model_hash: str
    epoch_ref: Reference_ValidationEpoch
    regime: str

class PredictionSeal(TypedDict):
    schema_name: Literal['qc2.models_prediction.PredictionSeal.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['prediction']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    run_ref: Reference_PredictionRun
    session_id: str
    role: PredictionRole
    ordered_prediction_refs: list[Reference_Prediction]
    disposition_counts: list[str]
    payload_inventory_hash: str
    deadline: str
    sealed_at: str
    evidence_refs: list[Reference_EvidenceEvent]

class RunDisposition(TypedDict):
    schema_name: Literal['qc2.models_prediction.RunDisposition.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['prediction']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    run_ref: Reference_PredictionRun
    instrument_ref: Reference_Instrument
    disposition: PredictionDisposition
    reason_code: str
    observed_at: str
    evidence_refs: list[Reference_EvidenceEvent]

class ShadowPredictionSet(TypedDict):
    schema_name: Literal['qc2.models_prediction.ShadowPredictionSet.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['prediction']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    model_ref: Reference_ModelManifest
    eligible_at: str
    target_label_refs: list[Reference_LabelDefinition]
    comparison_window_sessions: int
    comparator_refs: list[Reference_ModelManifest | Reference_BaselineManifest | Reference_ChampionPointer]
    registration_hash: str

class ReplayRequest(TypedDict):
    schema_name: Literal['qc2.models_prediction.ReplayRequest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    source_seal_ref: Reference_PredictionSeal
    requested_at: str
    environment_fingerprint: str
    reason_code: str
    replay_mode: ReplayMode

class ReplayReceipt(TypedDict):
    schema_name: Literal['qc2.models_prediction.ReplayReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    request_ref: Reference_ReplayRequest
    expected_hash: str
    actual_hash: str
    expected_count: int
    actual_count: int
    environment_fingerprint: str
    first_mismatch: str | None
    duration_ms: int
    verdict: ReplayVerdict

class Outcome(TypedDict):
    schema_name: Literal['qc2.outcomes_research.Outcome.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['ground_truth']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[Reference_DailyBar | Reference_CorporateActionRecord | Reference_MarketSnapshotRevision]
    content_hash: Sha256
    instrument_ref: Reference_Instrument
    session_id: str
    label_ref: Reference_LabelDefinition
    horizon_sessions: int
    reference_bar_ref: Reference_DailyBar
    reference_price: str
    next_open_bar_ref: Reference_DailyBar | None
    next_open_reference_price: str | None
    outcome_state: OutcomeState
    endpoint_return: ContinuousDecimal | None
    max_high_return: ContinuousDecimal | None
    min_low_return: ContinuousDecimal | None
    mfe: ContinuousDecimal | None
    mae: ContinuousDecimal | None
    max_high_price: str | None
    max_high_session: str | None
    max_high_session_offset: int | None
    min_low_price: str | None
    min_low_session: str | None
    min_low_session_offset: int | None
    extrema_tie_break: ExtremaTieBreak
    opening_gap_return: ContinuousDecimal | None
    next_open_proxy_endpoint_return: ContinuousDecimal | None
    next_open_proxy_max_high_return: ContinuousDecimal | None
    next_open_proxy_min_low_return: ContinuousDecimal | None
    next_open_proxy_mfe: ContinuousDecimal | None
    next_open_proxy_mae: ContinuousDecimal | None
    field_validity: list[OutcomeFieldValidityRecord]
    reason_codes: list[str]
    available_for_learning_at: str | None

class OutcomeRevision(TypedDict):
    schema_name: Literal['qc2.outcomes_research.OutcomeRevision.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['ground_truth']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[Reference_RawReceipt | Reference_DailyBar | Reference_CorporateActionRecord | Reference_EvidenceEvent | Reference_DataBundle]
    prior_outcome_ref: Reference_Outcome
    replacement_outcome_ref: Reference_Outcome
    revision_reason: str
    discovered_at: str
    correction_policy_ref: Reference_ConfigurationManifest

class RunnerEvent(TypedDict):
    schema_name: Literal['qc2.outcomes_research.RunnerEvent.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['ground_truth']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    instrument_ref: Reference_Instrument
    event_type: RunnerEventType
    start_session: str
    end_session: str | None
    label_ref: Reference_LabelDefinition
    outcome_ref: Reference_Outcome
    detected_at: str
    evidence_refs: list[Reference_EvidenceEvent | Reference_OutcomeRevision]

class RunnerGenome(TypedDict):
    schema_name: Literal['qc2.outcomes_research.RunnerGenome.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['apexlab']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    event_ref: Reference_RunnerEvent
    pre_event_snapshot_refs: list[Reference_MarketSnapshot | Reference_FeatureSnapshot]
    prediction_refs: list[Reference_Prediction]
    outcome_refs: list[Reference_Outcome]
    provenance_refs: list[Reference_EvidenceEvent | Reference_DataBundle | Reference_OutcomeRevision]
    curation_version: int
    event_time: str
    available_for_learning_at: str
    temporal_dependency_refs: list[Reference_MarketSnapshot | Reference_FeatureSnapshot | Reference_Prediction | Reference_Outcome | Reference_OutcomeRevision | Reference_EvidenceEvent]

class FailureGenome(TypedDict):
    schema_name: Literal['qc2.outcomes_research.FailureGenome.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['apexlab']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    event_ref: Reference_RunnerEvent
    failure_type: FailureType
    pre_event_snapshot_refs: list[Reference_MarketSnapshot | Reference_FeatureSnapshot]
    prediction_refs: list[Reference_Prediction]
    outcome_refs: list[Reference_Outcome]
    provenance_refs: list[Reference_EvidenceEvent | Reference_DataBundle | Reference_OutcomeRevision]
    curation_version: int
    event_time: str
    available_for_learning_at: str
    temporal_dependency_refs: list[Reference_MarketSnapshot | Reference_FeatureSnapshot | Reference_Prediction | Reference_Outcome | Reference_OutcomeRevision | Reference_EvidenceEvent]

class MemoryIndexManifest(TypedDict):
    schema_name: Literal['qc2.outcomes_research.MemoryIndexManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['apexlab']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    index_kind: MemoryIndexKind
    member_refs: list[Reference_RunnerGenome | Reference_FailureGenome | Reference_MatchedDecoySet]
    member_inventory_hash: str
    cutoff: str
    available_for_learning_at: str
    embedding_artifact_ref: Reference_ArtifactManifest | None

class MatchedDecoySet(TypedDict):
    schema_name: Literal['qc2.outcomes_research.MatchedDecoySet.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['apexlab']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    positive_event_refs: list[Reference_RunnerEvent]
    decoy_instrument_refs: list[Reference_Instrument]
    matching_procedure_hash: str
    pre_outcome_variable_ids: list[str]
    strata: list[str]
    calipers: list[str]
    unmatched_cases: list[str]
    outcome_membership_hash: str

class ReviewCase(TypedDict):
    schema_name: Literal['qc2.outcomes_research.ReviewCase.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['apexlab']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    review_kind: ReviewKind
    event_ref: Reference_RunnerEvent
    prediction_ref: Reference_Prediction | None
    disposition: PredictionDisposition
    reason_codes: list[str]
    reviewed_at: str
    evidence_refs: list[Reference_EvidenceEvent | Reference_Outcome | Reference_RunnerEvent]

class DatasetManifest(TypedDict):
    schema_name: Literal['qc2.outcomes_research.DatasetManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['apexlab']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    universe_fidelity: UniverseFidelity
    snapshot_refs: list[Reference_MarketSnapshot]
    raw_receipt_refs: list[Reference_RawReceipt]
    action_refs: list[Reference_CorporateActionRecord]
    registry_refs: list[Reference_FeatureRegistry | Reference_RunnerProtocolRegistry | Reference_LabelRegistry | Reference_ScoreManifest | Reference_BaselineManifest]
    memory_cutoff: str
    availability_policy: AvailabilityPolicy
    row_lineage_hash: str
    membership_hash: str
    time_start: str
    time_end: str
    symbol_count: int
    missingness_counts: list[str]
    revision_refs: list[Reference_MarketSnapshotRevision | Reference_OutcomeRevision]
    split_assignment_hash: str
    normalization_ref: Reference_AdjustmentManifest
    sampling_policy: str
    artifact_hash: str

class DatasetRowLineage(TypedDict):
    schema_name: Literal['qc2.outcomes_research.DatasetRowLineage.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['apexlab']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[Reference_MarketSnapshot | Reference_DailyBar | Reference_Outcome | Reference_FeatureSnapshot | Reference_Prediction | Reference_EvidenceEvent]
    content_hash: Sha256
    dataset_ref: Reference_DatasetManifest
    row_key: str
    instrument_ref: Reference_Instrument
    session_id: str
    horizon_sessions: int
    target_ref: Reference_LabelDefinition
    lineage_hash: str

class SplitManifest(TypedDict):
    schema_name: Literal['qc2.outcomes_research.SplitManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['apexlab']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    dataset_ref: Reference_DatasetManifest
    split_unit: SplitUnit
    training_intervals: list[str]
    validation_intervals: list[str]
    qualification_interval: str
    purge_sessions: int
    embargo_sessions: int
    cutoff_policy: str
    split_hash: str

class HoldoutAccessReceipt(TypedDict):
    schema_name: Literal['qc2.outcomes_research.HoldoutAccessReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    dataset_ref: Reference_DatasetManifest
    evaluator_identity: str
    access_scope: HoldoutAccessScope
    requested_at: str
    granted_at: str
    consumed_fields: list[str]
    released_metrics: list[str]
    receipt_hash: str

class Experiment(TypedDict):
    schema_name: Literal['qc2.outcomes_research.Experiment.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['apexlab']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    hypothesis: str
    search_space_hash: str
    code_hash: str
    environment_fingerprint: str
    dataset_ref: Reference_DatasetManifest
    split_ref: Reference_SplitManifest
    candidate_refs: list[Reference_ModelManifest]
    algorithm: str
    seed: int
    budget_ref: Reference_ConfigurationManifest
    compute_cost: str
    evaluation_access: list[str]
    result_ref: Reference_CandidateEvaluation | None
    rejection_reason: str | None
    artifact_refs: list[Reference_ArtifactManifest]

class CandidateEvaluation(TypedDict):
    schema_name: Literal['qc2.outcomes_research.CandidateEvaluation.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    candidate_ref: Reference_ModelManifest
    evaluator_identity: str
    dataset_ref: Reference_DatasetManifest
    split_ref: Reference_SplitManifest
    gate_results: list[GateResultRecord]
    evaluated_at: str
    verdict: EvaluationVerdict
    report_hash: str

class ChallengerEvaluation(TypedDict):
    schema_name: Literal['qc2.outcomes_research.ChallengerEvaluation.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    challenger_ref: Reference_ModelManifest
    reference_model_ref: Reference_ModelManifest
    evaluator_identity: str
    comparison_window: str
    gate_results: list[GateResultRecord]
    evaluated_at: str
    verdict: EvaluationVerdict
    report_hash: str

class DriftAssessment(TypedDict):
    schema_name: Literal['qc2.outcomes_research.DriftAssessment.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    model_ref: Reference_ModelManifest
    reference_window: str
    current_window: str
    metric_refs: list[Reference_MetricDefinition | Reference_MetricResult]
    threshold_policy_ref: Reference_ConfigurationManifest
    assessed_at: str
    status: DriftState
    evidence_refs: list[Reference_EvidenceEvent]

class ValidationEpoch(TypedDict):
    schema_name: Literal['qc2.validation.ValidationEpoch.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    epoch_key: str
    regime: str
    mode: OperatingMode
    epoch_state: EpochState
    start_session: str
    manifest_ref: Reference_EpochManifest | None
    champion_ref: Reference_ChampionPointer | None
    reference_model_ref: Reference_ModelManifest | None
    activated_at: str | None

class EpochManifest(TypedDict):
    schema_name: Literal['qc2.validation.EpochManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    epoch_key: str
    regime: str
    mode: OperatingMode
    calendar_ref: Reference_CalendarManifest
    universe_ref: Reference_UniverseManifest
    registry_refs: list[Reference_FeatureRegistry | Reference_RunnerProtocolRegistry | Reference_LabelRegistry | Reference_ScoreManifest | Reference_BaselineManifest]
    model_ref: Reference_ModelManifest
    reference_model_ref: Reference_ModelManifest
    strategy_ref: Reference_StrategyManifest
    effective_session: str

class ScheduledAttempt(TypedDict):
    schema_name: Literal['qc2.validation.ScheduledAttempt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    epoch_ref: Reference_ValidationEpoch
    session_id: str
    schedule_created_at: str
    expected_deadline: str
    attempt_state: ScheduledAttemptState
    run_ref: Reference_PredictionRun | None
    missed_reason: str | None

class ValidationSession(TypedDict):
    schema_name: Literal['qc2.validation.ValidationSession.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    epoch_ref: Reference_ValidationEpoch
    session_id: str
    qualification_ref: Reference_QualificationReceipt | None
    metric_result_refs: list[Reference_MetricResult]
    integrity_status: IntegrityVerdict
    sealed_at: str

class QualificationReceipt(TypedDict):
    schema_name: Literal['qc2.validation.QualificationReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    epoch_ref: Reference_ValidationEpoch
    session_id: str
    prediction_seal_ref: Reference_PredictionSeal
    prediction_integrity: IntegrityVerdict
    denominator_status: CoverageStatus
    on_time_seal: bool
    on_time_anchor: bool
    comparator_available: bool
    protocol_conformity: bool
    sealed_at: str
    checkpoint_ref: Reference_Checkpoint

class MetricDefinition(TypedDict):
    schema_name: Literal['qc2.validation.MetricDefinition.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    metric_key: str
    version: int
    estimand: str
    unit: str
    direction: MetricDirection
    missingness_policy: MissingnessPolicy
    tie_handling: str

class MetricResult(TypedDict):
    schema_name: Literal['qc2.validation.MetricResult.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    definition_ref: Reference_MetricDefinition
    epoch_ref: Reference_ValidationEpoch
    session_id: str | None
    value: ContinuousDecimal | None
    lower_bound: ContinuousDecimal | None
    upper_bound: ContinuousDecimal | None
    denominator: int
    missing_count: int
    computed_at: str

class StatisticalAnalysisPlan(TypedDict):
    schema_name: Literal['qc2.validation.StatisticalAnalysisPlan.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    epoch_ref: Reference_ValidationEpoch
    primary_metric_ref: Reference_MetricDefinition
    comparator_ref: Reference_BaselineManifest
    interval_method: str
    alpha: Probability
    practical_minimum_effect: ContinuousDecimal
    minimum_event_clusters: int
    minimum_effective_blocks: int
    resample_count: int
    missingness_method: str
    stopping_rule: str
    frozen_at: str

class ValidationReport(TypedDict):
    schema_name: Literal['qc2.validation.ValidationReport.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    epoch_ref: Reference_ValidationEpoch
    verdict: ValidationVerdict
    scheduled_attempt_refs: list[Reference_ScheduledAttempt]
    qualification_refs: list[Reference_QualificationReceipt]
    metric_refs: list[Reference_MetricResult | Reference_MetricDefinition]
    missingness_bounds: list[str]
    limitation_codes: list[str]
    report_hash: str
    sealed_at: str

class ReportAmendment(TypedDict):
    schema_name: Literal['qc2.validation.ReportAmendment.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    report_ref: Reference_ValidationReport
    revision_number: int
    reason: str
    impact_analysis: str
    correction_refs: list[Reference_OutcomeRevision | Reference_MarketSnapshotRevision]
    amendment_hash: str

class StrategyManifest(TypedDict):
    schema_name: Literal['qc2.execution.StrategyManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['strategy']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    strategy_key: str
    version: int
    selection_k: int
    rank_rule: str
    entry_window: str
    allocation_order: str
    price_cap_rule: str
    quantity_rounding: QuantityRounding
    stop_rule: str | None
    target_rule: str | None
    trailing_rule: str | None
    maximum_holding_sessions: int
    reentry_policy: str
    reservation_policy: str
    cancellation_policy: str
    gap_no_fill_policy: str
    competing_action_rule: str

class CapitalPolicy(TypedDict):
    schema_name: Literal['qc2.execution.CapitalPolicy.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['configuration']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    paper_starting_capital: str
    currency: str
    maximum_position_cost: str
    maximum_position_fraction: Probability
    maximum_gross_exposure: str
    cash_reserve: str
    maximum_concurrent_positions: int
    daily_loss_limit: str
    drawdown_response: str
    participation_limit: Probability
    external_activity_policy: str
    owner_approval_ref: Reference_OwnerCommandReceipt

class PaperOrderIntent(TypedDict):
    schema_name: Literal['qc2.execution.PaperOrderIntent.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    episode_ref: Reference_ExecutionEpisode
    paper_account_fingerprint: str
    action_kind: PaperAction
    source_ref: Reference_Prediction | Reference_Position | Reference_PaperOrderIntent
    instrument_ref: Reference_Instrument
    symbol_assignment_ref: Reference_SymbolAssignment
    side: OrderSide
    quantity_whole_shares: int
    limit_price: str | None
    stop_price: str | None
    order_type: OrderType
    time_in_force: TimeInForce
    session_restriction: SessionRestriction
    strategy_ref: Reference_StrategyManifest
    capital_policy_ref: Reference_CapitalPolicy
    predicted_session: str
    target_execution_session: str
    target_window: str
    expires_at: str
    reason_code: str
    safety_assessment_refs: list[Reference_ReadinessAssessment]
    reservation_ref: Reference_Reservation | None
    idempotency_key: str
    account_mode: AccountMode
    extended_hours: bool
    intent_state: IntentState

class IntentDecision(TypedDict):
    schema_name: Literal['qc2.execution.IntentDecision.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    intent_ref: Reference_PaperOrderIntent
    decision: IntentDecisionState
    reason_codes: list[str]
    readiness_ref: Reference_ReadinessAssessment
    policy_hash: str
    decided_at: str

class SubmissionAttempt(TypedDict):
    schema_name: Literal['qc2.execution.SubmissionAttempt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    intent_ref: Reference_PaperOrderIntent
    client_order_key: str
    normalized_request_hash: str
    attempt_number: int
    started_at: str
    outcome: SubmissionOutcome
    broker_order_ref: Reference_BrokerOrder | None
    evidence_ref: Reference_EvidenceEvent

class BrokerOrder(TypedDict):
    schema_name: Literal['qc2.execution.BrokerOrder.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    intent_ref: Reference_PaperOrderIntent
    paper_account_fingerprint: str
    client_order_key: str
    broker_order_id: str
    request_hash: str
    order_state: BrokerOrderState
    submitted_at: str
    updated_at: str
    filled_quantity: str
    remaining_quantity: str

class BrokerOrderEvent(TypedDict):
    schema_name: Literal['qc2.execution.BrokerOrderEvent.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    broker_order_ref: Reference_BrokerOrder
    provider_event_id: str
    event_type: BrokerOrderEventType
    event_sequence: int
    event_at: str
    received_at: str
    event_payload_hash: str

class Fill(TypedDict):
    schema_name: Literal['qc2.execution.Fill.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    broker_order_ref: Reference_BrokerOrder
    provider_fill_id: str
    instrument_ref: Reference_Instrument
    side: OrderSide
    quantity: str
    price: str
    currency: str
    filled_at: str
    received_at: str

class FillCorrection(TypedDict):
    schema_name: Literal['qc2.execution.FillCorrection.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    original_fill_ref: Reference_Fill
    correction_kind: FillCorrectionKind
    quantity_delta: str
    price_delta: str
    reason_code: str
    source_event_ref: Reference_BrokerOrderEvent
    corrected_at: str

class Position(TypedDict):
    schema_name: Literal['qc2.execution.Position.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    episode_ref: Reference_ExecutionEpisode
    instrument_ref: Reference_Instrument
    quantity: str
    average_cost: str
    currency: str
    as_of: str
    source_fill_refs: list[Reference_Fill]
    corporate_action_refs: list[Reference_CorporateActionRecord]
    reconciliation_status: ReconciliationStatus

class CashLedgerEntry(TypedDict):
    schema_name: Literal['qc2.execution.CashLedgerEntry.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    episode_ref: Reference_ExecutionEpisode
    entry_kind: CashEntryKind
    amount: str
    currency: str
    effective_at: str
    source_ref: Reference_PaperOrderIntent
    balance_after: str

class Reservation(TypedDict):
    schema_name: Literal['qc2.execution.Reservation.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    episode_ref: Reference_ExecutionEpisode
    intent_ref: Reference_PaperOrderIntent
    reservation_kind: ReservationKind
    instrument_ref: Reference_Instrument
    reserved_quantity: str
    reserved_cash: str
    currency: str
    state: ReservationState
    released_at: str | None

class ReconciliationReport(TypedDict):
    schema_name: Literal['qc2.execution.ReconciliationReport.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    episode_ref: Reference_ExecutionEpisode
    paper_account_fingerprint: str
    reconciled_at: str
    broker_order_refs: list[Reference_BrokerOrder]
    position_refs: list[Reference_Position]
    discrepancies: list[str]
    status: ReconciliationStatus
    evidence_ref: Reference_EvidenceEvent

class ExecutionEpisode(TypedDict):
    schema_name: Literal['qc2.execution.ExecutionEpisode.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['execution']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    paper_account_fingerprint: str
    account_mode: AccountMode
    opened_at: str
    opening_cash: str
    currency: str
    opening_position_refs: list[Reference_Position]
    opening_order_refs: list[Reference_BrokerOrder]
    strategy_ref: Reference_StrategyManifest
    capital_policy_ref: Reference_CapitalPolicy
    sealed_at: str
    episode_hash: str

class PromotionPolicy(TypedDict):
    schema_name: Literal['qc2.governance_owner.PromotionPolicy.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['promotion']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    policy_key: str
    version: int
    prospective_sessions: int
    minimum_events: int
    uncertainty_requirements: list[str]
    calibration_bounds: list[str]
    coverage_limits: list[str]
    stability_limits: list[str]
    regression_gates: list[str]
    maximum_attempts: int
    cooldown_sessions: int
    permitted_artifact_types: list[str]
    compatibility_envelope: list[str]
    epoch_modes: list[str]
    frozen_at: str

class PromotionBundleManifest(TypedDict):
    schema_name: Literal['qc2.governance_owner.PromotionBundleManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['promotion']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    candidate_model_ref: Reference_ModelManifest
    prior_champion_ref: Reference_ChampionPointer | None
    epoch_ref: Reference_ValidationEpoch
    mode: OperatingMode
    registry_refs: list[Reference_FeatureRegistry | Reference_RunnerProtocolRegistry | Reference_LabelRegistry | Reference_ScoreManifest | Reference_BaselineManifest]
    dataset_ref: Reference_DatasetManifest
    split_ref: Reference_SplitManifest
    holdout_receipt_refs: list[Reference_HoldoutAccessReceipt]
    replay_report_ref: Reference_ReplayReceipt
    evaluation_refs: list[Reference_CandidateEvaluation | Reference_ChallengerEvaluation | Reference_ValidationReport]
    shadow_seal_refs: list[Reference_PredictionSeal]
    policy_ref: Reference_PromotionPolicy
    gate_results: list[GateResultRecord]
    environment_fingerprint: str
    expires_at: str
    transition_intent: str
    inventory_hash: str

class PromotionRequest(TypedDict):
    schema_name: Literal['qc2.governance_owner.PromotionRequest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['promotion']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    bundle_ref: Reference_PromotionBundleManifest
    candidate_model_ref: Reference_ModelManifest
    expected_champion_ref: Reference_ChampionPointer | None
    epoch_ref: Reference_ValidationEpoch
    requested_at: str
    expires_at: str
    request_state: PromotionRequestState
    request_hash: str

class PromotionChallenge(TypedDict):
    schema_name: Literal['qc2.governance_owner.PromotionChallenge.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['promotion']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    request_ref: Reference_PromotionRequest
    bundle_hash: str
    candidate_hash: str
    expected_champion_hash: str | None
    expected_generation: int
    epoch_ref: Reference_ValidationEpoch
    registry_refs: list[Reference_FeatureRegistry | Reference_RunnerProtocolRegistry | Reference_LabelRegistry | Reference_ScoreManifest | Reference_BaselineManifest]
    policy_ref: Reference_PromotionPolicy
    nonce: str
    issued_at: str
    expires_at: str
    device_ref: Reference_OwnerDevice
    key_id: str

class PromotionDecision(TypedDict):
    schema_name: Literal['qc2.governance_owner.PromotionDecision.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['promotion']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    challenge_ref: Reference_PromotionChallenge
    decision: OwnerDecision
    signed_by_device_ref: Reference_OwnerDevice
    key_id: str
    signature: str
    signed_at: str
    request_hash: str

class PromotionReceipt(TypedDict):
    schema_name: Literal['qc2.governance_owner.PromotionReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['promotion']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    request_ref: Reference_PromotionRequest
    decision_ref: Reference_PromotionDecision
    transition_state: PromotionReceiptState
    prior_generation: int
    new_generation: int
    committed_at: str
    evidence_ref: Reference_EvidenceEvent
    pointer_hash: str | None

class ChampionPointer(TypedDict):
    schema_name: Literal['qc2.governance_owner.ChampionPointer.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['promotion']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    epoch_ref: Reference_ValidationEpoch
    role: ChampionRole
    model_ref: Reference_ModelManifest
    generation: int
    transitioned_at: str
    transition_receipt_ref: Reference_PromotionReceipt
    pointer_hash: str

class EpochActivationChallenge(TypedDict):
    schema_name: Literal['qc2.governance_owner.EpochActivationChallenge.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    epoch_manifest_ref: Reference_EpochManifest
    prospective_start_session: str
    account_identity_hash: str
    strategy_hash: str
    nonce: str
    issued_at: str
    expires_at: str
    device_ref: Reference_OwnerDevice
    key_id: str

class EpochActivationDecision(TypedDict):
    schema_name: Literal['qc2.governance_owner.EpochActivationDecision.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    challenge_ref: Reference_EpochActivationChallenge
    epoch_manifest_hash: str
    decision: EpochActivationChoice
    device_ref: Reference_OwnerDevice
    key_id: str
    signature: str
    signed_at: str

class EpochActivationReceipt(TypedDict):
    schema_name: Literal['qc2.governance_owner.EpochActivationReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['validation']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    decision_ref: Reference_EpochActivationDecision
    epoch_ref: Reference_ValidationEpoch
    epoch_manifest_hash: str
    start_session: str
    activation_state: ActivationState
    gate_results: list[GateResultRecord]
    activated_at: str
    evidence_ref: Reference_EvidenceEvent

class OwnerDevice(TypedDict):
    schema_name: Literal['qc2.governance_owner.OwnerDevice.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['identity']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    owner_key_id: str
    public_key: str
    signing_algorithm: SigningAlgorithm
    security_level: DeviceSecurityLevel
    enrollment_proof_hash: str
    owner_binding: str
    app_version: str
    revocation_state: DeviceRevocationState
    enrolled_at: str
    revoked_at: str | None

class OwnerSession(TypedDict):
    schema_name: Literal['qc2.governance_owner.OwnerSession.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['identity']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    device_ref: Reference_OwnerDevice
    session_id: str
    issued_at: str
    expires_at: str
    revoked_at: str | None
    scope_refs: list[str]
    refresh_generation: int

class EnrollmentChallenge(TypedDict):
    schema_name: Literal['qc2.governance_owner.EnrollmentChallenge.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['identity']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    owner_binding: str
    bootstrap_verifier_hash: str
    nonce: str
    issued_at: str
    expires_at: str
    single_use: bool
    consumed_at: str | None

class RecoveryEvent(TypedDict):
    schema_name: Literal['qc2.governance_owner.RecoveryEvent.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['identity']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    event_kind: RecoveryEventKind
    prior_device_refs: list[Reference_OwnerDevice]
    replacement_device_ref: Reference_OwnerDevice | None
    effective_at: str
    promotion_hold: bool
    entry_hold: bool
    reconciliation_required: bool
    evidence_ref: Reference_EvidenceEvent

class OwnerCommand(TypedDict):
    schema_name: Literal['qc2.governance_owner.OwnerCommand.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['owner_api']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    command_id: str
    command_type: OwnerCommandType
    idempotency_key: str
    request_body_hash: str
    issued_at: str
    device_ref: Reference_OwnerDevice
    signature: str
    scope: OwnerCommandScope

class OwnerCommandReceipt(TypedDict):
    schema_name: Literal['qc2.governance_owner.OwnerCommandReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['owner_api']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    command_ref: Reference_OwnerCommand
    state: OwnerCommandReceiptState
    resulting_evidence_ref: Reference_EvidenceEvent | None
    source_sequence: int
    projection_lag_ms: int
    received_at: str

class Alert(TypedDict):
    schema_name: Literal['qc2.governance_owner.Alert.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['alert']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    alert_type: str
    severity: AlertSeverity
    trigger_rule: str
    dedupe_key: str
    escalation_policy: str
    action_owner: str
    auto_resolution_condition: str
    readiness_effect: bool
    acknowledged_at: str | None
    resolved_at: str | None
    evidence_refs: list[Reference_EvidenceEvent]

class EvidenceEvent(TypedDict):
    schema_name: Literal['qc2.integrity_build.EvidenceEvent.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['evidence']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    installation_id: str
    stream_id: str
    sequence: int
    event_type: str
    actor_identity: str
    authorized_command_ref: Reference_OwnerCommand | None
    correlation_id: str
    payload_hash: str
    dependency_refs: list[Reference_ArtifactManifest | Reference_Checkpoint | Reference_AnchorReceipt]
    previous_event_hash: str | None
    event_hash: str
    wall_clock_at: str
    monotonic_generation: int

class Checkpoint(TypedDict):
    schema_name: Literal['qc2.integrity_build.Checkpoint.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['evidence']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    stream_id: str
    head_sequence: int
    head_hash: str
    event_count: int
    artifact_root_hash: str
    checkpoint_hash: str

class AnchorReceipt(TypedDict):
    schema_name: Literal['qc2.integrity_build.AnchorReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['evidence']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    checkpoint_ref: Reference_Checkpoint
    anchor_provider: str
    external_receipt_id: str
    accepted_at: str
    observed_at: str
    verification_key_id: str
    signature: str
    proof_level: ProofLevel

class ArtifactManifest(TypedDict):
    schema_name: Literal['qc2.integrity_build.ArtifactManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['model_registry']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    manifest_version: int
    files: list[ArtifactFileRecord]
    inventory_hash: str
    detached_signature: str | None
    transport_hash: str | None

class ArtifactDependency(TypedDict):
    schema_name: Literal['qc2.integrity_build.ArtifactDependency.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['model_registry']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    parent_ref: Reference_ArtifactManifest
    dependency_ref: Reference_ArtifactManifest
    dependency_role: str
    required_for_retention: bool
    discovered_at: str

class BackupManifest(TypedDict):
    schema_name: Literal['qc2.integrity_build.BackupManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['evidence']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    recovery_point_at: str
    database_snapshot_ref: Reference_ArtifactManifest
    artifact_inventory_refs: list[Reference_ArtifactManifest | Reference_DataBundle | Reference_DatasetManifest | Reference_ModelManifest | Reference_PredictionSeal]
    configuration_refs: list[Reference_ConfigurationManifest]
    key_inventory_hash: str
    evidence_root_ref: Reference_Checkpoint
    anchor_receipt_refs: list[Reference_AnchorReceipt]
    encryption_key_id: str
    inventory_hash: str

class RestoreReceipt(TypedDict):
    schema_name: Literal['qc2.integrity_build.RestoreReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['evidence']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    backup_ref: Reference_BackupManifest
    recovery_generation: int
    restored_at: str
    evidence_verdict: IntegrityVerdict
    artifact_inventory_verdict: IntegrityVerdict
    reconciliation_ref: Reference_ReconciliationReport | None
    outbound_orders_disabled: bool
    receipt_hash: str

class ConfigurationManifest(TypedDict):
    schema_name: Literal['qc2.integrity_build.ConfigurationManifest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['configuration']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    configuration_domain: ConfigurationDomain
    version: int
    effective_from: str
    setting_refs: list[str]
    policy_hash: str
    unresolved_decision_refs: list[Reference_UnknownDecision]
    fixture_only: bool
    signed_by_owner: bool

class UnknownDecision(TypedDict):
    schema_name: Literal['qc2.integrity_build.UnknownDecision.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['configuration']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    decision_key: str
    decision_class: UnknownDecisionClass
    reason: str
    affected_contract_refs: list[Reference_ConfigurationManifest | Reference_OwnerCommandReceipt | Reference_ValidationReport | Reference_EvidenceEvent | Reference_ArtifactManifest | Reference_BuildTask]
    responsible_authority: str
    evidence_needed: str
    activation_consequence: str
    decision_state: UnknownDecisionState
    resolved_by: Reference_OwnerCommandReceipt | None

class ChangeRequest(TypedDict):
    schema_name: Literal['qc2.integrity_build.ChangeRequest.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['build_governance']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    change_class: ChangeClass
    requirements_changed: list[str]
    reason: str
    impact_analysis: str
    migration_plan: str
    test_refs: list[str]
    effective_boundary: str
    owner_approval_ref: Reference_OwnerCommandReceipt | None
    status: ChangeRequestState

class ReferenceIntake(TypedDict):
    schema_name: Literal['qc2.integrity_build.ReferenceIntake.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['build_governance']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    repository_identity: str
    revision: str
    file_path: str
    file_sha256: str
    inspected_symbol: str
    relevant_test_refs: list[str]
    reason_for_inspection: str
    source_supported_meaning: str
    useful_concepts: list[str]
    conflicts: list[str]
    license: str
    provenance_limits: str
    disposition: ReferenceDisposition

class BuildTask(TypedDict):
    schema_name: Literal['qc2.integrity_build.BuildTask.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['build_governance']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    task_id: str
    task_name: str
    objective: str
    dependency_task_ids: list[str]
    authorized_legacy_refs: list[str]
    deliverable_refs: list[str]
    required_test_refs: list[str]
    acceptance_gate: str
    evidence_requirement: str
    calibration_dependency: CalibrationDependency
    task_state: BuildTaskState
    blocker_refs: list[str]

class TaskAcceptanceReceipt(TypedDict):
    schema_name: Literal['qc2.integrity_build.TaskAcceptanceReceipt.v1']
    schema_version: Literal['1.0']
    id: UuidV7
    created_at: UtcInstant
    owning_authority: Literal['build_governance']
    evidence_class: EvidenceClass
    environment_namespace: EnvironmentNamespace
    source_refs: list[ForeignReference]
    content_hash: Sha256
    task_ref: Reference_BuildTask
    task_spec_version: str
    source_commit: str
    changed_paths: list[str]
    executed_commands: list[str]
    test_counts: list[TestCountRecord]
    artifact_hashes: list[str]
    legacy_intake_refs: list[Reference_ReferenceIntake]
    unresolved_decisions: list[str]
    gate_verdict: BuildGateVerdict
    agent_identity: str
    reviewer_identity: str | None
    checked_at: str

__all__ = ['EvidenceClass', 'EnvironmentNamespace', 'MarketPhase', 'ClockStatus', 'JobState', 'JobAttemptState', 'OutboxState', 'ReadinessAction', 'ReadinessStatus', 'IdentityStatus', 'InstrumentClass', 'CorporateActionType', 'ActionUncertainty', 'MarketFeed', 'AdjustmentMode', 'BarTimeframe', 'BarStatus', 'DataCapability', 'CapabilityResult', 'CompletenessState', 'QuarantineDisposition', 'MissingnessPolicy', 'ZeroDenominatorPolicy', 'SignalDirection', 'RunnerProtocolResultState', 'SafetyResultState', 'MissingnessStatus', 'FeatureMissingReason', 'OutcomeFieldStatus', 'GateStatus', 'WarningPolicy', 'PriceReference', 'LabelTarget', 'MissingHeadPolicy', 'BaselineKind', 'ComparatorRole', 'ModelHeadKind', 'HeadAvailability', 'ModelLifecycle', 'PredictionRunState', 'PredictionDisposition', 'PredictionRowDisposition', 'ExtremaTieBreak', 'PredictionRole', 'ReplayMode', 'ReplayVerdict', 'OutcomeState', 'RunnerEventType', 'FailureType', 'MemoryIndexKind', 'ReviewKind', 'UniverseFidelity', 'AvailabilityPolicy', 'SplitUnit', 'HoldoutAccessScope', 'EvaluationVerdict', 'DriftState', 'OperatingMode', 'EpochState', 'ScheduledAttemptState', 'IntegrityVerdict', 'CoverageStatus', 'MetricDirection', 'ValidationVerdict', 'QuantityRounding', 'PaperAction', 'OrderSide', 'OrderType', 'TimeInForce', 'SessionRestriction', 'AccountMode', 'IntentState', 'IntentDecisionState', 'SubmissionOutcome', 'BrokerOrderState', 'BrokerOrderEventType', 'FillCorrectionKind', 'ReconciliationStatus', 'CashEntryKind', 'ReservationKind', 'ReservationState', 'PromotionRequestState', 'OwnerDecision', 'PromotionReceiptState', 'ChampionRole', 'EpochActivationChoice', 'ActivationState', 'SigningAlgorithm', 'DeviceSecurityLevel', 'DeviceRevocationState', 'RecoveryEventKind', 'OwnerCommandType', 'OwnerCommandScope', 'OwnerCommandReceiptState', 'AlertSeverity', 'ProofLevel', 'ConfigurationDomain', 'UnknownDecisionClass', 'UnknownDecisionState', 'ChangeClass', 'ChangeRequestState', 'ReferenceDisposition', 'CalibrationDependency', 'BuildTaskState', 'BuildGateVerdict', 'TimezoneId', 'CalendarManifest', 'CalendarRevision', 'MarketSession', 'ClockAssessment', 'JobDefinition', 'JobLease', 'JobAttempt', 'OutboxMessage', 'ReadinessAssessment', 'DeploymentCapabilityManifest', 'Instrument', 'SymbolAssignment', 'InstrumentClassification', 'CorporateActionRecord', 'AdjustmentManifest', 'CandidateCensus', 'DailyBar', 'RawReceipt', 'RequestManifest', 'DataCapabilityManifest', 'BarSemanticsManifest', 'DataBundle', 'UniverseManifest', 'MarketSnapshot', 'MarketSnapshotRevision', 'QuarantineCase', 'FeatureDefinition', 'FeatureRegistry', 'FeatureSnapshot', 'RunnerProtocolDefinition', 'RunnerProtocolRegistry', 'RunnerProtocolResult', 'SafetyProtocolDefinition', 'SafetyProtocolResult', 'LabelDefinition', 'LabelRegistry', 'ScoreDefinition', 'ScoreManifest', 'BaselineManifest', 'ModelManifest', 'ModelHeadDefinition', 'ModelHeadOutput', 'InferenceReceipt', 'PredictionRun', 'Prediction', 'ScientificPredictionPayload', 'PredictionSeal', 'RunDisposition', 'ShadowPredictionSet', 'ReplayRequest', 'ReplayReceipt', 'Outcome', 'OutcomeRevision', 'RunnerEvent', 'RunnerGenome', 'FailureGenome', 'MemoryIndexManifest', 'MatchedDecoySet', 'ReviewCase', 'DatasetManifest', 'DatasetRowLineage', 'SplitManifest', 'HoldoutAccessReceipt', 'Experiment', 'CandidateEvaluation', 'ChallengerEvaluation', 'DriftAssessment', 'ValidationEpoch', 'EpochManifest', 'ScheduledAttempt', 'ValidationSession', 'QualificationReceipt', 'MetricDefinition', 'MetricResult', 'StatisticalAnalysisPlan', 'ValidationReport', 'ReportAmendment', 'StrategyManifest', 'CapitalPolicy', 'PaperOrderIntent', 'IntentDecision', 'SubmissionAttempt', 'BrokerOrder', 'BrokerOrderEvent', 'Fill', 'FillCorrection', 'Position', 'CashLedgerEntry', 'Reservation', 'ReconciliationReport', 'ExecutionEpisode', 'PromotionPolicy', 'PromotionBundleManifest', 'PromotionRequest', 'PromotionChallenge', 'PromotionDecision', 'PromotionReceipt', 'ChampionPointer', 'EpochActivationChallenge', 'EpochActivationDecision', 'EpochActivationReceipt', 'OwnerDevice', 'OwnerSession', 'EnrollmentChallenge', 'RecoveryEvent', 'OwnerCommand', 'OwnerCommandReceipt', 'Alert', 'EvidenceEvent', 'Checkpoint', 'AnchorReceipt', 'ArtifactManifest', 'ArtifactDependency', 'BackupManifest', 'RestoreReceipt', 'ConfigurationManifest', 'UnknownDecision', 'ChangeRequest', 'ReferenceIntake', 'BuildTask', 'TaskAcceptanceReceipt']
