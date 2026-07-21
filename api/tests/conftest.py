import pytest
import sys
import importlib
from pathlib import Path

from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session
from typer.testing import CliRunner

from app.config import get_settings
from app.db import get_session, init_db
from app.deps import get_payment_provider
from app.main import app
from app.models import UserORM, PlanORM, PlanTemplateVersionORM, BillingInterval
from app.models.core import _utcnow
from app.services.mollie import FakePaymentProvider

# The current ToS version, used to pre-accept test users so deployment tests
# (which now require prior acceptance) work without threading acceptance through
# every case. Tests that specifically exercise the acceptance flow opt out.
CURRENT_TOS_VERSION = get_settings().current_tos_version


@pytest.fixture(autouse=True)
def _hermetic_hostname_settings(monkeypatch):
    """Isolate the whole suite from ambient DNS configuration.

    Hostname validation calls the real ``get_settings()``, which loads
    ``.env`` / ``.env.local`` / ``CAELUS_*`` vars. A configured ``CAELUS_DOMAIN``
    makes ``_check_cname`` perform real CNAME lookups against arbitrary test
    hostnames (-> ``not_resolving``), which breaks any test that creates a
    deployment. ``monkeypatch.delenv`` is not enough — the value comes from the
    ``.env.local`` *file* — so override ``get_settings`` to a blank-``domain``
    object (DNS check skipped). Tests that exercise DNS override it again.
    """
    from app.config import CaelusSettings

    monkeypatch.setattr(
        "app.services.hostnames.get_settings",
        lambda: CaelusSettings(reserved_hostnames=[], domain="", _env_file=None),
    )


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def cli_runner(tmp_path, monkeypatch):
    project_root = Path(__file__).resolve().parents[1]
    sys.path.append(str(project_root))
    # Use a temporary file-based SQLite DB for isolation
    # TODO: Refactor this to use sqlite:///:memory:
    db_path = tmp_path / "test_cli.db"
    # Ensure a clean DB file
    if db_path.exists():
        db_path.unlink()
    monkeypatch.setenv("CAELUS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("CAELUS_USER_EMAIL", "cli-test@example.com")

    from app.config import get_settings
    get_settings.cache_clear()

    import app.db as db

    importlib.reload(db)
    init_db(db.engine)

    import app.cli as cli

    importlib.reload(cli)

    return CliRunner(), cli.app


def create_free_plan_template(session: Session, product_id: int) -> int:
    """Create a free Plan + PlanTemplateVersion for a product.

    Returns the plan_template_version ID, suitable for passing as
    ``plan_template_id`` to DeploymentCreate or API deployment payloads.
    """
    plan = PlanORM(name="Free", product_id=product_id, created_at=_utcnow())
    session.add(plan)
    session.flush()
    ptv = PlanTemplateVersionORM(
        plan_id=plan.id,
        price_cents=0,
        billing_interval=BillingInterval.MONTHLY,
        storage_bytes=0,
        created_at=_utcnow(),
    )
    session.add(ptv)
    session.flush()
    plan.template_id = ptv.id
    session.commit()
    session.refresh(ptv)
    return ptv.id


def create_paid_plan_template(
    session: Session, product_id: int, *, price_cents: int = 1000, name: str = "Pro",
) -> int:
    """Create a paid Plan + PlanTemplateVersion for a product.

    Returns the plan_template_version ID.
    """
    plan = PlanORM(name=name, product_id=product_id, created_at=_utcnow())
    session.add(plan)
    session.flush()
    ptv = PlanTemplateVersionORM(
        plan_id=plan.id,
        price_cents=price_cents,
        billing_interval=BillingInterval.MONTHLY,
        storage_bytes=0,
        created_at=_utcnow(),
    )
    session.add(ptv)
    session.flush()
    plan.template_id = ptv.id
    session.commit()
    session.refresh(ptv)
    return ptv.id


ADMIN_EMAIL = "test@example.com"
AUTH_HEADER = {"X-Auth-Request-Email": ADMIN_EMAIL}

USER_EMAIL = "regular@example.com"
USER_AUTH_HEADER = {"X-Auth-Request-Email": USER_EMAIL}

OTHER_EMAIL = "other@example.com"
OTHER_AUTH_HEADER = {"X-Auth-Request-Email": OTHER_EMAIL}


def create_user(client, email: str, accept_tos: bool = True) -> dict:
    """Provision a regular (non-admin) user and return its ``UserRead`` dict.

    Users are created on their first authenticated request, so hitting
    ``GET /api/me`` with the target email auto-provisions the user. Use the
    returned dict's ``["id"]`` for the user id. Replaces the removed
    ``POST /api/users`` endpoint for test setup.

    By default the user is also marked as having accepted the current Terms of
    Service, since deploying now requires prior acceptance. Pass
    ``accept_tos=False`` to leave them unaccepted (for tests of the acceptance
    flow itself).
    """
    resp = client.get("/api/me", headers={"X-Auth-Request-Email": email})
    assert resp.status_code == 200, f"provisioning {email}: {resp.status_code}"
    if accept_tos:
        acc = client.post(
            "/api/me/tos-acceptance",
            json={"version": CURRENT_TOS_VERSION},
            headers={"X-Auth-Request-Email": email},
        )
        assert acc.status_code == 200, f"accepting tos for {email}: {acc.status_code}"
    return resp.json()


def make_accepted_user(session, email: str):
    """Create a user via the service *and* record ToS acceptance; return UserRead.

    For service-level tests that create deployments directly through
    ``create_deployment`` (which now requires the owning user to have accepted
    the current Terms).
    """
    from app.services import users as _users

    user = _users.create_user(session, _users.UserCreate(email=email))
    _users.record_tos_acceptance(
        session, user=session.get(UserORM, user.id), version=CURRENT_TOS_VERSION
    )
    return user


@pytest.fixture
def client(db_session):
    """Test client authenticated as an admin user (no payment provider)."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_session] = override_get_db
    app.dependency_overrides[get_payment_provider] = lambda: None

    # Pre-create the default test user as admin so existing tests pass
    admin_user = UserORM(email=ADMIN_EMAIL, is_admin=True,
                         tos_accepted_version=CURRENT_TOS_VERSION, tos_accepted_at=_utcnow())
    db_session.add(admin_user)
    db_session.commit()

    with TestClient(app, headers=AUTH_HEADER) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def fake_payment_provider():
    """A FakePaymentProvider instance shared across a test."""
    return FakePaymentProvider()


@pytest.fixture
def paid_client(db_session, fake_payment_provider, monkeypatch):
    """Test client with FakePaymentProvider injected via dependency override."""
    from app.config import get_settings

    monkeypatch.setenv("CAELUS_MOLLIE_REDIRECT_URL", "https://test.example.com")
    monkeypatch.setenv("CAELUS_MOLLIE_WEBHOOK_BASE_URL", "https://test.example.com/api")
    get_settings.cache_clear()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_session] = override_get_db
    app.dependency_overrides[get_payment_provider] = lambda: fake_payment_provider

    admin_user = UserORM(email=ADMIN_EMAIL, is_admin=True,
                         tos_accepted_version=CURRENT_TOS_VERSION, tos_accepted_at=_utcnow())
    db_session.add(admin_user)
    db_session.commit()

    with TestClient(app, headers=AUTH_HEADER) as client:
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def user_client(db_session):
    """Test client authenticated as a regular (non-admin) user."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_session] = override_get_db

    # Pre-create admin user (some tests need resources created by admin)
    admin_user = UserORM(email=ADMIN_EMAIL, is_admin=True,
                         tos_accepted_version=CURRENT_TOS_VERSION, tos_accepted_at=_utcnow())
    db_session.add(admin_user)
    # Pre-create the acting regular user as already-accepted so deploy tests
    # under this client don't trip the acceptance precondition.
    regular_user = UserORM(email=USER_EMAIL,
                           tos_accepted_version=CURRENT_TOS_VERSION, tos_accepted_at=_utcnow())
    db_session.add(regular_user)
    db_session.commit()
    db_session.refresh(admin_user)

    with TestClient(app, headers=USER_AUTH_HEADER) as c:
        yield c, admin_user

    app.dependency_overrides.clear()
