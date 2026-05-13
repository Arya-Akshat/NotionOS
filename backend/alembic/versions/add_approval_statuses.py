"""add_approval_statuses"""
revision = '1a2b3c4d5e6f'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Only adding values, no strict ENUM schema change needed for standard postgres String, but comment update
    pass

def downgrade():
    pass
