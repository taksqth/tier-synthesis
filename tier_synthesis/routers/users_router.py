from fasthtml.common import *  # type: ignore
from .base_layout import get_full_layout
from dataclasses import dataclass
from functools import lru_cache
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class User:
    id: str
    authorized: bool
    username: str
    avatar: str
    is_admin: bool

    def render_row(self) -> Any:
        return Tr(
            Td(self.username),
            Td(self.id),
            Td(
                CheckboxX(
                    checked=self.authorized,
                    hx_patch=f"/admin/users/{self.id}/toggle-authorized",
                    hx_target="closest tr",
                    hx_swap="outerHTML",
                )
            ),
            Td(
                CheckboxX(
                    checked=self.is_admin,
                    hx_patch=f"/admin/users/{self.id}/toggle-admin",
                    hx_target="closest tr",
                    hx_swap="outerHTML",
                )
            ),
        )

    @staticmethod
    def render_table(users_list: list["User"]) -> Any:
        logger.debug(f"Rendering user table with {len(users_list)} users")

        return (
            H1("User Management"),
            Table(
                Thead(
                    Tr(
                        Th("Username"),
                        Th("ID"),
                        Th("Authorized"),
                        Th("Admin"),
                    )
                ),
                Tbody(
                    *[user.render_row() for user in users_list],
                ),
                cls="table",
            ),
        )


db = database(os.environ.get("DB_PATH", "app/database.db"))
users = db.create(
    User,
    pk="id",
    transform=True,
)


DEFAULT_AVATAR = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48'%3E%3Crect width='48' height='48' fill='%23ccc'/%3E%3C/svg%3E"
ANONYMOUS_AVATAR = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48'%3E%3Ccircle cx='24' cy='24' r='20' fill='%23999'/%3E%3Ctext x='24' y='30' text-anchor='middle' fill='white' font-size='20'%3E%3F%3C/text%3E%3C/svg%3E"


@lru_cache(maxsize=128)
def get_user_avatar(owner_id: str):
    user_data = db.q("SELECT username, avatar FROM user WHERE id = ?", [owner_id])
    if user_data:
        username = user_data[0]["username"]
        avatar_hash = user_data[0].get("avatar")
        if avatar_hash:
            avatar_url = f"https://cdn.discordapp.com/avatars/{owner_id}/{avatar_hash}.png?size=128"
        else:
            avatar_url = DEFAULT_AVATAR
        return username, avatar_url
    return "Unknown", DEFAULT_AVATAR


def get_anonymous_avatar():
    return "Anonymous", ANONYMOUS_AVATAR


def users_share_group(user_id_1: str, user_id_2: str) -> bool:
    if user_id_1 == user_id_2:
        return True

    result = db.q(
        """
        SELECT COUNT(*) as shared_count
        FROM user_group_membership ugm1
        JOIN user_group_membership ugm2
        ON ugm1.group_id = ugm2.group_id
        WHERE ugm1.user_id = ? AND ugm2.user_id = ?
        """,
        [user_id_1, user_id_2],
    )

    return result[0]["shared_count"] > 0 if result else False


def get_shared_group_users(user_id):
    result = db.q(
        """
        SELECT DISTINCT ugm2.user_id
        FROM user_group_membership ugm1
        JOIN user_group_membership ugm2 ON ugm1.group_id = ugm2.group_id
        WHERE ugm1.user_id = ?
        """,
        [user_id],
    )
    return {row["user_id"] for row in result}


ar_users = APIRouter(prefix="/admin/users")
ar_users.name = "Users"  # type: ignore


@ar_users.get("/list", name="Manage Users")
def list_users(htmx, request) -> Any:
    logger.info("Rendering user management page")
    users_list = users(order_by="-username")
    content = User.render_table(users_list)
    return get_full_layout(content, htmx, request.scope.get("is_admin", False))


@ar_users.patch("/{user_id}/toggle-authorized")
def toggle_authorized(user_id: str, request) -> Any:
    if not request.scope.get("is_admin", False):
        return Response("Forbidden", status_code=403)

    logger.info(f"Toggling authorization for user {user_id}")
    user = users[user_id]
    user.authorized = not user.authorized
    users.update(user)
    return user.render_row()


@ar_users.patch("/{user_id}/toggle-admin")
def toggle_admin(user_id: str, request) -> Any:
    if not request.scope.get("is_admin", False):
        return Response("Forbidden", status_code=403)

    logger.info(f"Toggling admin status for user {user_id}")
    user = users[user_id]
    user.is_admin = not user.is_admin
    users.update(user)
    return user.render_row()


users_router = ar_users
