from fasthtml.common import *
from . import get_api_routers
import os


def list_item(content, action_button):
    """Create a list item article with content and action button"""
    return Article(content, action_button, cls="flex-row")


def tag(text):
    """Create a small tag badge"""
    return Small(text, cls="tag")


def get_named_routes(api_router):
    return [(route[3], route[1]) for route in api_router.routes if route[3] is not None]


def get_header(is_admin=False):

    def create_nav_link(title, page_path):
        return A(title, hx_get=page_path, hx_target="#main", hx_push_url="true")

    def should_show_router(api_router):
        is_admin_router = api_router.prefix.startswith("/admin/")
        if is_admin_router:
            return is_admin
        return api_router.show

    return Container(
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
                    if should_show_router(api_router)
                ]
            ),
        ),
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


def get_full_layout(content, htmx, is_admin=False):
    if htmx.request is None:
        return (
            Title("Tier Synthesis"),
            Header(get_header(is_admin)),
            Container(content, id="main"),
            Div(id="toast"),
            Footer(get_footer()),
            Script("""
                (function() {
                    if (window._globalHandlersRegistered) return;
                    window._globalHandlersRegistered = true;

                    document.body.addEventListener('htmx:beforeSwap', function() {
                        document.querySelectorAll('details[open]').forEach(details => {
                            details.removeAttribute('open');
                        });
                    });
                })();
            """),
        )
    return content
