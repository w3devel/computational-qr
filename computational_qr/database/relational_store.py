"""Relational persistence layer for QR codes using SQLAlchemy 2.x.

Supports both **SQLite** (portable, file-based or in-memory) and **PostgreSQL**
(server-side).  Use ``RelationalQRStore`` as a context manager for automatic
session lifecycle management.

Example – SQLite::

    from computational_qr.database import RelationalQRStore
    from computational_qr.core import QRData, PayloadType

    data = QRData(PayloadType.TEXT, "hello world")

    with RelationalQRStore("sqlite:///qr.db") as store:
        record = store.store_qr(data)
        png = store.get_png(record.id)

Example – PostgreSQL::

    with RelationalQRStore("postgresql+psycopg://user:pw@localhost/qrdb") as store:
        record = store.store_qr(data)
"""

from __future__ import annotations

import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    LargeBinary,
    String,
    Text,
    DateTime,
    ForeignKey,
    Integer,
    select,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    Session,
)
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy import create_engine as _sa_create_engine
from sqlalchemy import Engine


# ---------------------------------------------------------------------------
# Custom UUID type that works for both SQLite (CHAR 36) and PostgreSQL (native)
# ---------------------------------------------------------------------------

class UUIDType(TypeDecorator):
    """Platform-independent UUID type.

    Stores as a native UUID on PostgreSQL and as a 36-character CHAR string
    on other databases (e.g. SQLite).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            try:
                from sqlalchemy.dialects.postgresql import UUID as PG_UUID
                return dialect.type_descriptor(PG_UUID(as_uuid=True))
            except ImportError:
                pass
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value) if isinstance(value, uuid.UUID) else str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


# ---------------------------------------------------------------------------
# ORM declarative base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QRCodeRow(Base):
    """SQLAlchemy ORM model for the ``qr_codes`` table."""

    __tablename__ = "qr_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(), primary_key=True, default=uuid.uuid4
    )
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    payload_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    qr_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    artifact: Mapped["QRArtifactRow | None"] = relationship(
        "QRArtifactRow",
        back_populates="qr_code",
        uselist=False,
        cascade="all, delete-orphan",
    )


class QRArtifactRow(Base):
    """SQLAlchemy ORM model for the ``qr_artifacts`` table (1:1 with qr_codes)."""

    __tablename__ = "qr_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    qr_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(), ForeignKey("qr_codes.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    png_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    svg_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    render_spec: Mapped[str | None] = mapped_column(Text, nullable=True)
    rendered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    qr_code: Mapped["QRCodeRow"] = relationship("QRCodeRow", back_populates="artifact")


# ---------------------------------------------------------------------------
# Domain objects returned to the caller
# ---------------------------------------------------------------------------

@dataclass
class QRRecord:
    """A stored QR code record, including optional pre-rendered artifacts.

    Parameters
    ----------
    id:
        UUID primary key.
    fingerprint:
        SHA-256-derived short fingerprint from :meth:`~QRData.fingerprint`.
    payload_type:
        String label of the payload type.
    qr_data:
        The deserialised :class:`~computational_qr.core.qr_encoder.QRData`.
    created_at / updated_at:
        UTC timestamps.
    png_bytes:
        Pre-rendered PNG artifact, or ``None`` if not yet rendered.
    svg_text:
        Pre-rendered SVG artifact, or ``None`` if not yet rendered.
    render_spec:
        JSON-encoded render parameters used when artifacts were generated.
    """

    id: uuid.UUID
    fingerprint: str
    payload_type: str
    qr_data: Any  # QRData – avoid circular import in type annotation
    created_at: datetime
    updated_at: datetime
    png_bytes: bytes | None = None
    svg_text: str | None = None
    render_spec: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# RelationalQRStore
# ---------------------------------------------------------------------------

class RelationalQRStore:
    """Relational persistence layer for QR codes.

    Supports **SQLite** (default, portable) and **PostgreSQL**.

    Parameters
    ----------
    database_url:
        SQLAlchemy database URL, e.g. ``"sqlite:///qr.db"`` or
        ``"postgresql+psycopg://user:pw@localhost/qrdb"``.
    echo:
        If ``True``, log all SQL statements (useful for debugging).
    """

    def __init__(self, database_url: str = "sqlite:///:memory:", echo: bool = False) -> None:
        self.database_url = database_url
        self._echo = echo
        self._engine: Engine | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "RelationalQRStore":
        """Create the engine and ensure all tables exist."""
        try:
            import sqlalchemy  # noqa: F401  (validate importable)
        except ImportError as exc:
            raise ImportError(
                "SQLAlchemy is required. Install it with: pip install sqlalchemy>=2.0"
            ) from exc
        self._engine = _sa_create_engine(self.database_url, echo=self._echo)
        Base.metadata.create_all(self._engine)
        return self

    def create_schema(self) -> None:
        """Idempotently create all tables (equivalent to ``metadata.create_all``).

        Useful when you want to manage the schema explicitly (e.g. after running
        Alembic migrations to a specific revision) without re-creating the engine.
        Unlike :meth:`connect`, this method does **not** create the engine; call
        :meth:`connect` first.
        """
        if self._engine is None:
            raise RuntimeError("Call connect() before create_schema().")
        Base.metadata.create_all(self._engine)

    def close(self) -> None:
        """Dispose the engine and release all connections."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> "RelationalQRStore":
        return self.connect()

    def __exit__(self, *args) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session(self) -> Session:
        if self._engine is None:
            raise RuntimeError(
                "Store is not connected. Use 'with RelationalQRStore(...) as store:' "
                "or call connect() first."
            )
        return Session(self._engine)

    @staticmethod
    def _render_png(qr_data, encoder_kwargs: dict) -> bytes:
        """Render *qr_data* to PNG bytes using :class:`~QREncoder`."""
        from computational_qr.core.qr_encoder import QREncoder

        enc = QREncoder(
            error_correction=encoder_kwargs.get("error_correction", "M"),
            box_size=encoder_kwargs.get("box_size", 10),
            border=encoder_kwargs.get("border", 4),
        )
        fill = encoder_kwargs.get("fill_color", "black")
        back = encoder_kwargs.get("back_color", "white")
        img = enc.encode_image(qr_data, fill_color=fill, back_color=back)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def _render_svg(qr_data, encoder_kwargs: dict) -> str:
        """Render *qr_data* to an SVG string."""
        from computational_qr.core.qr_encoder import QREncoder

        enc = QREncoder(
            error_correction=encoder_kwargs.get("error_correction", "M"),
            box_size=encoder_kwargs.get("box_size", 10),
            border=encoder_kwargs.get("border", 4),
        )
        return enc.encode_svg(qr_data)

    @staticmethod
    def _row_to_record(row: QRCodeRow) -> QRRecord:
        from computational_qr.core.qr_encoder import QRData

        qr_data = QRData.from_json(row.qr_json)
        artifact = row.artifact
        png = artifact.png_bytes if artifact else None
        svg = artifact.svg_text if artifact else None
        spec: dict = {}
        if artifact and artifact.render_spec:
            try:
                spec = json.loads(artifact.render_spec)
            except (json.JSONDecodeError, TypeError):
                spec = {}
        return QRRecord(
            id=row.id,
            fingerprint=row.fingerprint,
            payload_type=row.payload_type,
            qr_data=qr_data,
            created_at=row.created_at,
            updated_at=row.updated_at,
            png_bytes=png,
            svg_text=svg,
            render_spec=spec,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_qr(
        self,
        qr_data,
        qr_id: uuid.UUID | None = None,
        render_png: bool = True,
        render_svg: bool = True,
        fill_color: str = "black",
        back_color: str = "white",
        error_correction: str = "M",
        box_size: int = 10,
        border: int = 4,
    ) -> QRRecord:
        """Persist *qr_data* and (optionally) pre-render PNG/SVG artifacts.

        If a record with the same fingerprint already exists it is updated
        in place and artifacts are re-rendered when requested.

        Parameters
        ----------
        qr_data:
            A :class:`~computational_qr.core.qr_encoder.QRData` envelope.
        qr_id:
            Explicit UUID for the new record.  Auto-generated if omitted.
        render_png:
            Whether to render and store a PNG artifact.
        render_svg:
            Whether to render and store an SVG artifact.
        fill_color / back_color:
            QR module colours (passed to :meth:`~QREncoder.encode_image`).
        error_correction / box_size / border:
            Encoding parameters forwarded to :class:`~QREncoder`.

        Returns
        -------
        QRRecord
            The persisted record including any rendered artifacts.
        """
        encoder_kwargs: dict[str, Any] = {
            "fill_color": fill_color,
            "back_color": back_color,
            "error_correction": error_correction,
            "box_size": box_size,
            "border": border,
        }

        fp = qr_data.fingerprint()
        qr_json = qr_data.to_json()
        payload_type = qr_data.payload_type.value

        png_bytes: bytes | None = None
        svg_text: str | None = None

        if render_png:
            png_bytes = self._render_png(qr_data, encoder_kwargs)
        if render_svg:
            svg_text = self._render_svg(qr_data, encoder_kwargs)

        render_spec_str = json.dumps(encoder_kwargs)
        now = _utcnow()

        with self._session() as session:
            # Look for an existing record with the same fingerprint
            stmt = select(QRCodeRow).where(QRCodeRow.fingerprint == fp)
            existing = session.scalars(stmt).first()

            if existing is not None:
                existing.qr_json = qr_json
                existing.payload_type = payload_type
                existing.updated_at = now

                if render_png or render_svg:
                    if existing.artifact is None:
                        artifact = QRArtifactRow(
                            qr_id=existing.id,
                            png_bytes=png_bytes,
                            svg_text=svg_text,
                            render_spec=render_spec_str,
                            rendered_at=now,
                        )
                        session.add(artifact)
                    else:
                        if render_png:
                            existing.artifact.png_bytes = png_bytes
                        if render_svg:
                            existing.artifact.svg_text = svg_text
                        existing.artifact.render_spec = render_spec_str
                        existing.artifact.rendered_at = now

                session.commit()
                session.refresh(existing)
                if existing.artifact:
                    session.refresh(existing.artifact)
                return self._row_to_record(existing)

            # Create a new record
            row_id = qr_id or uuid.uuid4()
            row = QRCodeRow(
                id=row_id,
                fingerprint=fp,
                payload_type=payload_type,
                qr_json=qr_json,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()  # get row.id assigned

            if render_png or render_svg:
                artifact = QRArtifactRow(
                    qr_id=row.id,
                    png_bytes=png_bytes,
                    svg_text=svg_text,
                    render_spec=render_spec_str,
                    rendered_at=now,
                )
                session.add(artifact)

            session.commit()
            session.refresh(row)
            if row.artifact:
                session.refresh(row.artifact)
            return self._row_to_record(row)

    def get_qr(self, qr_id: uuid.UUID) -> QRRecord | None:
        """Retrieve a :class:`QRRecord` by its UUID primary key.

        Returns ``None`` if not found.
        """
        with self._session() as session:
            row = session.get(QRCodeRow, qr_id)
            if row is None:
                return None
            return self._row_to_record(row)

    def get_by_fingerprint(self, fingerprint: str) -> QRRecord | None:
        """Retrieve a :class:`QRRecord` by its short fingerprint.

        Returns ``None`` if not found.
        """
        with self._session() as session:
            stmt = select(QRCodeRow).where(QRCodeRow.fingerprint == fingerprint)
            row = session.scalars(stmt).first()
            if row is None:
                return None
            return self._row_to_record(row)

    def get_png(self, qr_id: uuid.UUID) -> bytes | None:
        """Return the pre-rendered PNG bytes for *qr_id*, or ``None``."""
        with self._session() as session:
            row = session.get(QRCodeRow, qr_id)
            if row is None or row.artifact is None:
                return None
            return row.artifact.png_bytes

    def get_svg(self, qr_id: uuid.UUID) -> str | None:
        """Return the pre-rendered SVG string for *qr_id*, or ``None``."""
        with self._session() as session:
            row = session.get(QRCodeRow, qr_id)
            if row is None or row.artifact is None:
                return None
            return row.artifact.svg_text

    def list_qr(
        self,
        limit: int = 100,
        offset: int = 0,
        payload_type: str | None = None,
    ) -> list[QRRecord]:
        """List stored QR records, optionally filtered by *payload_type*.

        Parameters
        ----------
        limit:
            Maximum number of results to return (default 100).
        offset:
            Number of records to skip (for pagination).
        payload_type:
            If provided, only records whose ``payload_type`` matches are
            returned (e.g. ``"text"``, ``"prolog"``).
        """
        with self._session() as session:
            stmt = select(QRCodeRow).order_by(QRCodeRow.created_at)
            if payload_type is not None:
                stmt = stmt.where(QRCodeRow.payload_type == payload_type)
            stmt = stmt.offset(offset).limit(limit)
            rows = session.scalars(stmt).all()
            return [self._row_to_record(r) for r in rows]

    def delete_qr(self, qr_id: uuid.UUID) -> bool:
        """Delete the record with *qr_id* (and its artifact).

        Returns ``True`` if a record was deleted, ``False`` if not found.
        """
        with self._session() as session:
            row = session.get(QRCodeRow, qr_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
