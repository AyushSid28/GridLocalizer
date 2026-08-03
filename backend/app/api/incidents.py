from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db import get_db
from app.models import Incident, ScheduledOutage, TicketStatus
from app.settings import get_settings
import httpx


router = APIRouter(prefix="/incidents", tags=["incidents"])


class CrewAssignmentIn(BaseModel):
    crew_label: str


def active_schedule_for_incident(db: Session, inc: Incident) -> dict | None:
    now = datetime.now(timezone.utc)
    if db.bind.dialect.name == "sqlite":
        now = now.replace(tzinfo=None)

    scopes: list[tuple[str, str | None]] = [
        ("dt", inc.dt_id),
        ("feeder", inc.feeder_id),
    ]
    for scope, target_id in scopes:
        if not target_id:
            continue
        outage = db.scalar(
            select(ScheduledOutage)
            .where(
                ScheduledOutage.scope == scope,
                ScheduledOutage.target_id == target_id,
                ScheduledOutage.starts_at <= now,
                ScheduledOutage.ends_at >= now,
            )
            .limit(1)
        )
        if outage:
            return {
                "id": outage.id,
                "scope": outage.scope,
                "target_id": outage.target_id,
                "starts_at": outage.starts_at.isoformat(),
                "ends_at": outage.ends_at.isoformat(),
                "reason": outage.reason,
            }
    return None


@router.get("")
def list_incidents(db: Session = Depends(get_db)) -> list[dict]:
    """Get all detected and active/historical incidents."""
    stmt = select(Incident).order_by(Incident.created_at.desc())
    rows = db.scalars(stmt).all()
    return [
        {
            "id": r.id,
            "kind": r.kind.value,
            "status": r.status.value,
            "feeder_id": r.feeder_id,
            "dt_id": r.dt_id,
            "span_from": r.span_from,
            "span_to": r.span_to,
            "lat": r.lat,
            "lon": r.lon,
            "pincode": r.pincode,
            "affected_poles": r.affected_poles,
            "confidence": r.confidence,
            "reasons": r.reasons,
            "evidence": r.evidence,
            "topology_mode": r.topology_mode,
            "summary": r.summary,
            "crew_label": r.crew_label,
            "verify_note": r.verify_note,
            "scheduled_outage": active_schedule_for_incident(db, r),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "verified_at": r.verified_at.isoformat() if r.verified_at else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        }
        for r in rows
    ]


@router.post("/{incident_id}/acknowledge")
def acknowledge_incident(incident_id: str, db: Session = Depends(get_db)) -> dict:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    if inc.status != TicketStatus.detected:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot acknowledge incident in status {inc.status.value}",
        )

    inc.status = TicketStatus.acknowledged
    db.commit()
    return {"id": inc.id, "status": inc.status.value}


@router.post("/{incident_id}/assign_crew")
def assign_crew(
    incident_id: str, data: CrewAssignmentIn, db: Session = Depends(get_db)
) -> dict:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    if inc.status not in [TicketStatus.detected, TicketStatus.acknowledged]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot assign crew to incident in status {inc.status.value}",
        )

    inc.status = TicketStatus.crew_assigned
    inc.crew_label = data.crew_label
    db.commit()
    return {"id": inc.id, "status": inc.status.value, "crew_label": inc.crew_label}


@router.post("/{incident_id}/resolve")
def resolve_incident(incident_id: str, db: Session = Depends(get_db)) -> dict:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    if inc.status != TicketStatus.crew_assigned:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resolve incident in status {inc.status.value}. Crew must be assigned first.",
        )

    inc.status = TicketStatus.resolved
    inc.verify_note = "Repair marked complete. Waiting for power_restored and boot telemetry before automatic closure."
    db.commit()
    return {
        "id": inc.id,
        "status": inc.status.value,
        "note": inc.verify_note,
    }


@router.post("/{incident_id}/explain")
async def explain_incident(incident_id: str, db: Session = Depends(get_db)) -> dict:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    settings = get_settings()
    reasons_bulleted = "\n".join(f"- {r}" for r in inc.reasons)

    prompt = (
        f"You are a utility operator assistant. Explain the following power grid incident in a short, "
        f"technical, and objective paragraph. Focus ONLY on the provided deterministic reasons and stats. "
        f"Do not extrapolate, assume, or invent new facts:\n\n"
        f"Incident Kind: {inc.kind.value.upper()} Outage\n"
        f"Affected Poles: {inc.affected_poles}\n"
        f"Confidence: {(inc.confidence * 100):.0f}%\n"
        f"Deterministic Evidence:\n{reasons_bulleted}"
    )

    # Try Groq first (key configured in .env as GROQ_API_KEY)
    if settings.groq_api_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a professional control room assistant for a power grid. Summarize facts strictly. Keep response under 3 sentences.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 150,
                    },
                )
                if response.status_code == 200:
                    summary = response.json()["choices"][0]["message"]["content"].strip()
                    return {"id": inc.id, "explanation": summary, "source": "groq-llm"}
        except Exception:
            pass  # Fall through to deterministic

    # Try OpenAI if configured
    if settings.openai_api_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": "You are a professional control room assistant for a power grid. Summarize facts strictly."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 150,
                    },
                )
                if response.status_code == 200:
                    summary = response.json()["choices"][0]["message"]["content"].strip()
                    return {"id": inc.id, "explanation": summary, "source": "openai-llm"}
        except Exception:
            pass  # Fall through to deterministic

    # Deterministic fallback — always works, no API key needed
    reasons_str = " ".join(inc.reasons)
    fallback = (
        f"Deterministic grid analysis identified a {inc.kind.value} outage affecting {inc.affected_poles} poles. "
        f"The localization engine computed a confidence of {(inc.confidence * 100):.0f}% based on verified telemetry patterns: "
        f"{reasons_str}"
    )
    return {"id": inc.id, "explanation": fallback, "source": "deterministic"}
