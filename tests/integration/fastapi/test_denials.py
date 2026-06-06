"""FastAPI denial mapping: FORBIDDEN->403, NOT_FOUND->404, missing->404."""

from __future__ import annotations

from uuid import UUID, uuid4

from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pyrmit.adapters.fastapi import require_policy
from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
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


def _engine_with_surface(
    surface: DenialSurface,
) -> PolicyEngine[Principal[Actor, str], Action, Match]:
    engine: PolicyEngine[Principal[Actor, str], Action, Match] = PolicyEngine()

    @engine.policy(
        action=Action.READ,
        subject_type=Match,
        denial_surface=surface,
    )
    def _pol(p: Principal[Actor, str], s: Match) -> Decision:
        if p.actor.is_admin or p.actor.user_id == s.owner_id:
            return ALLOW
        return deny("not_owner")

    return engine


def _build_app(
    engine: PolicyEngine[Principal[Actor, str], Action, Match],
    actor: Actor,
) -> FastAPI:
    app = FastAPI()

    @app.get("/matches/{match_id}")
    async def _get(
        match_id: UUID,
        _authz: None = Depends(
            require_policy(
                engine=engine,
                action=Action.READ,
                subject_type=Match,
                load_subject=load_match,
                get_principal=make_principal_loader(actor),
            )
        ),
    ) -> dict[str, str]:
        return {"id": str(match_id)}

    return app


class TestForbiddenDenial:
    def test_denied_caller_gets_403_with_reason(self) -> None:
        engine = _engine_with_surface(DenialSurface.FORBIDDEN)
        stranger = Actor(user_id=uuid4(), is_admin=False)
        app = _build_app(engine, stranger)
        client = TestClient(app)
        response = client.get(f"/matches/{EXISTING_MATCH.id}")
        assert_that(response.status_code).is_equal_to(403)
        body = response.json()
        assert_that(body["detail"]["code"]).is_equal_to("FORBIDDEN")
        assert_that(body["detail"]["reason"]).is_equal_to("not_owner")


class TestNotFoundDenial:
    def test_denied_with_not_found_returns_404_without_reason(self) -> None:
        engine = _engine_with_surface(DenialSurface.NOT_FOUND)
        stranger = Actor(user_id=uuid4(), is_admin=False)
        app = _build_app(engine, stranger)
        client = TestClient(app)
        response = client.get(f"/matches/{EXISTING_MATCH.id}")
        assert_that(response.status_code).is_equal_to(404)
        body = response.json()
        assert_that(body["detail"]["code"]).is_equal_to("NOT_FOUND")
        # No `reason` -- existence MUST NOT leak.
        assert_that("reason" in body["detail"]).is_false()


class TestMissingSubject:
    def test_loader_returns_none_always_yields_404(self) -> None:
        # Even FORBIDDEN-bound routes return 404 for unknown subjects.
        engine = _engine_with_surface(DenialSurface.FORBIDDEN)
        admin = Actor(user_id=uuid4(), is_admin=True)
        app = _build_app(engine, admin)
        client = TestClient(app)
        unknown_id = uuid4()
        response = client.get(f"/matches/{unknown_id}")
        assert_that(response.status_code).is_equal_to(404)
        body = response.json()
        assert_that(body["detail"]["code"]).is_equal_to("NOT_FOUND")
