from fasthtml.common import *
from . import get_api_routers


def get_named_routes(api_router):
    return [(route[3], route[1]) for route in api_router.routes if route[3] is not None]


def get_header():
    def create_nav_link(title, page_path):
        return A(title, hx_get=page_path, hx_target="#main", hx_push_url="true")

    return Div(
        Nav(
            Ul(Li(Strong(A("Home", href="/")))),
            Ul(
                *[
                    Li(
                        Details(
                            Summary(api_router.name),
                            Ul(
                                *[
                                    Li(create_nav_link(name, url))
                                    for name, url in get_named_routes(api_router)
                                ]
                            ),
                            cls="dropdown",
                        )
                    )
                    for api_router in get_api_routers()
                    if api_router.show
                ]
            ),
        ),
        cls="container",
    )


def get_footer():
    return Container(
        Section(
            Nav(
                Ul(
                    Li(A("Privacy Policy", cls="secondary", href="/privacy")),
                    Li(A("Terms of Service", cls="secondary", href="/terms")),
                ),
                cls="links",
            )
        ),
        Section(
            P(
                "Code licensed ",
                A(
                    "MIT",
                    cls="secondary",
                    href="https://github.com/taksqth/tier-synthesis/blob/main/LICENSE",
                ),
                ".",
            ),
            P("Currently v0.1.0"),
        ),
    )


def get_full_layout(content, htmx):
    if htmx.request is None:
        return (
            Title("Tier Synthesis"),
            Header(get_header()),
            Container(content, id="main"),
            Footer(get_footer()),
        )
    return content
