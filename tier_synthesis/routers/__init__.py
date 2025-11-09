def get_api_routers():
    from .users_router import users_router
    from .groups_router import groups_router
    from .images_router import images_router
    from .tierlist_router import tierlist_router
    from .latent_router import latent_router
    from .profile_router import profile_router

    return [
        images_router,
        tierlist_router,
        latent_router,
        profile_router,
        users_router,
        groups_router,
    ]
