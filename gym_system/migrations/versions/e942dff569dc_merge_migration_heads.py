"""Merge migration heads

Revision ID: e942dff569dc
Revises: 0f70844f6ff9, 9f9885da6eef
Create Date: 2026-04-28 10:28:04.149897

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e942dff569dc'
down_revision = ('0f70844f6ff9', '9f9885da6eef')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
