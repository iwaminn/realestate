"""add update_listing_status_after_scraping to scraping_schedules

Revision ID: add_listing_status_opt
Revises: 298941651329
Create Date: 2025-10-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_listing_status_opt'
down_revision = '298941651329'
branch_labels = None
depends_on = None


def upgrade():
    # scraping_schedulesテーブルにupdate_listing_status_after_scrapingカラムを追加
    op.add_column('scraping_schedules', sa.Column('update_listing_status_after_scraping', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    # カラムを削除
    op.drop_column('scraping_schedules', 'update_listing_status_after_scraping')
