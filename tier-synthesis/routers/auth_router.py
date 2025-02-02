from datetime import datetime
from fasthtml.common import *
from fasthtml.oauth import OAuth, DiscordAppClient
from dataclasses import dataclass
from .base_layout import get_full_layout


ar_auth = APIRouter(prefix="/auth")
ar_auth.name = "Auth"

@ar_auth.get("/discord")
def get_discord_login(request: Request):