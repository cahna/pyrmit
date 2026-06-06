"""NULL denial surface propagates the mapper's status, body, and headers.

Pins the contract that ``null_mapper`` returns an ``HttpDenial`` value
whose status_code, detail, and headers all reach the client untouched.
The typed-value shape replaced an earlier ``Response``-shaped API where
body and headers were silently dropped.
"""

from __future__ import annotations

from uuid import UUID

from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pyrmit.adapters.fastapi import HttpDenial, require_policy
from pyrmit.core.decision import Decision, DenialSurface, deny
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


def _null_mapper(decision: Decision) -> HttpDenial:
    return HttpDenial(
        status_code=200,
        reason=decision.reason,
        headers={"X-Auth-Null": "1"},
        detail={"data": None, "reason": decision.reason},
    )


class TestNullSurfacePropagation:
    def _make_app(self) -> FastAPI:
        engine: PolicyEngine[Principal[Actor, str], Action, Match] = PolicyEngine()

        @engine.policy(action=Action.READ, subject_type=Match, denial_surface=DenialSurface.NULL)
        def _pol(_p: Principal[Actor, str], _s: Match) -> Decision:
            return deny("match_hidden")

        non_admin = Actor(user_id=UUID(int=42), is_admin=False)
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
                    get_principal=make_principal_loader(non_admin),
                    null_mapper=_null_mapper,
                )
            ),
        ) -> dict[str, str]:
            return {"id": str(match_id), "status": "ok"}

        return app

    def test_status_code_is_taken_from_mapper(self) -> None:
        client = TestClient(self._make_app(), raise_server_exceptions=False)
        response = client.get(f"/matches/{EXISTING_MATCH.id}")
        assert_that(response.status_code).is_equal_to(200)

    def test_body_propagates_from_mapper(self) -> None:
        client = TestClient(self._make_app(), raise_server_exceptions=False)
        response = client.get(f"/matches/{EXISTING_MATCH.id}")
        body = response.json()
        # FastAPI's HTTPException handler wraps detail under "detail".
        assert_that(body).contains_key("detail")
        detail = body["detail"]
        assert_that(detail).is_equal_to({"data": None, "reason": "match_hidden"})

    def test_headers_propagate_from_mapper(self) -> None:
        client = TestClient(self._make_app(), raise_server_exceptions=False)
        response = client.get(f"/matches/{EXISTING_MATCH.id}")
        assert_that(response.headers.get("X-Auth-Null")).is_equal_to("1")

    def test_default_detail_falls_back_to_reason_when_not_set(self) -> None:
        """An HttpDenial without an explicit detail uses reason as detail."""
        engine: PolicyEngine[Principal[Actor, str], Action, Match] = PolicyEngine()

        @engine.policy(action=Action.READ, subject_type=Match, denial_surface=DenialSurface.NULL)
        def _pol(_p: Principal[Actor, str], _s: Match) -> Decision:
            return deny("match_hidden")

        app = FastAPI()
        non_admin = Actor(user_id=UUID(int=42), is_admin=False)

        @app.get("/matches/{match_id}")
        async def get_match(
            match_id: UUID,
            _authz: None = Depends(
                require_policy(
                    engine=engine,
                    action=Action.READ,
                    subject_type=Match,
                    load_subject=load_match,
                    get_principal=make_principal_loader(non_admin),
                    null_mapper=lambda d: HttpDenial(status_code=200, reason=d.reason),
                )
            ),
        ) -> dict[str, str]:
            return {"id": str(match_id), "status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/matches/{EXISTING_MATCH.id}")
        assert_that(response.status_code).is_equal_to(200)
        assert_that(response.json()).is_equal_to({"detail": "match_hidden"})
