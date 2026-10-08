"""Session-grouped temporal split checks for QC2 qualification datasets."""

from __future__ import annotations

from collections.abc import Sequence

from .models import (
    SplitRow,
    SplitValidation,
    ValidationAuthorityError,
    session_date,
    unique_session_ids,
    utc_instant,
)


def validate_temporal_split(
    *,
    session_order: Sequence[str],
    rows: Sequence[SplitRow],
    training_sessions: Sequence[str],
    validation_sessions: Sequence[str],
    qualification_sessions: Sequence[str],
    purged_sessions: Sequence[str],
    embargo_sessions: Sequence[str],
    training_cutoff_at: str,
    validation_cutoff_at: str,
) -> SplitValidation:
    """Validate chronology, session grouping, purge gaps, and label availability.

    `session_order` is supplied by the pinned exchange calendar. Calendar dates
    are not substituted for exchange-session distance.
    """
    ordered_calendar = unique_session_ids(session_order, "session_order")
    calendar_index = {session: index for index, session in enumerate(ordered_calendar)}
    train = unique_session_ids(training_sessions, "training_sessions")
    validation = unique_session_ids(validation_sessions, "validation_sessions")
    qualification = unique_session_ids(qualification_sessions, "qualification_sessions")
    purged = tuple(
        sorted(set(unique_session_ids(purged_sessions, "purged_sessions", allow_empty=True)))
    )
    embargoed = tuple(
        sorted(set(unique_session_ids(embargo_sessions, "embargo_sessions", allow_empty=True)))
    )

    stage_sets = {
        "TRAINING": set(train),
        "VALIDATION": set(validation),
        "QUALIFICATION": set(qualification),
    }
    if not train or not validation or not qualification:
        raise ValidationAuthorityError("training, validation, and qualification splits are required")
    if any(not sessions <= set(ordered_calendar) for sessions in stage_sets.values()):
        raise ValidationAuthorityError("split references a session outside the pinned calendar")
    if any(stage_sets[left] & stage_sets[right] for left, right in (
        ("TRAINING", "VALIDATION"),
        ("TRAINING", "QUALIFICATION"),
        ("VALIDATION", "QUALIFICATION"),
    )):
        raise ValidationAuthorityError("training, validation, and qualification overlap")
    if stage_sets["TRAINING"] & (set(purged) | set(embargoed)):
        raise ValidationAuthorityError("training rows cannot occupy purge or embargo sessions")
    if stage_sets["VALIDATION"] & (set(purged) | set(embargoed)):
        raise ValidationAuthorityError("validation rows cannot occupy purge or embargo sessions")
    if stage_sets["QUALIFICATION"] & (set(purged) | set(embargoed)):
        raise ValidationAuthorityError("qualification rows cannot occupy purge or embargo sessions")

    ordered_stages = [
        min(calendar_index[item] for item in train),
        max(calendar_index[item] for item in train),
        min(calendar_index[item] for item in validation),
        max(calendar_index[item] for item in validation),
        min(calendar_index[item] for item in qualification),
        max(calendar_index[item] for item in qualification),
    ]
    if not (
        ordered_stages[0] <= ordered_stages[1] < ordered_stages[2]
        <= ordered_stages[3] < ordered_stages[4] <= ordered_stages[5]
    ):
        raise ValidationAuthorityError(
            "outer split stages must be chronological in exchange-session order"
        )

    training_cutoff = utc_instant(training_cutoff_at, "training_cutoff_at")
    validation_cutoff = utc_instant(validation_cutoff_at, "validation_cutoff_at")
    if validation_cutoff <= training_cutoff:
        raise ValidationAuthorityError("validation cutoff must follow the training cutoff")

    gap_sessions = set(ordered_calendar) - (
        stage_sets["TRAINING"] | stage_sets["VALIDATION"] | stage_sets["QUALIFICATION"]
    )
    if not (set(purged) | set(embargoed)) <= gap_sessions:
        raise ValidationAuthorityError("purge and embargo sessions must be excluded from all splits")

    row_ids: set[str] = set()
    session_stages: dict[str, str] = {}
    training_boundary = min(calendar_index[item] for item in validation)
    qualification_boundary = min(calendar_index[item] for item in qualification)
    for row in rows:
        if not row.row_id or row.row_id in row_ids:
            raise ValidationAuthorityError("split rows require unique non-empty row IDs")
        row_ids.add(row.row_id)
        session_date(row.session_id, "row.session_id")
        session_date(row.dependency_end_session, "row.dependency_end_session")
        if row.session_id not in calendar_index or row.dependency_end_session not in calendar_index:
            raise ValidationAuthorityError("row dates must belong to the pinned exchange calendar")
        if row.stage not in stage_sets or row.session_id not in stage_sets[row.stage]:
            raise ValidationAuthorityError("all rows from a session must remain in its declared split")
        previous_stage = session_stages.setdefault(row.session_id, row.stage)
        if previous_stage != row.stage:
            raise ValidationAuthorityError("symbols from one session cannot cross split stages")
        available_at = utc_instant(row.available_for_learning_at, "available_for_learning_at")
        dependency_end = calendar_index[row.dependency_end_session]
        row_index = calendar_index[row.session_id]
        if dependency_end < row_index:
            raise ValidationAuthorityError("label dependency end cannot precede its source session")
        if row.stage == "TRAINING":
            if dependency_end >= training_boundary:
                raise ValidationAuthorityError("training labels overlap the validation boundary")
            if available_at >= training_cutoff:
                raise ValidationAuthorityError("training labels were unavailable at the training cutoff")
        elif row.stage == "VALIDATION":
            if dependency_end >= qualification_boundary:
                raise ValidationAuthorityError("validation labels overlap the qualification boundary")
            if available_at >= validation_cutoff:
                raise ValidationAuthorityError(
                    "validation labels were unavailable at the simulated fold cutoff"
                )

    return SplitValidation(
        training_sessions=train,
        validation_sessions=validation,
        qualification_sessions=qualification,
        purged_sessions=purged,
        embargo_sessions=embargoed,
    )
