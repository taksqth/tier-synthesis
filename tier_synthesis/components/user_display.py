from fasthtml.common import *  # type: ignore


def UserDisplay(owner_id: str, viewer_id: str | None, clickable: bool = True) -> Any:
    """Render user avatar and name, optionally with profile link."""
    from routers.users_router import get_user_avatar, users_share_group

    username, avatar_url = get_user_avatar(owner_id)
    can_view_profile = clickable and viewer_id and users_share_group(viewer_id, owner_id)

    if can_view_profile:
        return A(
            Img(src=avatar_url, alt="avatar", cls="avatar"),
            Strong(username),
            href=f"/profiles/user/{owner_id}",
            hx_boost="true",
            hx_target="#main",
        )
    else:
        return Div(
            Img(src=avatar_url, alt="avatar", cls="avatar"),
            Strong(username),
        )
