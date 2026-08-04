import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.db import Base
from app.models import (
    DistributionTransformer,
    FaultKind,
    Feeder,
    Incident,
    Pole,
    PoleState,
    TicketStatus,
)
from app.api.incidents import explain_incident
from app.settings import get_settings

engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(bind=engine)


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture
def test_db():
    tables = [
        Feeder.__table__,
        DistributionTransformer.__table__,
        Pole.__table__,
        PoleState.__table__,
        Incident.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    db = TestingSessionLocal()

    # Seed
    inc = Incident(
        id="INC-EX",
        kind=FaultKind.dt,
        status=TicketStatus.detected,
        feeder_id="F-TEST",
        dt_id="DT-1",
        affected_poles=3,
        reasons=["All 3 poles dark", "DT primary silent"],
        confidence=0.95,
    )
    db.add(inc)
    db.commit()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=tables)


@pytest.mark.anyio
async def test_explain_fallback(test_db):
    # Retrieve explanation with no API key
    with patch("app.api.incidents.get_settings") as mock_settings:
        mock_settings.return_value.groq_api_key = ""
        mock_settings.return_value.openai_api_key = ""
        res = await explain_incident("INC-EX", db=test_db)
        
        assert res["id"] == "INC-EX"
        assert res["source"] == "deterministic"
        assert "Deterministic grid analysis identified a dt outage" in res["explanation"]
        assert "All 3 poles dark" in res["explanation"]


@pytest.mark.anyio
async def test_explain_llm_success(test_db):
    from unittest.mock import MagicMock
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "This is a mocked LLM explanation of the transformer outage."
                }
            }
        ]
    }

    with patch("app.api.incidents.get_settings") as mock_settings, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):

        
        mock_settings.return_value.groq_api_key = "fake-groq-key"
        mock_settings.return_value.openai_api_key = ""
        
        res = await explain_incident("INC-EX", db=test_db)
        
        assert res["id"] == "INC-EX"
        assert res["source"] == "groq-llm"
        assert res["explanation"] == "This is a mocked LLM explanation of the transformer outage."
