"""Derived vector index and restricted ingest credentials."""

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0002_search_chunks"
down_revision = "0001_business_data"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_key", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("document_path", sa.String(500)),
        sa.Column("inquiry_id", sa.Integer(), sa.ForeignKey("inquiries.id", ondelete="CASCADE")),
        sa.Column("chunk_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_revision", sa.String(64), nullable=False),
        sa.Column("embedding_id", sa.String(300), nullable=False),
        sa.Column("reference_ids", ARRAY(sa.String(64)), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.CheckConstraint(
            "(kind = 'document' AND document_path IS NOT NULL AND inquiry_id IS NULL) OR "
            "(kind = 'inquiry' AND document_path IS NULL AND inquiry_id IS NOT NULL)", name="origin"),
        sa.CheckConstraint("chunk_number >= 0", name="number"),
        sa.UniqueConstraint("source_key", "chunk_number", name="uq_chunks_source_number"),
    )
    op.create_index("ix_chunks_inquiry_id", "chunks", ["inquiry_id"])
    op.execute("GRANT SELECT ON chunks TO logi_scope_reader")
    op.execute("CREATE ROLE logi_scope_ingest LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS")
    op.execute("GRANT USAGE ON SCHEMA public TO logi_scope_ingest")
    op.execute("GRANT SELECT ON inquiries TO logi_scope_ingest")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON chunks TO logi_scope_ingest")


def downgrade():
    op.drop_table("chunks")
    op.execute("REVOKE SELECT ON inquiries FROM logi_scope_ingest")
    op.execute("REVOKE USAGE ON SCHEMA public FROM logi_scope_ingest")
    op.execute("DROP ROLE logi_scope_ingest")
