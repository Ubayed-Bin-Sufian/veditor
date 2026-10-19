"""Add event-scoped rooms and backfill existing talk rooms."""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "name", name="uq_rooms_event_id_name"),
    )
    op.create_index("ix_rooms_event_id", "rooms", ["event_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_rooms_event_id_name_ci "
        "ON rooms (event_id, lower(name))"
    )
    op.execute(
        "INSERT INTO rooms (event_id, name, created_at) "
        "SELECT DISTINCT ON (event_id, lower(trim(room))) event_id, trim(room), NOW() "
        "FROM talks WHERE room IS NOT NULL AND trim(room) <> '' "
        "ORDER BY event_id, lower(trim(room)), id"
    )


def downgrade() -> None:
    op.drop_index("uq_rooms_event_id_name_ci", table_name="rooms")
    op.drop_index("ix_rooms_event_id", table_name="rooms")
    op.drop_table("rooms")
