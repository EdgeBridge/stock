"""Add highest_price partial_profit_taken and usd_krw_rate columns

Revision ID: 607feca4f8b7
Revises: cfbdf0cd6e1f
Create Date: 2026-03-26 14:54:40.909550

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '607feca4f8b7'
down_revision: Union[str, Sequence[str], None] = 'cfbdf0cd6e1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    STOCK-58: Add columns to support:
    1. Persistent highest_price tracking across restarts
    2. Partial profit taking flag to prevent duplicate sells
    3. Historical exchange rates in portfolio snapshots
    """
    # Add columns to positions table
    op.add_column('positions', sa.Column('highest_price', sa.Float(), nullable=True))
    op.add_column(
        'positions',
        sa.Column(
            'partial_profit_taken',
            sa.Boolean(),
            nullable=False,
            server_default=False,
        ),
    )

    # Add usd_krw_rate to portfolio_snapshots table
    op.add_column(
        'portfolio_snapshots', sa.Column('usd_krw_rate', sa.Float(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove columns from positions table
    op.drop_column('positions', 'partial_profit_taken')
    op.drop_column('positions', 'highest_price')

    # Remove usd_krw_rate from portfolio_snapshots table
    op.drop_column('portfolio_snapshots', 'usd_krw_rate')
