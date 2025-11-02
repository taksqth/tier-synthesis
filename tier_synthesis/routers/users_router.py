from fasthtml.common import *
from .base_layout import get_full_layout
from dataclasses import dataclass
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

    def render_row(self) -> Tr:
        return Tr(
            Td(self.username),
            Td(self.id),
            Td(
                Input(
                    type="checkbox",
                    checked=self.authorized,
                    hx_patch=f"/admin/users/{self.id}/toggle-authorized",
                    hx_target="closest tr",
                    hx_swap="outerHTML",
                )
            ),
            Td(
                Input(
                    type="checkbox",
                    checked=self.is_admin,
                    hx_patch=f"/admin/users/{self.id}/toggle-admin",
                    hx_target="closest tr",
                    hx_swap="outerHTML",
                )
            ),
        )

    @staticmethod
    def render_table(users_list: list["User"]):
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


ar_users = APIRouter(prefix="/admin/users")
ar_users.name = "Users"


@ar_users.get("/list", name="Manage Users")
def list_users(htmx, request):
    logger.info("Rendering user management page")
    users_list = users(order_by="-username")
    content = User.render_table(users_list)
    return get_full_layout(content, htmx, request.scope.get("is_admin", False))


@ar_users.patch("/{user_id}/toggle-authorized")
def toggle_authorized(user_id: str):
    logger.info(f"Toggling authorization for user {user_id}")
    user = users[user_id]
    user.authorized = not user.authorized
    users.update(user)
    return user.render_row()


@ar_users.patch("/{user_id}/toggle-admin")
def toggle_admin(user_id: str):
    logger.info(f"Toggling admin status for user {user_id}")
    user = users[user_id]
    user.is_admin = not user.is_admin
    users.update(user)
    return user.render_row()


users_router = ar_users
