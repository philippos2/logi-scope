"""Allow explicitly recorded missing shipments, distinct from delays."""

from alembic import op
import sqlalchemy as sa

revision = "0003_missing_shipments"
down_revision = "0002_search_chunks"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(op.f("ck_shipments_status"), "shipments", type_="check")
    op.create_check_constraint(
        "status", "shipments", "status IN ('in_transit', 'delayed', 'delivered', 'missing')"
    )


def downgrade():
    # Preserve data: refuse downgrade if missing records still exist.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM shipments WHERE status = 'missing')")):
        raise RuntimeError("Resolve missing shipment records before downgrading")
    op.drop_constraint(op.f("ck_shipments_status"), "shipments", type_="check")
    op.create_check_constraint(
        "status", "shipments", "status IN ('in_transit', 'delayed', 'delivered')"
    )
