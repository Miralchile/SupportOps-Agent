"""Add SupportOps API keys

Revision ID: b7f2c9e4a102
Revises: 8f6c1b2d4a91
Create Date: 2026-06-27 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7f2c9e4a102'
down_revision: Union[str, None] = '8f6c1b2d4a91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'supportops_api_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False, server_default='DashScope'),
        sa.Column('provider', sa.String(length=50), nullable=False, server_default='dashscope'),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=False, server_default='https://dashscope.aliyuncs.com/compatible-mode/v1'),
        sa.Column('model', sa.String(length=120), nullable=False, server_default='qwen-plus'),
        sa.Column('embedding_model', sa.String(length=120), nullable=False, server_default='text-embedding-v3'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_supportops_api_keys_user_id', 'supportops_api_keys', ['user_id'])
    op.create_index('idx_supportops_api_keys_provider', 'supportops_api_keys', ['provider'])
    op.create_index('idx_supportops_api_keys_is_active', 'supportops_api_keys', ['is_active'])
    op.create_index('idx_supportops_api_keys_user_provider_active', 'supportops_api_keys', ['user_id', 'provider', 'is_active'])


def downgrade() -> None:
    op.drop_index('idx_supportops_api_keys_user_provider_active', table_name='supportops_api_keys')
    op.drop_index('idx_supportops_api_keys_is_active', table_name='supportops_api_keys')
    op.drop_index('idx_supportops_api_keys_provider', table_name='supportops_api_keys')
    op.drop_index('idx_supportops_api_keys_user_id', table_name='supportops_api_keys')
    op.drop_table('supportops_api_keys')
