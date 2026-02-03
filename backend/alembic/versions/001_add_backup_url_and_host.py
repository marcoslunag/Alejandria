"""Add backup_url and download_host to chapters

Revision ID: 001
Revises:
Create Date: 2024-01-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add backup_url column to chapters table
    op.add_column('chapters', sa.Column('backup_url', sa.String(500), nullable=True))

    # Add download_host column to chapters table
    op.add_column('chapters', sa.Column('download_host', sa.String(50), nullable=True))


def downgrade() -> None:
    # Remove columns
    op.drop_column('chapters', 'download_host')
    op.drop_column('chapters', 'backup_url')
