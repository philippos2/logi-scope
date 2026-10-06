"""Delivery update idempotency and a separate limited writer role."""

from alembic import op
import sqlalchemy as sa

revision = '0004_delivery_updates'
down_revision = '0003_missing_shipments'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    sa.Sequence('delivery_events_id_seq', start=1000000).create(bind)
    op.alter_column('delivery_events', 'id', server_default=sa.text("nextval('delivery_events_id_seq')"))
    op.add_column('delivery_events', sa.Column('event_key', sa.String(36), nullable=True))
    op.add_column('delivery_events', sa.Column('reported_status', sa.String(32), nullable=True))
    op.create_unique_constraint('uq_delivery_events_event_key', 'delivery_events', ['event_key'])
    op.create_check_constraint('reported_status', 'delivery_events', "reported_status IS NULL OR reported_status IN ('in_transit', 'delayed', 'delivered', 'missing')")
    op.execute('CREATE ROLE logi_scope_updater LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
    op.execute('GRANT USAGE ON SCHEMA public TO logi_scope_updater')
    op.execute('GRANT SELECT ON shipments, delivery_events TO logi_scope_updater')
    op.execute('GRANT UPDATE (status) ON shipments TO logi_scope_updater')
    op.execute('GRANT INSERT ON delivery_events TO logi_scope_updater')
    op.execute('GRANT USAGE ON SEQUENCE delivery_events_id_seq TO logi_scope_updater')


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM delivery_events WHERE event_key IS NOT NULL)")):
        raise RuntimeError("Remove update-demo events before downgrading")
    op.execute('REVOKE ALL ON shipments, delivery_events FROM logi_scope_updater')
    op.execute('REVOKE ALL ON SEQUENCE delivery_events_id_seq FROM logi_scope_updater')
    op.execute('REVOKE ALL ON SCHEMA public FROM logi_scope_updater')
    op.execute('DROP ROLE logi_scope_updater')
    op.drop_constraint(op.f('ck_delivery_events_reported_status'), 'delivery_events', type_='check')
    op.drop_constraint('uq_delivery_events_event_key', 'delivery_events', type_='unique')
    op.drop_column('delivery_events', 'reported_status')
    op.drop_column('delivery_events', 'event_key')
    op.alter_column('delivery_events', 'id', server_default=None)
    sa.Sequence('delivery_events_id_seq').drop(op.get_bind())
