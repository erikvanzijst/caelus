"""An account's SSH public keys — owned by a user, scoped to no deployment.

Nothing consumes these rows yet; see the `account-ssh-keys` design doc.
"""

from datetime import datetime
from typing import Optional

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, ForeignKey, Index, Integer, SmallInteger, String, Text

from app.models.core import _utcnow


class SshKeyORM(SQLModel, table=True):
    __tablename__ = "user_ssh_key"
    __table_args__ = (
        # Uniqueness rides on the fingerprint rather than on `public_key`
        # itself: it is the same guarantee (a digest of that blob) at a fixed
        # 50 characters, and a btree over the blob would exceed its 2704-byte
        # row ceiling at RSA-16384.
        Index("uq_user_ssh_key_fingerprint", "user_id", "fingerprint", unique=True),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    key_type: str = Field(sa_column=Column(String(64), nullable=False))
    # `<type> <base64 blob>`, comment stripped.
    public_key: str = Field(sa_column=Column(Text(), nullable=False))
    fingerprint: str = Field(sa_column=Column(String(64), nullable=False))
    bits: int = Field(sa_column=Column(SmallInteger, nullable=False))
    label: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class SshKeyCreate(SQLModel):
    """The entire client-supplied input to registering a key."""

    model_config = ConfigDict(extra="forbid")

    public_key: str
    label: Optional[str] = None


class SshKeyRead(SQLModel):
    """One registered key, in the single representation every read returns."""

    fingerprint: str
    key_type: str
    bits: int
    label: Optional[str] = None
    public_key: str
    created_at: datetime
