from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Optional, Any
from uuid import UUID, uuid4

from pydantic import ConfigDict, field_validator, model_validator
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Enum as SAEnum,
    ForeignKey,
    Identity,
    Integer,
    Index,
    JSON,
    PrimaryKeyConstraint,
    Text,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)

from app.config import get_settings
from app.services.reconcile_constants import DEPLOYMENT_STATUS_DELETED


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserBase(SQLModel):
    email: str


class UserORM(UserBase, table=True):
    __tablename__ = "user"
    __table_args__ = (
        Index(
            "uq_user_active",
            func.lower(Column("email")),
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
            postgresql_where=Column("deleted_at").is_(None),
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(nullable=False, unique=False)
    is_admin: bool = Field(default=False, nullable=False)
    mollie_customer_id: Optional[str] = Field(default=None)
    # Terms of Service acceptance is a user-level fact recorded once, not per
    # deployment. Both are NULL until the user's first deployment records
    # consent. `tos_accepted_version` is the accepted ToS effective date
    # (YYYY-MM-DD, recorded verbatim as displayed); `tos_accepted_at` is the
    # instant of the click (a timestamp, the evidentiary value).
    tos_accepted_version: Optional[str] = Field(default=None, nullable=True)
    tos_accepted_at: Optional[datetime] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    deployments: list["DeploymentORM"] = Relationship(back_populates="user")
    subscriptions: list["SubscriptionORM"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "SubscriptionORM.user_id"},
    )
    deleted_at: Optional[datetime] = Field(default=None)


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int
    is_admin: bool
    created_at: datetime


class TosAcceptanceCreate(SQLModel):
    """Request body for recording the current user's ToS acceptance."""
    model_config = ConfigDict(extra="forbid")
    # The ToS version (effective date) the user is accepting, as displayed to
    # them. Shape-validated here; the service additionally requires it to equal
    # the current version before recording.
    version: str

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise ValueError("version must be an ISO-8601 date (YYYY-MM-DD)")
        return v


class TosAcceptanceRead(SQLModel):
    """The current user's ToS acceptance status. `version` is null until the
    user has accepted; this resource is always readable (a 200 status document,
    not a 404-when-absent).

    `current_version` is the version the platform currently requires
    (`settings.current_tos_version`) and is always present, so non-browser
    clients — which have no bundled ToS document to parse an effective date
    from — can learn which version to submit. It is independent of `version`:
    the two differ whenever the terms have changed since the user accepted.
    """
    version: Optional[str] = None
    accepted_at: Optional[datetime] = None
    current_version: str


class ProductVisibility(StrEnum):
    """Whether a product is offered to end users.

    Runtime state, deliberately independent of curation: a catalog-managed
    product may be hidden, and a database-authored one may be public. New
    products start ADMIN so onboarding is never visible before it is ready.
    """

    PUBLIC = "public"
    ADMIN = "admin"


class ProductBase(SQLModel):
    name: str
    description: str | None = None
    template_id: Optional[int] = None
    category: str | None = None
    replaces: str | None = None
    visibility: ProductVisibility = ProductVisibility.ADMIN


class ProductORM(ProductBase, table=True):
    __tablename__ = "product"
    __table_args__ = (
        Index(
            "uq_product_name_active",
            func.lower(Column("name")),
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
            postgresql_where=Column("deleted_at").is_(None),
        ),
        Index(
            "uq_product_slug_active",
            "slug",
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
            postgresql_where=Column("deleted_at").is_(None),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field()
    # The stable key joining this row to its `products/catalog/<slug>.yaml`
    # file, deliberately independent of `name` so renaming a product does not
    # orphan its catalog entry. Null for database-authored products.
    slug: Optional[str] = Field(default=None, nullable=True)
    # Whether the catalog owns this product. Written *only* by the
    # CatalogReconciler, derived from catalog file presence, so the file and
    # the flag cannot disagree.
    curated: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    # The product's canonical template used for new deployments:
    template_id: Optional[int] = Field(
        default=None, foreign_key="product_template_version.id", index=True
    )
    # Relative path to product icon under STATIC_PATH (e.g., "icons/<sha1>.png")
    rel_icon_path: Optional[str] = Field(default=None, nullable=True)
    visibility: ProductVisibility = Field(
        default=ProductVisibility.ADMIN,
        sa_column=Column(
            SAEnum(ProductVisibility, values_callable=lambda e: [m.value for m in e]),
            nullable=False,
            server_default=ProductVisibility.ADMIN.value,
        ),
    )
    template: "ProductTemplateVersionORM" = Relationship(
        back_populates="products",
        sa_relationship_kwargs={"foreign_keys": "ProductORM.template_id", "lazy": "joined"},
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    templates: list["ProductTemplateVersionORM"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={"foreign_keys": "ProductTemplateVersionORM.product_id"},
    )
    plans: list["PlanORM"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={"foreign_keys": "PlanORM.product_id"},
    )
    deleted_at: Optional[datetime] = Field(default=None)


class ProductCreate(ProductBase):
    # `slug` and `curated` are reconciler-owned, so an attempt to set them out
    # of band is rejected rather than silently ignored.
    model_config = ConfigDict(extra="forbid")


class ProductUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")
    id: Optional[int] = None
    name: str | None = None
    template_id: Optional[int] = None
    description: str | None = None
    category: str | None = None
    replaces: str | None = None
    visibility: ProductVisibility | None = None


class ProductReadBase(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    icon_url: Optional[str] = None
    # Read-only projections of the reconciler-owned columns; the admin UI
    # branches on `curated` to render catalog-managed products read-only.
    slug: Optional[str] = None
    curated: bool = False

    @model_validator(mode="before")
    @classmethod
    def _compute_icon_url(cls, data: Any) -> Any:
        """Derive icon_url from rel_icon_path when serializing from ORM."""
        from app.config import get_static_url_base

        if isinstance(data, dict):
            rel = data.get("rel_icon_path")
        else:
            rel = getattr(data, "rel_icon_path", None)
        if rel:
            if isinstance(data, dict):
                data.setdefault("icon_url", f"{get_static_url_base()}/{rel}")
            else:
                # For ORM objects, we need to return a dict so we can inject icon_url
                d = {k: getattr(data, k) for k in cls.model_fields if hasattr(data, k)}
                d["icon_url"] = f"{get_static_url_base()}/{rel}"
                return d
        return data


class ProductRead(ProductReadBase):
    template: Optional["ProductTemplateVersionRead"]


class ProductTemplateVersionBase(SQLModel):
    product_id: int
    chart_ref: str = None
    chart_version: str = None
    chart_digest: Optional[str] = None
    system_values_json: Optional[dict[str, Any]] = None
    values_schema_json: Optional[dict[str, Any]] = None


class ProductTemplateVersionORM(ProductTemplateVersionBase, table=True):
    __tablename__ = "product_template_version"

    id: Optional[int] = Field(default=None, primary_key=True)
    chart_ref: str
    chart_version: str
    system_values_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    values_schema_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    product_id: int = Field(
        sa_column=Column(Integer, ForeignKey("product.id"), nullable=False, index=True)
    )
    # The git commit whose catalog produced this row, stamped once on insert by
    # the reconciler. Audit metadata only: deliberately absent from the create
    # and read schemas, never read by application logic, and never part of
    # template matching (a null value simply means "not catalog-produced").
    catalog_commit: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
    product: ProductORM = Relationship(
        back_populates="templates",
        sa_relationship_kwargs={"foreign_keys": "ProductTemplateVersionORM.product_id", "lazy": "joined"},
    )
    products: list["ProductORM"] = Relationship(
        back_populates="template", sa_relationship_kwargs={"foreign_keys": "ProductORM.template_id"}
    )
    deployments: list["DeploymentORM"] = Relationship(
        back_populates="applied_template",
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.applied_template_id"},
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)


class ProductTemplateVersionCreate(ProductTemplateVersionBase):
    product_id: Optional[int] = None


class ProductTemplateVersionRead(ProductTemplateVersionBase):
    id: Optional[int]
    created_at: datetime
    product: ProductReadBase


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------


class DeploymentBase(SQLModel):
    desired_template_id: int
    user_id: int
    user_values_json: Optional[dict[str, Any]] = Field(default=None)


class DeploymentORM(DeploymentBase, table=True):
    __tablename__ = "deployment"
    __table_args__ = (
        Index(
            "uq_deployment_active",
            "user_id",
            func.lower(Column("hostname")),
            "desired_template_id",
            unique=True,
            sqlite_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
            postgresql_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
        ),
        Index(
            "uq_hostname_active",
            func.lower(Column("hostname")),
            unique=True,
            sqlite_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
            postgresql_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
        ),
        Index(
            "uq_deployment_ns_name_active",
            "namespace",
            "name",
            unique=True,
            sqlite_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
            postgresql_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
        ),
    )

    id: UUID = Field(default_factory=uuid4, sa_column=Column(Uuid, primary_key=True))
    user_id: int = Field(foreign_key="user.id", index=True)
    desired_template_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("product_template_version.id"),
            nullable=False,
            index=True,
        ),
    )
    applied_template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("product_template_version.id"),
            nullable=True,
            index=True,
        ),
    )
    # ── Release pointers ──────────────────────────────────────────────────
    #
    # The reference between `deployment` and `deployment_release` is mutual,
    # and under immediate constraints neither row could be inserted first:
    # the deployment would violate this NOT NULL, and the release would
    # violate its `deployment_id` FK. Both primary keys are Python-generated
    # `uuid4`, so both ids are known before either INSERT; the deployment is
    # therefore inserted with `desired_release_id` already set, the release
    # second, and DEFERRABLE INITIALLY DEFERRED defers the check to COMMIT.
    #
    # `use_alter` is what makes that work mechanically. It lifts these two
    # FKs out of the table dependency graph, which would otherwise be cyclic
    # -- breaking both `create_all`'s DDL ordering and SQLAlchemy's flush
    # ordering, and leaving `deployment_release.deployment_id` as the only
    # edge, which orders the INSERTs exactly as above.
    #
    # Deferred NO ACTION also replaces the `ON DELETE SET NULL` that would
    # otherwise be reached for, and which would contradict the NOT NULL: a
    # hard delete drops both rows in one transaction and the deferred check
    # sees neither.
    #
    # NOT NULL: every deployment is created together with its first release,
    # and the migration backfills one for every deployment that predates the
    # ledger. A deployment without a release it wants to be running is not a
    # state the system has.
    desired_release_id: UUID = Field(
        sa_column=Column(
            Uuid,
            ForeignKey(
                "deployment_release.id",
                name="fk_deployment_desired_release_id",
                use_alter=True,
                deferrable=True,
                initially="DEFERRED",
            ),
            nullable=False,
            index=True,
        ),
    )
    applied_release_id: Optional[UUID] = Field(
        default=None,
        sa_column=Column(
            Uuid,
            ForeignKey(
                "deployment_release.id",
                name="fk_deployment_applied_release_id",
                use_alter=True,
                deferrable=True,
                initially="DEFERRED",
            ),
            nullable=True,
            index=True,
        ),
    )
    applied_release: Optional["DeploymentReleaseORM"] = Relationship(
        sa_relationship_kwargs={
            "viewonly": True,
            "lazy": "joined",
            "foreign_keys": "DeploymentORM.applied_release_id",
        }
    )
    desired_release: Optional["DeploymentReleaseORM"] = Relationship(
        sa_relationship_kwargs={
            "viewonly": True,
            "lazy": "joined",
            "foreign_keys": "DeploymentORM.desired_release_id",
        }
    )
    hostname: Optional[str] = Field(
        default=None, sa_column=Column(String(), nullable=True, index=True)
    )
    name: str = Field(sa_column=Column(String(), nullable=False, index=True))
    namespace: str = Field(sa_column=Column(String(), nullable=False, index=True))
    user_values_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    status: str = Field(default="pending", nullable=False, index=True)
    generation: int = Field(default=1, nullable=False)
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
    last_reconcile_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)
    reconcile_jobs: list["DeploymentReconcileJobORM"] = Relationship(back_populates="deployment")
    user: UserORM = Relationship(back_populates="deployments", sa_relationship_kwargs={"lazy": "joined"})
    desired_template: Optional[ProductTemplateVersionORM] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.desired_template_id", "lazy": "joined"}
    )
    applied_template: Optional[ProductTemplateVersionORM] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.applied_template_id", "lazy": "joined"}
    )
    subscription_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("subscription.id"),
            nullable=True,
            index=True,
        ),
    )
    subscription: Optional["SubscriptionORM"] = Relationship(
        back_populates="deployments",
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.subscription_id", "lazy": "joined"},
    )

    def payment_description(self) -> str:
        """The description used for Mollie payments MUST be unique per customer. So if a user has
        multiple instances of the same product, we need to include the instance ID in the description.
        """
        return f"{self.subscription.plan_template.plan.product.name} -- {self.subscription.plan_template.plan.name} (instance {self.id})"


_BUILD_ID_FIELD_DESCRIPTION = (
    "Build this rollout deploys, recorded on the release for provenance. "
    "Optional; validated only for existence and ownership."
)


class DeploymentCreate(DeploymentBase):
    model_config = ConfigDict(extra="forbid")
    plan_template_id: int
    user_values_json: dict[str, Any] = Field(default=dict())
    user_id: Optional[int] = None
    build_id: Optional[UUID] = Field(
        default=None, description=_BUILD_ID_FIELD_DESCRIPTION
    )


class DeploymentUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")
    id: Optional[UUID] = None
    user_id: Optional[int] = None
    desired_template_id: int
    user_values_json: Optional[dict[str, Any]] = Field(default=None)
    build_id: Optional[UUID] = Field(
        default=None, description=_BUILD_ID_FIELD_DESCRIPTION
    )


class DeploymentRead(DeploymentBase):
    id: UUID
    created_at: datetime
    user: UserRead
    hostname: Optional[str] = None
    desired_template: ProductTemplateVersionRead
    applied_template: Optional[ProductTemplateVersionRead]
    applied_release: Optional["DeploymentReleaseRead"] = None
    subscription_id: Optional[int] = None
    subscription: Optional["SubscriptionRead"] = None
    name: str
    namespace: str
    status: str = Field(default="pending")
    generation: int = Field(default=1)
    last_error: Optional[str] = None
    last_reconcile_at: Optional[datetime] = None


class SftpCredentialsRead(SQLModel):
    """SFTP connection details for a deployment with file access.

    host/port are the user-facing platform endpoint (from settings); username
    and password come from the deployment's credentials Secret in the cluster
    and are never persisted in the Caelus database.
    """
    host: str
    port: int
    username: str
    password: str


class DeploymentCreateResponse(SQLModel):
    """Envelope returned by the deployment creation endpoint only."""
    deployment: DeploymentRead
    checkout_url: str | None = None


# ---------------------------------------------------------------------------
# Deployment release
# ---------------------------------------------------------------------------
#
# A release is the record of *one rollout* of a deployment. It is created by
# the request that asks for the rollout -- POST/PUT /deployments, in the same
# transaction as the deployment write -- and completed later by the reconciler
# that applies it. The reconciler never creates one.
#
# No column is ever revised. The request writes identity and intent
# (`number`, `template_id`, `build_id`, `values_json`, `created_at`); the
# reconciler writes outcome (`started_at`, `ended_at`, `error`,
# `helm_revision`). `started_at` is write-if-null so that a lease reclaim
# after a worker died mid-Helm still records when work *first* began -- how
# many attempts there were is `deployment_reconcile_job.attempt`, not
# something to infer from here.


class ReleaseStatus(StrEnum):
    """A release's status, always derived and never stored.

    Liveness is the opposite case and is *not* here: a release is live iff
    it is `deployment.applied_release_id`, which the reconciler writes when
    it succeeds. That is a recorded action, not an observation, so storing it
    costs one column and no subquery.
    """

    QUEUED = "queued"
    IN_FLIGHT = "in_flight"
    ABANDONED = "abandoned"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


class DeploymentReleaseBase(SQLModel):
    deployment_id: UUID
    number: int
    template_id: int


class DeploymentReleaseORM(DeploymentReleaseBase, table=True):
    __tablename__ = "deployment_release"
    __table_args__ = (
        # Structural, not incidental: `number` is assigned as max+1 per
        # deployment, which is safe only because `enqueue_job` rejects a
        # second open job and `update_deployment` requires ready/error.
        # The constraint is what makes that a guarantee rather than a habit.
        UniqueConstraint("deployment_id", "number", name="uq_release_number"),
    )

    id: UUID = Field(default_factory=uuid4, sa_column=Column(Uuid, primary_key=True))
    number: int = Field(sa_column=Column(Integer, nullable=False))
    deployment_id: UUID = Field(
        sa_column=Column(
            Uuid,
            ForeignKey("deployment.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    template_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("product_template_version.id"),
            nullable=False,
        )
    )
    # Nullable and routinely null: builds exist only for products that deploy
    # tenant-supplied code, so a null here is a curated product, not an
    # incomplete record.
    build_id: Optional[UUID] = Field(
        default=None,
        sa_column=Column(
            Uuid,
            ForeignKey("build.id"),
            nullable=True,
            index=True,
        ),
    )
    # The *user* values, not the merged values. System overrides do not exist
    # yet at request time and are largely per-apply platform detail; the user
    # values are the intent, and are what comparing two releases would need.
    values_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    # `lazy="raise"`: readers must ask for it with `joinedload`. Not imported --
    # `models/build.py` imports this module; the registry resolves the name.
    build: Optional["BuildORM"] = Relationship(  # noqa: F821
        sa_relationship_kwargs={"viewonly": True, "lazy": "raise"}
    )

    # ── Written by the reconciler, once each ──────────────────────────────
    started_at: Optional[datetime] = Field(default=None, nullable=True)
    ended_at: Optional[datetime] = Field(default=None, nullable=True)
    error: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
    helm_revision: Optional[int] = Field(default=None, nullable=True)

    @property
    def status(self) -> ReleaseStatus:
        """Derive the release's status from the three outcome columns.

        A release that has been created but not yet applied is QUEUED rather
        than missing or erroneous -- which is the state of every deployment
        awaiting payment.

        IN_FLIGHT becomes ABANDONED once work has been in flight for longer
        than the reconcile job lease, because past that point another worker
        is entitled to steal the job and the one that held it is presumed
        dead. The lease is the right threshold rather than HELM_TIMEOUT_SEC:
        a reconcile may legitimately spend the full Helm budget, and the
        lease is already tuned to sit above it.
        """
        if self.started_at is None:
            return ReleaseStatus.QUEUED
        if self.ended_at is None:
            started = self.started_at
            # Postgres hands back naive datetimes for a plain DateTime column
            # while `_utcnow()` writes aware ones; comparing the two raises.
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            lease = timedelta(seconds=get_settings().reconcile_job_lease_seconds)
            if datetime.now(UTC) - started > lease:
                return ReleaseStatus.ABANDONED
            return ReleaseStatus.IN_FLIGHT
        return ReleaseStatus.FAILED if self.error else ReleaseStatus.SUCCEEDED


class DeploymentReleaseRead(DeploymentReleaseBase):
    id: UUID
    build_id: Optional[UUID] = None
    values_json: Optional[dict[str, Any]] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    error: Optional[str] = None
    helm_revision: Optional[int] = None
    # Derived on read from the property above; there is no column behind it.
    status: ReleaseStatus


class DeploymentReleaseWithBuildRead(DeploymentReleaseRead):
    """A release read as a resource, with its build inlined.

    Kept distinct from `DeploymentReleaseRead`, which is what
    `DeploymentRead.applied_release` uses: deployment queries carry no
    `joinedload`, so a `build` field there would raise.
    """

    build: Optional["BuildRead"] = None


# ---------------------------------------------------------------------------
# Deployment vars
# ---------------------------------------------------------------------------
#
# A var is one entry in a deployment's process environment. The table is
# append-only: setting a key inserts a row, deleting it inserts a *tombstone*
# -- a row with no value -- and nothing is ever updated in place except the
# re-encryption sweep, which rewrites a row's representation and never its
# plaintext.
#
# The effective set ("head") is the newest row per key with the tombstones
# filtered out (`app/services/vars.py`).
#
# `release_var` freezes head onto a release at the moment it is created, which
# is what makes a release reproducible after later writes and deletions.


class DeploymentVarORM(SQLModel, table=True):
    __tablename__ = "deployment_var"
    __table_args__ = (
        CheckConstraint(
            "(value_encrypted IS NULL) = (key_id IS NULL)",
            name="ck_deployment_var_tombstone",
        ),
        # Head resolution: newest row per key within one deployment.
        Index("ix_deployment_var_head", "deployment_id", "key", text("id DESC")),
        # Serves key retirement and the re-encryption sweep.
        Index("ix_deployment_var_key_id", "key_id"),
    )

    # `Identity(always=True)` because nothing may choose an id here: head
    # resolution and the release snapshot both order by it, so the sequence is
    # the record of what was written after what. SQLite ignores Identity, and
    # only auto-increments a column typed exactly INTEGER -- hence the variant.
    id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            BigInteger().with_variant(Integer, "sqlite"),
            Identity(always=True),
            primary_key=True,
            autoincrement=True,
        ),
    )
    deployment_id: UUID = Field(
        sa_column=Column(
            Uuid,
            ForeignKey("deployment.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    key: str = Field(sa_column=Column(String(64), nullable=False))
    # NULL is meaningful: it is the tombstone. Never plaintext -- non-sensitive
    # values are encrypted by the same code path as sensitive ones.
    value_encrypted: Optional[str] = Field(
        default=None, sa_column=Column(Text(), nullable=True)
    )
    # The fingerprint of the encrypting key (8 hex chars), not its position in
    # the configured list: keys are introduced by prepending, which would
    # silently renumber every historical row.
    key_id: Optional[str] = Field(default=None, sa_column=Column(String(8), nullable=True))
    # Per row rather than per key, which is what lets a key be flipped to
    # sensitive by writing a new row.
    sensitive: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false"))
    )
    created_by: int = Field(
        sa_column=Column(Integer, ForeignKey("user.id"), nullable=False)
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class ReleaseVarORM(SQLModel, table=True):
    """The var rows a release was created with. Immutable once written.

    No `key` column: it is reachable through the join, and denormalizing it
    would create a second place for a key name to be wrong.
    """

    __tablename__ = "release_var"
    __table_args__ = (
        PrimaryKeyConstraint("release_id", "var_id"),
        Index("ix_release_var_var", "var_id"),
    )

    release_id: UUID = Field(
        sa_column=Column(
            Uuid,
            ForeignKey("deployment_release.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    var_id: int = Field(
        sa_column=Column(
            BigInteger().with_variant(Integer, "sqlite"),
            ForeignKey("deployment_var.id", ondelete="CASCADE"),
            nullable=False,
        )
    )


class DeploymentReconcileJobBase(SQLModel):
    deployment_id: UUID
    reason: str
    status: str = Field(default="queued")
    run_after: datetime = Field(default_factory=_utcnow, nullable=False)
    # Number of times this job has been re-claimed after its lease expired,
    # i.e. how often a worker died mid-reconcile while holding it. Bumped by
    # JobService._claim_next_job_* on reclaim only, never on a first claim.
    attempt: int = Field(default=0, nullable=False)
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    last_error: Optional[str] = None


class DeploymentReconcileJobORM(DeploymentReconcileJobBase, table=True):
    __tablename__ = "deployment_reconcile_job"
    __table_args__ = (
        Index(
            "uq_open_reconcile_job_per_deployment",
            "deployment_id",
            unique=True,
            sqlite_where=Column("status").in_(("queued", "running")),
            postgresql_where=Column("status").in_(("queued", "running")),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    deployment_id: UUID = Field(
        sa_column=Column(
            Uuid,
            ForeignKey("deployment.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    deployment: DeploymentORM = Relationship(back_populates="reconcile_jobs")
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)
