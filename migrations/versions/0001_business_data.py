"""Business source-of-truth tables, vector extension and reader permissions."""

from alembic import op
import sqlalchemy as sa

revision = "0001_business_data"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("branch", sa.String(200), nullable=False),
    )
    op.create_index("ix_customers_name", "customers", ["name"])
    op.create_table(
        "shipments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("destination", sa.String(200), nullable=False),
        sa.Column("expected_delivery_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('in_transit', 'delayed', 'delivered')", name="status"),
    )
    op.create_index("ix_shipments_customer_id", "shipments", ["customer_id"])
    op.create_table(
        "delivery_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("shipment_id", sa.String(64), sa.ForeignKey("shipments.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("incident_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_delivery_events_shipment_id", "delivery_events", ["shipment_id"])
    op.create_index("ix_delivery_events_incident_id", "delivery_events", ["incident_id"])
    op.create_table(
        "inquiries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("shipment_id", sa.String(64), sa.ForeignKey("shipments.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
    )
    op.create_index("ix_inquiries_customer_id", "inquiries", ["customer_id"])
    op.create_index("ix_inquiries_shipment_id", "inquiries", ["shipment_id"])
    op.execute("CREATE ROLE logi_scope_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS")
    op.execute("ALTER ROLE logi_scope_reader SET default_transaction_read_only = on")
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO logi_scope_reader")
    op.execute("GRANT SELECT ON customers, shipments, delivery_events, inquiries TO logi_scope_reader")


def downgrade():
    for table in ("inquiries", "delivery_events", "shipments", "customers"):
        op.drop_table(table)
    op.execute("REVOKE USAGE ON SCHEMA public FROM logi_scope_reader")
    op.execute("DROP ROLE logi_scope_reader")
    # Do not drop the extension: other tables may depend on it.
