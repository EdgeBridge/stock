"""initial schema

Revision ID: cfbdf0cd6e1f
Revises:
Create Date: 2026-03-07 01:19:15.403224

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'cfbdf0cd6e1f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('exchange', sa.String(10), nullable=False, server_default='NASD'),
        sa.Column('side', sa.String(4), nullable=False),
        sa.Column('order_type', sa.String(10), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('price', sa.Float()),
        sa.Column('filled_quantity', sa.Float(), server_default='0'),
        sa.Column('filled_price', sa.Float()),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('strategy_name', sa.String(50)),
        sa.Column('kis_order_id', sa.String(50)),
        sa.Column('pnl', sa.Float()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('filled_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_orders_symbol', 'orders', ['symbol'])
    op.create_index('idx_orders_created', 'orders', ['created_at'])
    op.create_index('idx_orders_status', 'orders', ['status'])

    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('exchange', sa.String(10), nullable=False, server_default='NASD'),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('avg_price', sa.Float(), nullable=False),
        sa.Column('current_price', sa.Float()),
        sa.Column('unrealized_pnl', sa.Float()),
        sa.Column('stop_loss', sa.Float()),
        sa.Column('take_profit', sa.Float()),
        sa.Column('trailing_stop', sa.Float()),
        sa.Column('strategy_name', sa.String(50)),
        sa.Column('opened_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol'),
    )
    op.create_index('idx_positions_symbol', 'positions', ['symbol'])

    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('total_value_usd', sa.Float(), nullable=False),
        sa.Column('cash_usd', sa.Float(), nullable=False),
        sa.Column('invested_usd', sa.Float(), nullable=False),
        sa.Column('realized_pnl', sa.Float()),
        sa.Column('unrealized_pnl', sa.Float()),
        sa.Column('daily_pnl', sa.Float()),
        sa.Column('drawdown_pct', sa.Float()),
        sa.Column('recorded_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_snapshots_recorded', 'portfolio_snapshots', ['recorded_at'])

    op.create_table(
        'strategy_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('strategy_name', sa.String(50), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('signal_type', sa.String(10), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('indicators', JSONB()),
        sa.Column('market_state', sa.String(20)),
        sa.Column('created_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_strategy_logs_created', 'strategy_logs', ['created_at'])

    op.create_table(
        'scanner_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('scan_type', sa.String(30), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('exchange', sa.String(10)),
        sa.Column('score', sa.Float()),
        sa.Column('details', JSONB()),
        sa.Column('created_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_scanner_created', 'scanner_results', ['created_at'])

    op.create_table(
        'sector_analysis',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sector_code', sa.String(10), nullable=False),
        sa.Column('sector_name', sa.String(30), nullable=False),
        sa.Column('strength_score', sa.Float()),
        sa.Column('return_1w', sa.Float()),
        sa.Column('return_1m', sa.Float()),
        sa.Column('return_3m', sa.Float()),
        sa.Column('trend', sa.String(10)),
        sa.Column('created_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'agent_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('agent_type', sa.String(30), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', JSONB()),
        sa.Column('created_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('severity', sa.String(10), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', JSONB()),
        sa.Column('created_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'backtest_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('config', JSONB(), nullable=False),
        sa.Column('metrics', JSONB(), nullable=False),
        sa.Column('trades', JSONB()),
        sa.Column('equity_curve', JSONB()),
        sa.Column('created_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'watchlist',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('exchange', sa.String(10), nullable=False, server_default='NASD'),
        sa.Column('name', sa.String(100)),
        sa.Column('sector', sa.String(30)),
        sa.Column('market_cap', sa.BigInteger()),
        sa.Column('source', sa.String(20)),
        sa.Column('score', sa.Float()),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('added_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol'),
    )
    op.create_index('idx_watchlist_active', 'watchlist', ['is_active'])


def downgrade() -> None:
    op.drop_table('watchlist')
    op.drop_table('backtest_results')
    op.drop_table('events')
    op.drop_table('agent_logs')
    op.drop_table('sector_analysis')
    op.drop_table('scanner_results')
    op.drop_table('strategy_logs')
    op.drop_table('portfolio_snapshots')
    op.drop_table('positions')
    op.drop_table('orders')
