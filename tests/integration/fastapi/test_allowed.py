"""Allowed caller -> handler runs."""

from __future__ import annotations

from uuid import UUID

from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pyrmit.adapters.fastapi import require_policy
from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.principal import Principal
from tests.integration.fastapi._fixtures import (
    EXISTING_MATCH,
    Action,
    Actor,
    Match,
    load_match,
    make_principal_loader,
)


class TestAllowedFlow:
    def test_allowed_route_returns_handler_output(self) -> None:
        engine: PolicyEngine[Principal[Actor, str], Action, Match] = PolicyEngine()

        @engine.policy(action=Action.READ, subject_type=Match)
        def _pol(_p: Principal[Actor, str], _s: Match) -> Decision:
            return ALLOW

        admin = Actor(user_id=UUID(int=99), is_admin=True)
        app = FastAPI()

        @app.get("/matches/{match_id}")
        async def get_match(
            match_id: UUID,
            _authz: None = Depends(
                require_policy(
                    engine=engine,
                    action=Action.READ,
                    subject_type=Match,
                    load_subject=load_match,
                    get_principal=make_principal_loader(admin),
                )
            ),
        ) -> dict[str, str]:
            return {"id": str(match_id), "status": "ok"}

        client = TestClient(app)
        response = client.get(f"/matches/{EXISTING_MATCH.id}")
        assert_that(response.status_code).is_equal_to(200)
        assert_that(response.json()).is_equal_to({"id": str(EXISTING_MATCH.id), "status": "ok"})
