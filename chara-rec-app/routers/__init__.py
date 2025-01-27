def get_api_routers():
    from .images_router import images_router
    from .tierlist_router import tierlist_router

    return [images_router, tierlist_router]
