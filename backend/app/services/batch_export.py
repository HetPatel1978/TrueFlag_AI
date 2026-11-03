"""Bounded authorized spreadsheet-safe CSV; never exports predictors or original source IDs."""

import csv
import hashlib
import io

from sqlalchemy.orm import Session

from app.services.batch_assessments import event
from app.services.csv_staging import _now, _timeouts

EXPORT_SCHEMA = "trueflag.batch-results.v1"
EXPORT_FIELDS = (
    "case_id",
    "source_row_number",
    "outcome",
    "policy",
    "sar_positive_score",
    "recommendation",
    "override_reason",
    "assessment_id",
    "job_id",
    "retrying",
    "reason_code",
    "model_version",
    "model_sha256",
    "policy_version",
    "policy_sha256",
    "human_decision_required",
)


class ExportLimit(Exception):
    pass


def safe_cell(value):
    text = "" if value is None else str(value)
    # Quoting alone does not stop spreadsheet formulas. Guard whitespace/BOM prefixes too.
    visible = text.lstrip("\ufeff \t\r\n\v\f")
    if text.startswith(("\t", "\r", "\n")) or visible.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def export_results(service, actor_id, batch_id, offset, limit):
    if (
        type(offset) is not int
        or not 0 <= offset <= 10000
        or type(limit) is not int
        or not 1 <= limit <= service.settings.batch_export_max_rows
    ):
        raise ExportLimit
    # Buffer one bounded range before returning any bytes; permission/audit failure releases none.
    with Session(service.engine) as session, session.begin():
        _timeouts(session)
        batch = service._authorized(session, actor_id, batch_id)
        counts = service._finish(session, batch)
        output = io.StringIO(newline="")
        writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        output.write("\ufeff")
        writer.writerow(EXPORT_FIELDS)
        size, returned = len(output.getvalue().encode("utf-8")), 0
        row_buffer = io.StringIO(newline="")
        row_writer = csv.writer(row_buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        for row in service._results_in_session(session, batch, offset, limit):
            assessment = row["assessment"]
            fields = {
                "case_id": row["case_id"],
                "source_row_number": row["source_row_number"],
                "outcome": row["outcome"],
                "policy": batch.policy,
                "sar_positive_score": assessment.score if assessment else None,
                "recommendation": assessment.recommended_route if assessment else None,
                "override_reason": assessment.policy_trace.override_reason if assessment else None,
                "assessment_id": assessment.assessment_id if assessment else None,
                "job_id": row["job_id"],
                "retrying": row["retrying"],
                "reason_code": row["reason_code"],
                "model_version": batch.model_version,
                "model_sha256": batch.model_sha256,
                "policy_version": batch.policy_version,
                "policy_sha256": batch.policy_sha256,
                "human_decision_required": True,
            }
            row_buffer.seek(0)
            row_buffer.truncate()
            row_writer.writerow([safe_cell(fields[name]) for name in EXPORT_FIELDS])
            chunk = row_buffer.getvalue()
            size += len(chunk.encode("utf-8"))
            if size > service.settings.batch_export_max_bytes:
                raise ExportLimit
            output.write(chunk)
            returned += 1
        payload = output.getvalue().encode("utf-8")
        if len(payload) > service.settings.batch_export_max_bytes:
            raise ExportLimit
        event(
            session,
            batch,
            "exported",
            export_schema=EXPORT_SCHEMA,
            offset=offset,
            requested_limit=limit,
            returned=returned,
            total=counts["total_cases"],
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            exported_at=_now(session).isoformat(),
        )
        session.flush()
        return payload, counts["total_cases"], returned
