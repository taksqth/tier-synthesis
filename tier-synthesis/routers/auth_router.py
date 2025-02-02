import logging
from datetime import datetime
from fasthtml.common import *
from fasthtml.oauth import OAuth, DiscordAppClient
from dataclasses import dataclass
from .base_layout import get_full_layout

logger = logging.getLogger(__name__)


ar_auth = APIRouter(prefix="/auth")
ar_auth.name = "Auth"


@ar_auth.get("/discord")
def get_discord_login(request: Request):
    client = DiscordAppClient(
        client_id=os.environ.get("DISCORD_CLIENT_ID"),
        client_secret=os.environ.get("DISCORD_CLIENT_SECRET"),
    )
