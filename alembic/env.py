import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv
from urllib.parse import quote_plus

from app.core.database import Base

load_dotenv()

config = context.config

fileConfig(config.config_file_name)

target_metadata = Base.metadata

user = os.getenv("DB_USER")
password = quote_plus(os.getenv("DB_PASSWORD"))
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")
db = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql://{user}:{password}@{host}:{port}/{db}"


# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
from app.core.database import Base
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.models.extracted_email import ExtractedEmail
from app.models.lead import Lead
from app.models.email_message import EmailMessage
from app.models.instagram_action import InstagramAction
from app.models.automation_job import AutomationJob
from app.models.daily_stats import DailyStats
from app.models.country_stats import CountryStats
from app.models.category_stats import CategoryStats
from app.models.channel_metrics import ChannelMetrics
from app.models.channel_social import ChannelSocialLink
from app.models.ai_usage import AIUsageLog
from app.models.system_log import SystemLog
from app.models.error_log import ErrorLog
from app.models.user import User
from app.models.user_settings import UserSettings
from app.models.email_template import EmailTemplate
from app.models.saved_filter import SavedFilter
from app.models.saved_view import SavedView
from app.models.template_usage import TemplateUsage
from app.models.target_category import TargetCategory
# --- ADD THESE NEW IMPORTS ---
from app.models.campaign import Campaign, CampaignLead, CampaignEvent
target_metadata = Base.metadata


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        {"sqlalchemy.url": DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()



if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
