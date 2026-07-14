"""Add SupportOps tables

Revision ID: 8f6c1b2d4a91
Revises: 980b32f130df
Create Date: 2026-06-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8f6c1b2d4a91'
down_revision: Union[str, None] = '980b32f130df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tickets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('instruction', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=255), nullable=False),
        sa.Column('intent', sa.String(length=255), nullable=False),
        sa.Column('response', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=False, server_default='csv'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_tickets_user_id', 'tickets', ['user_id'])
    op.create_index('idx_tickets_category', 'tickets', ['category'])
    op.create_index('idx_tickets_intent', 'tickets', ['intent'])
    op.create_index('idx_tickets_created_at', 'tickets', ['created_at'])

    op.create_table(
        'agent_traces',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('tool_name', sa.String(length=255), nullable=False),
        sa.Column('tool_input', sa.Text(), nullable=True),
        sa.Column('tool_output', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='success'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_agent_traces_user_id', 'agent_traces', ['user_id'])
    op.create_index('idx_agent_traces_session_id', 'agent_traces', ['session_id'])
    op.create_index('idx_agent_traces_created_at', 'agent_traces', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_agent_traces_created_at', table_name='agent_traces')
    op.drop_index('idx_agent_traces_session_id', table_name='agent_traces')
    op.drop_index('idx_agent_traces_user_id', table_name='agent_traces')
    op.drop_table('agent_traces')

    op.drop_index('idx_tickets_created_at', table_name='tickets')
    op.drop_index('idx_tickets_intent', table_name='tickets')
    op.drop_index('idx_tickets_category', table_name='tickets')
    op.drop_index('idx_tickets_user_id', table_name='tickets')
    op.drop_table('tickets')
