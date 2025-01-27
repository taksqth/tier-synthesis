import os
from fasthtml.common import *
from routers.base_layout import get_full_layout
from routers import get_api_routers

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


app, rt = fast_app(hdrs=(picolink,), before=bware, exception_handlers={404: _not_found})
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
        H1("Welcome to Image Gallery"),
        P("A simple image gallery application built with FastHTML"),
    )
    if htmx.request is None:
        return get_full_layout(content)
    return content


if __name__ == "__main__":
    serve()
