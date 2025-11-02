def get_api_routers():
    from .images_router import images_router
    from .users_router import users_router
    from .tierlist_router import tierlist_router
    from .groups_router import groups_router

    return [images_router, tierlist_router, users_router, groups_router]
