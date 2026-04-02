"""Add login attempt model

Revision ID: add_login_attempt
Revises: 1750d7a0b4a5
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_login_attempt'
down_revision = '1750d7a0b4a5'
branch_labels = None
depends_on = None


def upgrade():
    # Create login_attempt table
    op.create_table('login_attempt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('last_attempt_time', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ip_address')
    )


def downgrade():
    # Drop login_attempt table
    op.drop_table('login_attempt')
