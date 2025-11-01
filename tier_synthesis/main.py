import os
from fasthtml.common import *
from fasthtml.oauth import DiscordAppClient
from fasthtml.components import Zero_md
from routers.base_layout import get_full_layout
from routers import get_api_routers
import logging
import httpx

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


api_routers = get_api_routers()


class User:
    id: str
    authorized: bool
    username: str
    avatar: str


db = database(os.environ.get("DB_PATH", "app/database.db"))
users = db.create(
    User,
    pk="id",
    transform=True,
)


def before(req, session):
    auth = req.scope["auth"] = session.get("user_id", None)
    if not auth:
        return RedirectResponse("/login", status_code=303)
    elif not users[auth].authorized and auth != os.environ.get("ADMIN_USER_ID"):
        return RedirectResponse("/unauthorized", status_code=303)


bware = Beforeware(
    before,
    skip=[
        r"/favicon\.ico",
        r"/static/.*",
        r".*\.css",
        "/login",
        "/terms",
        "/privacy",
        "/auth_redirect",
        "/unauthorized",
    ],
)


def _not_found(req, exc):
    logger.error(f"404 Not Found: {req.url.path}")
    content = Titled(
        H1("404 - Page Not Found", align="center"),
        P("The page you're looking for doesn't exist.", align="center"),
        style="margin-top: 2em",
    )
    return content


def _server_error(req, exc):
    logger.error(f"Internal Server Error: {str(exc)}")
    content = Titled(
        "500 - Internal Server Error",
        P(
            "We're experiencing some technical difficulties. Please try again later or contact support if the problem persists.",
            align="center",
        ),
        style="margin-top: 2em",
    )
    return content


app, rt = fast_app(
    hdrs=(
        picolink,
        [Script(type="module", src="https://cdn.jsdelivr.net/npm/zero-md@3?register")],
    ),
    before=bware,
    exception_handlers={404: _not_found, 500: _server_error},
    debug=os.environ.get("DEBUG", "false").lower() == "true",
)

for router in get_api_routers():
    router.to_app(app)


def get_discord_client():
    client_id = os.environ.get("DISCORD_CLIENT_ID")
    client_secret = os.environ.get("DISCORD_CLIENT_SECRET")
    if not client_id or not client_secret:
        missing_vars = []
        if not client_id:
            missing_vars.append("DISCORD_CLIENT_ID")
        if not client_secret:
            missing_vars.append("DISCORD_CLIENT_SECRET")
        raise HTTPException(
            status_code=500,
            detail=f"Missing required environment variables: {', '.join(missing_vars)}",
        )
    return DiscordAppClient(
        client_id=client_id, client_secret=client_secret, scope="identify"
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("favicon.ico")


@app.get("/login")
def login(htmx):
    client = get_discord_client()
    login_link = client.login_link(redirect_uri=os.environ.get("DISCORD_REDIRECT_URI"))
    logging.debug(f"Generated Discord login link: {login_link}")
    content = P(A("Login with Discord", href=login_link), align="center")
    return get_full_layout(content, htmx)


@app.get("/logout")
def logout(session):
    session.pop("user_id", None)
    return RedirectResponse("/login", status_code=303)


@app.get("/auth_redirect")
async def auth_redirect(code: str, session):
    client = get_discord_client()
    client.parse_response(code)
    token = client.token["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_data = httpx.get(
        "https://discord.com/api/v10/users/@me", headers=headers
    ).json()
    session["user_id"] = user_data["id"]
    if user_data["id"] not in users:
        users.insert(
            User(
                id=user_data["id"],
                authorized=False,
                username=user_data["username"],
                avatar=user_data["avatar"],
            )
        )
    return RedirectResponse("/", status_code=303)


@app.get("/unauthorized")
def unauthorized(htmx):
    content = P(
        "You are not authorized to access this resource. Please contact an administrator."
    )
    return get_full_layout(content, htmx)


@app.get("/")
def get_home(htmx):
    content = (
        H1("Welcome to TierSynthesis"),
        P(
            "Create, share, and analyze character tier lists collaboratively. ",
            "Discover patterns in character preferences and find like-minded fans.",
        ),
        Div(
            A(
                "Create New Tier List",
                hx_get="/tierlist/edit",
                hx_target="#main",
                hx_push_url="true",
                cls="button",
            ),
            style="text-align: center; margin-top: 2em;",
        ),
    )
    return get_full_layout(content, htmx)


@app.get("/health")
def health_check():
    return "OK"


@app.get("/privacy")
def get_privacy(htmx):
    with open("docs/privacy.md") as f:
        md_content = f.read()
    css_template = Template(Style(""), data_append=True)
    content = (
        H1("Privacy Policy"),
        Zero_md(css_template, Script(md_content, type="text/markdown")),
    )
    return get_full_layout(content, htmx)


@app.get("/terms")
def get_privacy(htmx):
    with open("docs/terms.md") as f:
        md_content = f.read()
    css_template = Template(Style(""), data_append=True)
    content = (
        H1("Terms of Service"),
        Zero_md(css_template, Script(md_content, type="text/markdown")),
    )
    return get_full_layout(content, htmx)


if __name__ == "__main__":
    serve()
