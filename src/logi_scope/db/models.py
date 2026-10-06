"""Business source-of-truth models and derived RAG search chunks."""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, MetaData, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
    })


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200), index=True)
    branch: Mapped[str] = mapped_column(String(200))
    shipments: Mapped[list[Shipment]] = relationship(back_populates="customer", lazy="raise")
    inquiries: Mapped[list[Inquiry]] = relationship(back_populates="customer", lazy="raise")


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (CheckConstraint(
        "status IN ('in_transit', 'delayed', 'delivered', 'missing')", name="status"
    ),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    destination: Mapped[str] = mapped_column(String(200))
    expected_delivery_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    customer: Mapped[Customer] = relationship(back_populates="shipments", lazy="raise")
    events: Mapped[list[DeliveryEvent]] = relationship(back_populates="shipment", lazy="raise")


class DeliveryEvent(Base):
    __tablename__ = "delivery_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    incident_id: Mapped[str | None] = mapped_column(String(64), index=True)
    shipment: Mapped[Shipment] = relationship(back_populates="events", lazy="raise")


class Inquiry(Base):
    __tablename__ = "inquiries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    shipment_id: Mapped[str | None] = mapped_column(ForeignKey("shipments.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str] = mapped_column(Text)
    customer: Mapped[Customer] = relationship(back_populates="inquiries", lazy="raise")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'document' AND document_path IS NOT NULL AND inquiry_id IS NULL) OR "
            "(kind = 'inquiry' AND document_path IS NULL AND inquiry_id IS NOT NULL)", name="origin"
        ),
        CheckConstraint("chunk_number >= 0", name="number"),
        UniqueConstraint("source_key", "chunk_number", name="uq_chunks_source_number"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(32))
    document_path: Mapped[str | None] = mapped_column(String(500))
    inquiry_id: Mapped[int | None] = mapped_column(ForeignKey("inquiries.id", ondelete="CASCADE"), index=True)
    chunk_number: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    source_revision: Mapped[str] = mapped_column(String(64))
    embedding_id: Mapped[str] = mapped_column(String(300))
    reference_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
