from fasthtml.common import *
from .base_layout import get_full_layout
from dataclasses import dataclass
import os
import logging

logger = logging.getLogger(__name__)

ADMIN_ID = os.environ.get("ADMIN_USER_ID")


@dataclass
class User:
    """Handles user data and rendering operations"""

    id: str
    authorized: bool
    username: str
    avatar: str

    @staticmethod
    def is_admin(user_id: str) -> bool:
        """Check if the user is an admin"""
        return user_id == ADMIN_ID

    def render_row(self) -> Tr:
        """Create a table row for this user"""
        return Tr(
            Td(self.username),
            Td(self.id),
            Td(
                Input(
                    type="checkbox",
                    checked=self.authorized,
                    hx_patch=f"/admin/users/{self.id}/toggle",
                    hx_target="closest tr",
                    hx_swap="outerHTML",
                )
            ),
        )

    @staticmethod
    def render_table(users_list: list["User"]) -> Container:
        """Render the user management table"""
        logger.debug(f"Rendering user table with {len(users_list)} users")

        return (
            H1("User Management"),
            Table(
                Thead(
                    Tr(
                        Th("Username"),
                        Th("ID"),
                        Th("Authorized"),
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
ar_users.name = "User Management"
ar_users.show = False


@ar_users.get("/list")
def list_users(htmx, session):
    """Display the user management page"""
    logger.info("Rendering user management page")

    user_id = session.get("user_id")
    if not user_id or user_id != ADMIN_ID:
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return RedirectResponse("/unauthorized", status_code=303)

    users_list = users(order_by="-username")
    content = User.render_table(users_list)

    return get_full_layout(content, htmx)


@ar_users.patch("/{user_id}/toggle")
def toggle_user(user_id: str, session):
    """Toggle a user's authorized status"""
    logger.info(f"Toggling authorization for user {user_id}")

    caller_user_id = session.get("user_id")
    if not caller_user_id or caller_user_id != ADMIN_ID:
        logger.warning(f"Unauthorized access attempt by user {caller_user_id}")
        return RedirectResponse("/unauthorized", status_code=303)

    try:
        user = users[user_id]
        user.authorized = not user.authorized
        users.update(user)
        logger.info(
            f"Successfully toggled user {user_id} authorization to {user.authorized}"
        )

        return user.render_row()
    except Exception as e:
        logger.error(f"Failed to toggle user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update user")


users_router = ar_users
