import os
from fasthtml.common import *
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


bware = Beforeware(before, skip=[r"/favicon\.ico", r"/static/.*", r".*\.css", "/auth"])


def _not_found(req, exc):
    content = Container(
        H1("404 - Page Not Found", align="center"),
        P("The page you're looking for doesn't exist.", align="center"),
        style="margin-top: 2em",
    )
    return Titled("Not Found", content)


app, rt = fast_app(
    hdrs=(picolink,),
    before=bware,
    exception_handlers={404: _not_found},
    debug=os.environ.get("DEBUG", "false").lower() == "true",
)
for router in get_api_routers():
    router.to_app(app)


@app.get("/auth")
def auth_handler(req, sess):
    token = req.query_params.get("token")
    print(f"token: {token}")
    print(os.getenv("ACCESS_TOKEN", ""))
    if token == os.getenv("ACCESS_TOKEN", ""):
        sess["auth"] = token
        return RedirectResponse("/", status_code=303)
    return Titled(
        "Forbidden",
        P("You are not authorized to access this page."),
    )


@app.get("/")
def get_home(htmx):
    content = Container(
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
    if htmx.request is None:
        return get_full_layout(content)
    return content


@app.get("/health")
def health_check():
    return "OK"


if __name__ == "__main__":
    serve()
