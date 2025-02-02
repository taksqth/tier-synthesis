import os
from fasthtml.common import *
from fasthtml.components import Zero_md
from routers.base_layout import get_full_layout
from routers import get_api_routers
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


api_routers = get_api_routers()


def before(req, sess):
    auth = req.scope["auth"] = sess.get("auth", None)
    if not auth or auth != os.getenv("ACCESS_TOKEN"):
        return RedirectResponse("/auth", status_code=303)


bware = Beforeware(
    before,
    skip=[r"/favicon\.ico", r"/static/.*", r".*\.css", "/auth", "/terms", "/privacy"],
)


def _not_found(req, exc):
    logger.error(f"404 Not Found: {req.url.path}")
    content = Container(
        H1("404 - Page Not Found", align="center"),
        P("The page you're looking for doesn't exist.", align="center"),
        style="margin-top: 2em",
        id="main",
    )
    if htmx.request is None:
        return get_full_layout(content)
    return content


def _server_error(htmx, req, exc):
    logger.error(f"Internal Server Error: {str(exc)}")
    content = Titled(
        "500 - Internal Server Error",
        P(
            "We're experiencing some technical difficulties. Please try again later or contact support if the problem persists.",
            align="center",
        ),
        style="margin-top: 2em",
        id="main",
    )
    if htmx.request is None:
        return get_full_layout(content)
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


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("favicon.ico")


@app.get("/auth")
def auth_handler(req, sess, htmx):
    token = req.query_params.get("token")
    print(f"token: {token}")
    print(os.getenv("ACCESS_TOKEN", ""))
    if token == os.getenv("ACCESS_TOKEN", ""):
        sess["auth"] = token
        return RedirectResponse("/", status_code=303)
    content = (
        H1("Forbidden"),
        P("You are not authorized to access this page."),
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
