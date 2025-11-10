from fasthtml.common import *  # type: ignore
from .base_layout import get_full_layout, list_item
from components.modal import Modal, ModalOpenButton, ModalCloseButton
from dataclasses import dataclass
import os
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE SETUP
# ============================================================================

db = database(os.environ.get("DB_PATH", "app/database.db"))


# ============================================================================
# ROUTER SETUP
# ============================================================================

ar_groups = APIRouter(prefix="/admin/groups")
ar_groups.name = "Groups"  # type: ignore


# ============================================================================
# MODELS
# ============================================================================


@dataclass
class UserGroup:
    """Data and rendering logic for user groups"""

    id: int
    groupname: str

    @staticmethod
    def render_group_list(group_list: list["UserGroup"]):
        logger.debug(f"Rendering group list with {len(group_list)} groups")

        return Div(
            Header(
                H1("Group Management"),
                ModalOpenButton("Create Group", "createGroupModal", cls="primary"),
                cls="flex-row",
            ),
            Modal(
                Article(
                    Header(
                        ModalCloseButton("createGroupModal"),
                        P(Strong("Create New Group")),
                    ),
                    Form(
                        Fieldset(
                            Label(
                                "Group Name",
                                Input(
                                    name="groupname",
                                    required=True,
                                    placeholder="example: MyUserGroup",
                                ),
                            ),
                            Input(
                                value="Create Group",
                                type="submit",
                                hx_post=f"{ar_groups.prefix}/new",
                                hx_target="#main",
                                _at_click="$refs.createGroupModal.close(); document.documentElement.classList.remove('modal-is-open', 'modal-is-opening', 'modal-is-closing')",
                            ),
                        ),
                    ),
                ),
                ref_name="createGroupModal",
            ),
            *[
                list_item(
                    A(
                        group.groupname,
                        href=f"{ar_groups.prefix}/id/{group.id}",
                        hx_boost="true",
                        hx_target="#main",
                    ),
                    Button(
                        "Delete",
                        hx_delete=f"{ar_groups.prefix}/id/{group.id}",
                        hx_confirm=f"Delete group {group.groupname}?",
                        hx_target="#main",
                        hx_push_url="true",
                        cls="secondary outline",
                    ),
                )
                for group in group_list
            ],
            x_data="{}",
        )

    @staticmethod
    def render_group_info(group: "UserGroup"):
        logger.debug(f"Rendering group info for group: {(group.id, group.groupname)}")

        return Div(
            Header(
                H1(f"{group.groupname}"),
                ModalOpenButton(
                    "Add Member",
                    "addMemberModal",
                    cls="primary",
                    hx_get=f"{ar_groups.prefix}/id/{group.id}/member-options",
                    hx_trigger="click",
                    hx_target="#member-select-container",
                ),
                cls="flex-row",
            ),
            Modal(
                Article(
                    Header(
                        ModalCloseButton("addMemberModal"),
                        P(Strong("Add Member to Group")),
                    ),
                    Form(
                        Fieldset(
                            Div(id="member-select-container"),
                            Input(
                                value="Add Member",
                                type="submit",
                                hx_post=f"{ar_groups.prefix}/id/{group.id}/add-member",
                                hx_target="#main",
                                _at_click="$refs.addMemberModal.close(); document.documentElement.classList.remove('modal-is-open', 'modal-is-opening', 'modal-is-closing')",
                            ),
                        ),
                    ),
                ),
                ref_name="addMemberModal",
            ),
            Hr(),
            Section(
                UserGroupMembership.render_user_table_for_group(group.id),
                id="members-list",
            ),
            x_data="{}",
        )


user_groups = db.create(
    UserGroup,
    pk="id",
    transform=True,
)


# ============================================================================
# FEATURE: GROUP MANAGEMENT
# ============================================================================


@ar_groups.get("/list", name="Manage Groups")
def list_groups(htmx, request):
    logger.info("Rendering user group management page")
    group_list = user_groups(order_by="-groupname")
    content = UserGroup.render_group_list(group_list)
    return get_full_layout(content, htmx, request.scope.get("is_admin", False))


@ar_groups.get("/id/{group_id}")
def view_group(group_id: str, htmx, request):
    group = user_groups.get(group_id)
    content = UserGroup.render_group_info(group)
    return get_full_layout(content, htmx, request.scope.get("is_admin", False))


@ar_groups.post("/new")
def create_group(groupname: str, htmx, request):
    user_groups.insert(groupname=groupname)
    logger.info(f"Create group {groupname}")
    return list_groups(htmx, request)


@ar_groups.delete("/id/{group_id}")
def delete_group(group_id: str, htmx, request):
    logger.info(f"Deleting group {group_id}")
    user_groups.delete(group_id)
    return list_groups(htmx, request)


# ============================================================================
# FEATURE: GROUP MEMBERSHIP
# ============================================================================


@dataclass
class UserGroupMembership:
    id: int
    user_id: str
    group_id: int

    @staticmethod
    def render_user_table_for_group(group_id: int):
        """Render the user membership list for a specific group"""
        logger.debug(f"Rendering user membership list for group {group_id}")
        users = db.q(
            """
            SELECT user.*, user_group_membership.id as membership_id
            FROM user
            JOIN user_group_membership
            ON user.id = user_group_membership.user_id
            WHERE user_group_membership.group_id = ?
        """,
            [group_id],
        )

        return (
            H2("Members"),
            *[
                list_item(
                    Span(user["username"]),
                    Button(
                        "Remove",
                        hx_delete=f"{ar_groups.prefix}/membership/{user['membership_id']}",
                        hx_confirm=f"Remove {user['username']} from this group?",
                        hx_target="#main",
                        hx_push_url="true",
                        cls="secondary outline",
                    ),
                )
                for user in users
            ],
        )


user_group_membership = db.create(
    UserGroupMembership,
    pk="id",
    foreign_keys=(("user_id", "user"), ("group_id", "user_group")),
    transform=True,
)


@ar_groups.get("/id/{group_id}/member-options")
def get_member_options(group_id: str):
    users = db.q(
        """
        SELECT id, username FROM user
        WHERE id NOT IN (
            SELECT user_id FROM user_group_membership WHERE group_id = ?
        )
        """,
        [group_id],
    )

    if not users:
        return P("All users are already members of this group", style="margin: 1rem 0;")

    return Select(
        *[Option(user["username"], value=user["id"]) for user in users],
        name="member_user_id",
        required=True,
    )


@ar_groups.post("/id/{group_id}/add-member")
def add_member(group_id: str, member_user_id: str, htmx, request):
    user_group_membership.insert({"user_id": member_user_id, "group_id": group_id})
    logger.info(f"Added user {member_user_id} to group {group_id}")
    return view_group(group_id, htmx, request)


@ar_groups.delete("/membership/{membership_id}")
def remove_user_from_group(membership_id: str, htmx, request):
    group_id = user_group_membership[membership_id].group_id
    logger.info(f"Removing membership {membership_id}")
    user_group_membership.delete(membership_id)
    return view_group(group_id, htmx, request)


# ============================================================================
# EXPORT
# ============================================================================

groups_router = ar_groups
