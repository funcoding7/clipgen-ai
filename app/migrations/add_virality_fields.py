"""Add virality and caption fields to clips table

Revision ID: add_virality_fields
Revises: 
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_virality_fields'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to clips table
    op.add_column('clips', sa.Column('virality_score', sa.Integer(), nullable=True))
    op.add_column('clips', sa.Column('hook_type', sa.String(), nullable=True))
    op.add_column('clips', sa.Column('transcript_json', sa.String(), nullable=True))
    op.add_column('clips', sa.Column('layout_type', sa.String(), nullable=True, server_default='center_crop'))


def downgrade():
    # Remove columns
    op.drop_column('clips', 'layout_type')
    op.drop_column('clips', 'transcript_json')
    op.drop_column('clips', 'hook_type')
    op.drop_column('clips', 'virality_score')
