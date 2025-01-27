from fasthtml.common import *
from . import get_api_routers


def get_named_routes(api_router):
    return [(route[3], route[1]) for route in api_router.routes if route[3] is not None]


def Navbar():
    def create_nav_link(title, page_path):
        return A(title, hx_get=page_path, hx_target="#main", hx_push_url="true")

    return Nav(
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
            ]
        ),
    )


def get_full_layout(content):
    return Titled(
        "Image Gallery App",
        Navbar(),
        Main(content, cls="container", id="main"),
    )
