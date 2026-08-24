"""Allow deployment.hostname to be null

A deployment whose desired template declares no hostname-titled field has no
hostname, and the create/update services already persist ``null`` in that case
(``app/services/deployments.py`` guards on ``derived_hostname is not None``).
The column has been NOT NULL since the initial revision, so that path raised
in production; the test suite could not catch it because the test schema was
built from model metadata, which declares the column nullable.

This also leaves room for headless deployments -- apps served without an
ingress -- which have no hostname by construction.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-24

"""

from alembic import op
import sqlalchemy as sa


revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "deployment",
        "hostname",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "deployment",
        "hostname",
        existing_type=sa.String(),
        nullable=False,
    )
