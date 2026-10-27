"""Add synthetic medication requests and local FHIR provenance."""

from alembic import op

from clinresearch.database.models import FHIRResource, MedicationRequest

revision = "0002_fhir"
down_revision = "0001_existing"
branch_labels = None
depends_on = None


def upgrade():
    MedicationRequest.__table__.create(op.get_bind(), checkfirst=True)
    FHIRResource.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Destructive downgrade is unsupported; restore a verified backup")
