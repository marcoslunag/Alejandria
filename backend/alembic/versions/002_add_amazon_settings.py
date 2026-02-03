"""Add Amazon credentials to app_settings

Revision ID: 002
Revises: 001
Create Date: 2026-01-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Amazon credentials columns to app_settings table
    op.add_column('app_settings', sa.Column('amazon_email', sa.String(255), nullable=True))
    op.add_column('app_settings', sa.Column('amazon_password', sa.String(255), nullable=True))
    op.add_column('app_settings', sa.Column('amazon_device_name', sa.String(255), nullable=True))
    op.add_column('app_settings', sa.Column('kindle_sync_method', sa.String(50), server_default='auto', nullable=True))


def downgrade() -> None:
    # Remove Amazon columns
    op.drop_column('app_settings', 'kindle_sync_method')
    op.drop_column('app_settings', 'amazon_device_name')
    op.drop_column('app_settings', 'amazon_password')
    op.drop_column('app_settings', 'amazon_email')
