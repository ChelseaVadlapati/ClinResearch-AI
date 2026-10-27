"""Adopt the existing normalized schema without deleting data."""

from alembic import op
from sqlalchemy import inspect

from clinresearch.database.models import Base

revision = "0001_existing"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = inspect(connection)
    names = {"patients", "encounters", "conditions", "observations", "import_runs", "rejected_rows"}
    for table in Base.metadata.sorted_tables:
        if table.name not in names:
            continue
        if inspector.has_table(table.name):
            columns = {column["name"] for column in inspector.get_columns(table.name)}
            if columns != set(table.columns.keys()):
                raise RuntimeError(f"Existing table {table.name} needs manual schema review")
        else:
            table.create(connection)


def downgrade():
    raise RuntimeError("Destructive downgrade is unsupported; restore a verified backup")
