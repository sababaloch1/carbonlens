"""S4 - Recommendations: generation (AI + rules), listing and status workflow.

FR-4.03 rule-based, FR-4.04 AI-tailored, FR-4.05 de-duplicated & ranked,
FR-4.06 list/filter, FR-4.07 status lifecycle (audited, NFR-4.10).
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from api.app.core.enums import AuditAction, RecSource, RecStatus, Scope
from api.app.core.models import Department, Recommendation, User
from api.app.data_identity.services import audit_service

from ..config import get_settings
from ..footprint import FootprintService, FootprintSummary
from ..llm import LLMClient, LLMError
from ..prompts import RECOMMENDATIONS_SYSTEM, wrap_data
from ..rules import generate_rule_recommendations
from ..schemas import AIRecommendationItem, GenerateResponse, GenerationMode, RecommendationOut

logger = logging.getLogger("carbonlens.coach")

# Allowed status transitions (FR-4.07)
TRANSITIONS: dict[RecStatus, set[RecStatus]] = {
    RecStatus.proposed: {RecStatus.accepted, RecStatus.dismissed},
    RecStatus.accepted: {RecStatus.completed, RecStatus.dismissed},
    RecStatus.dismissed: {RecStatus.proposed},
    RecStatus.completed: set(),
}


def _norm(title: str) -> str:
    return " ".join(title.lower().split())


def _ai_recommendations(
    llm: LLMClient, summary: FootprintSummary, existing_titles: list[str], dept_names: dict[str, UUID],
) -> list[tuple[AIRecommendationItem, UUID | None]]:
    s = get_settings()
    system = RECOMMENDATIONS_SYSTEM.format(max_items=s.max_ai_recommendations)
    payload = {
        "footprint": summary.to_prompt_context(),
        "existing_recommendations": existing_titles[:30],
    }
    data, _usage = llm.complete_json(system, wrap_data(payload), s.max_tokens_recs)
    raw_items = data.get("recommendations")
    if not isinstance(raw_items, list):
        raise LLMError("Model response has no 'recommendations' list")

    valid: list[tuple[AIRecommendationItem, UUID | None]] = []
    for raw in raw_items[: s.max_ai_recommendations]:
        try:
            item = AIRecommendationItem.model_validate(raw)
        except ValidationError:
            logger.info("Dropped invalid AI recommendation")  # NFR-4.05
            continue
        # Plausibility: a measure can't save more than its category (or the whole footprint) emits.
        cap = summary.category_t(item.category) if item.category else summary.total_t_co2e
        if cap <= 0:
            continue  # refers to a category the company does not have
        item.est_saving_t_co2e = round(min(item.est_saving_t_co2e, cap), 2)
        dept_id = dept_names.get(_norm(item.department)) if item.department else None
        valid.append((item, dept_id))
    if not valid:
        raise LLMError("Model returned no usable recommendations")
    return valid


def generate(db: Session, user: User, llm: LLMClient | None, mode: GenerationMode) -> GenerateResponse:
    summary = FootprintService(db).build(user.org_id)
    if not summary.has_data:
        return GenerateResponse(created=[], warning="No calculated emissions yet. Add activity records first.")

    existing = db.query(Recommendation).filter(Recommendation.org_id == user.org_id).all()
    seen = {_norm(r.title) for r in existing if r.title}

    if mode == GenerationMode.ai and llm is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI is not configured (OPENAI_API_KEY missing)")

    candidates: list[dict] = []
    source = RecSource.rules
    warning = None

    if mode in (GenerationMode.auto, GenerationMode.ai) and llm is not None:
        dept_names = {
            _norm(d.name): d.id
            for d in db.query(Department).filter(Department.org_id == user.org_id).all()
        }
        try:
            for item, dept_id in _ai_recommendations(llm, summary, [r.title for r in existing if r.title], dept_names):
                desc = item.description + (f"\n\nWhy: {item.reasoning}" if item.reasoning else "")
                candidates.append(dict(
                    title=item.title, description=desc, est_saving_t_co2e=item.est_saving_t_co2e,
                    cost_level=item.cost_level, effort=item.effort, scope=item.scope,
                    department_id=dept_id,
                ))
            source = RecSource.ai
        except LLMError as exc:
            if mode == GenerationMode.ai:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"AI unavailable: {exc}")
            warning = "AI was unavailable, so rule-based recommendations were used instead."  # NFR-4.01
    elif mode == GenerationMode.auto and llm is None:
        warning = "AI is not configured, so rule-based recommendations were used."

    if source == RecSource.rules:
        for r in generate_rule_recommendations(summary):
            candidates.append(dict(
                title=r.title, description=f"{r.description}\n\nWhy: {r.reasoning}",
                est_saving_t_co2e=r.est_saving_t_co2e, cost_level=r.cost_level, effort=r.effort,
                scope=r.scope, department_id=None,
            ))

    created: list[Recommendation] = []
    skipped = 0
    for c in sorted(candidates, key=lambda c: c["est_saving_t_co2e"], reverse=True):  # FR-4.05 ranked
        key = _norm(c["title"])
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        rec = Recommendation(org_id=user.org_id, source=source, status=RecStatus.proposed, **c)
        db.add(rec)
        created.append(rec)
    db.commit()
    for rec in created:
        db.refresh(rec)
        audit_service.log_action(db, user.org_id, user.id, "Recommendation", rec.id, AuditAction.create,
                                 {"source": source.value})

    return GenerateResponse(
        source_used=source,
        created=[RecommendationOut.model_validate(r) for r in created],
        skipped_duplicates=skipped,
        warning=warning,
    )


def list_recommendations(
    db: Session, user: User, status_filter: RecStatus | None = None, scope: Scope | None = None,
    department_id: UUID | None = None, source: RecSource | None = None,
) -> list[Recommendation]:
    q = db.query(Recommendation).filter(Recommendation.org_id == user.org_id)  # NFR-4.03
    if status_filter:
        q = q.filter(Recommendation.status == status_filter)
    if scope:
        q = q.filter(Recommendation.scope == scope)
    if department_id:
        q = q.filter(Recommendation.department_id == department_id)
    if source:
        q = q.filter(Recommendation.source == source)
    return q.order_by(Recommendation.est_saving_t_co2e.desc()).all()


def get_recommendation(db: Session, user: User, rec_id: UUID) -> Recommendation:
    rec = db.query(Recommendation).filter(
        Recommendation.id == rec_id, Recommendation.org_id == user.org_id
    ).first()
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found")
    return rec


def update_status(db: Session, user: User, rec_id: UUID, new_status: RecStatus) -> Recommendation:
    rec = get_recommendation(db, user, rec_id)
    old = rec.status
    if new_status not in TRANSITIONS.get(old, set()):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot change status from '{old.value}' to '{new_status.value}'"
        )
    rec.status = new_status
    db.commit()
    db.refresh(rec)
    audit_service.log_action(db, user.org_id, user.id, "Recommendation", rec.id, AuditAction.update,
                             {"status": {"from": old.value, "to": new_status.value}})  # NFR-4.10
    return rec
