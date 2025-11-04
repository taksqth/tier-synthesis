from fasthtml.common import *
from .base_layout import get_full_layout, list_item, tag
from dataclasses import dataclass
from datetime import datetime
import os
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class DBTierlist:
    TIERS = ["S", "A", "B", "C", "D"]

    id: int
    owner_id: str
    category: str
    name: str
    data: str
    created_at: str

    def get_tier_data(self, images: list) -> dict:
        """Get tierlist data with image elements"""
        logger.debug(f"Loading tier data from JSON: {self.data}")
        data = json.loads(self.data)

        result = {tier: [] for tier in self.TIERS}
        leftover_images = []
        for image in images:
            for tier, image_ids in data.items():
                if str(image.id) in image_ids:
                    result[tier].append(self._get_image_element(image))
                    break
            else:
                leftover_images.append(self._get_image_element(image))
        return result, leftover_images

    def _get_tierlist_data_js(self) -> str:
        """Get JavaScript to extract tierlist data from the DOM"""
        return """Object.fromEntries(
            Array.from(document.querySelectorAll('[data-tier]')).map(tier => [
                tier.dataset.tier,
                Array.from(tier.querySelectorAll('div'))
                    .map(div => div.dataset.imageId)
            ])
        )"""

    def render_page(
        self,
        images: list,
        can_edit: bool = True,
        user_groups: list = None,
        shared_group_ids: list = None,
    ) -> Container:
        from .users_router import get_user_avatar

        filtered_images = [img for img in images if img.category == self.category]
        tierlist_data, leftover_images = self.get_tier_data(filtered_images)
        username, avatar_url = get_user_avatar(self.owner_id)

        return Div(
            Header(
                H1("Image Tier List" + (" (Read Only)" if not can_edit else "")),
                A(
                    "Back to tierlists",
                    href=f"{ar_tierlist.prefix}/list",
                    hx_boost="true",
                    hx_target="#main",
                    cls="secondary",
                    role="button",
                ),
                cls="flex-row",
            ),
            Div(
                Img(
                    src=avatar_url,
                    alt="avatar",
                    cls="avatar",
                ),
                Strong(username),
                cls="user-info large",
            ),
            self._create_save_form(can_edit, user_groups or [], shared_group_ids or []),
            P("Category: ", tag(self.category)),
            *[
                self._create_tier_row(tier, can_edit, tierlist_data[tier])
                for tier in tierlist_data.keys()
            ],
            H2("Available Images"),
            make_container(
                Div(
                    *leftover_images,
                    cls="grid",
                ),
                can_edit,
            ),
            Script("""
                (function() {
                    const container = document.currentScript.parentElement;

                    if (container._tierlistHandlersRegistered) return;
                    container._tierlistHandlersRegistered = true;

                    const getData = () => Alpine.$data(container);

                    document.body.addEventListener('htmx:beforeRequest', function(e) {
                        if (e.detail.elt && e.detail.elt.id === 'tierlist-save-btn') return;

                        const data = getData();
                        if (data && data.hasUnsavedChanges) {
                            if (!confirm('You have unsaved changes. Are you sure you want to leave?')) {
                                e.preventDefault();
                            }
                        }
                    });

                    window.addEventListener('beforeunload', function(e) {
                        const data = getData();
                        if (data && data.hasUnsavedChanges) {
                            e.preventDefault();
                            e.returnValue = '';
                        }
                    });
                })();
            """),
            **{"x-data": "{ dragging: null, saving: false, hasUnsavedChanges: false }"},
        )

    def _get_image_element(self, image):
        return make_draggable(
            Div(
                Img(
                    src=f"/images/thumbnail/{image.id}",
                    alt=image.name,
                    draggable="false",
                    style="pointer-events: none;",
                ),
                data_image_id=str(image.id),
            )
        )

    def _create_tier_row(self, tier: str, can_edit: bool, images: list = None):
        """Create a tier row"""
        return Div(
            H2(tier),
            make_container(
                Div(
                    *(images or []),
                    cls="grid",
                    data_tier=tier,
                ),
                can_edit,
            ),
        )

    def _create_save_form(self, can_edit, user_groups, shared_group_ids):
        return Fieldset(
            Label(
                "Name",
                Group(
                    Input(
                        name="tierlist_name",
                        value=self.name,
                        placeholder="My Tierlist",
                        id="tierlist-name-input",
                        readonly=not can_edit,
                        **{"@input": "hasUnsavedChanges = true"} if can_edit else {},
                    ),
                    Button(
                        "Save",
                        hx_post=f"{ar_tierlist.prefix}/id/{self.id}",
                        hx_vals=f"""js:{{
                            tierlist_data: {self._get_tierlist_data_js()},
                            name: document.getElementById('tierlist-name-input').value,
                            shared_groups: Array.from(document.querySelectorAll('input[name="shared_groups"]:checked')).map(cb => cb.value).join(',')
                        }}""",
                        hx_target="#main",
                        hx_push_url="true",
                        cls="primary",
                        id="tierlist-save-btn",
                        disabled=not can_edit,
                        **{
                            "x-bind:aria-busy": "saving",
                            "@htmx:before-request": "saving = true; hasUnsavedChanges = false",
                            "@htmx:after-request": "saving = false",
                        }
                        if can_edit
                        else {},
                    ),
                    cls="flex-row",
                ),
            ),
            (
                Label(
                    "Share with groups",
                    *[
                        CheckboxX(
                            name="shared_groups",
                            value=str(group["id"]),
                            checked=group["id"] in shared_group_ids,
                            disabled=not can_edit,
                            label=group["groupname"],
                            **{"@input": "hasUnsavedChanges = true"} if can_edit else {},
                        )
                        for group in user_groups
                    ],
                )
                if user_groups
                else None
            ),
        )

    @staticmethod
    def render_list(
        tierlist_list: list["DBTierlist"],
        user_id: str,
        categories: list = None,
        selected_category: str = "",
        mine_only: bool = False,
    ):
        from .users_router import get_user_avatar

        return Div(
            Header(
                H1("My Tierlists"),
                A(
                    "Create New",
                    href=f"{ar_tierlist.prefix}/new",
                    hx_boost="true",
                    hx_target="#main",
                    cls="primary",
                    role="button",
                ),
                cls="flex-row",
            ),
            Div(
                (
                    Label(
                        "Filter by category",
                        Select(
                            Option("All", value="", selected=(not selected_category)),
                            *[
                                Option(
                                    cat, value=cat, selected=(cat == selected_category)
                                )
                                for cat in (categories or [])
                            ],
                            name="category",
                            hx_get=f"{ar_tierlist.prefix}/list",
                            hx_target="#main",
                            hx_include="[name='mine_only']",
                            hx_push_url="true",
                        ),
                    )
                    if categories
                    else None
                ),
                CheckboxX(
                    name="mine_only",
                    value="true",
                    checked=mine_only,
                    label="Show only mine",
                    hx_get=f"{ar_tierlist.prefix}/list",
                    hx_target="#main",
                    hx_include="[name='category']",
                ),
                style="display: flex; gap: 1rem; align-items: center; margin-bottom: 1rem;",
            ),
            *[
                list_item(
                    Div(
                        A(
                            Div(
                                Img(
                                    src=get_user_avatar(tierlist.owner_id)[1],
                                    alt="avatar",
                                    cls="avatar",
                                ),
                                Small(get_user_avatar(tierlist.owner_id)[0]),
                                cls="user-info",
                            ),
                            Strong(tierlist.name),
                            f" - {tierlist.created_at[:10]}",
                            Br(),
                            tag(tierlist.category),
                            tag("Owned" if tierlist.owner_id == user_id else "Shared"),
                            href=f"{ar_tierlist.prefix}/id/{tierlist.id}",
                            hx_boost="true",
                            hx_target="#main",
                        ),
                        rating_display(tierlist.id, user_id),
                    ),
                    Button(
                        "Delete",
                        hx_delete=f"{ar_tierlist.prefix}/id/{tierlist.id}",
                        hx_confirm="Delete this tierlist?",
                        hx_target="#main",
                        hx_push_url="true",
                        cls="secondary outline",
                    )
                    if tierlist.owner_id == user_id
                    else None,
                )
                for tierlist in tierlist_list
            ]
            if tierlist_list
            else P("No tierlists yet. Create one to get started!"),
        )


@dataclass
class TierlistShare:
    id: int
    tierlist_id: int
    user_group_id: int


@dataclass
class TierlistRating:
    id: int
    tierlist_id: int
    user_id: str
    rating: int


@dataclass
class TierlistComment:
    id: int
    tierlist_id: int
    user_id: str
    comment: str
    created_at: str


db = database(os.environ.get("DB_PATH", "app/database.db"))
tierlists = db.create(
    DBTierlist,
    pk="id",
    foreign_keys=[("owner_id", "user")],
    transform=True,
)
tierlist_shares = db.create(
    TierlistShare,
    pk="id",
    foreign_keys=(("tierlist_id", "db_tierlist"), ("user_group_id", "user_group")),
    transform=True,
)
tierlist_ratings = db.create(
    TierlistRating,
    pk="id",
    foreign_keys=(("tierlist_id", "db_tierlist"), ("user_id", "user")),
    transform=True,
)
tierlist_comments = db.create(
    TierlistComment,
    pk="id",
    foreign_keys=(("tierlist_id", "db_tierlist"), ("user_id", "user")),
    transform=True,
)


def get_accessible_tierlists(user_id: str, is_admin: bool, fetch_all: bool = False):
    if is_admin or fetch_all:
        result = db.q("SELECT * FROM db_tierlist ORDER BY created_at DESC")
    else:
        result = db.q(
            """
            SELECT DISTINCT db_tierlist.*
            FROM db_tierlist
            LEFT JOIN tierlist_share ON db_tierlist.id = tierlist_share.tierlist_id
            LEFT JOIN user_group_membership ON tierlist_share.user_group_id = user_group_membership.group_id
            WHERE db_tierlist.owner_id = ?
               OR user_group_membership.user_id = ?
            ORDER BY db_tierlist.created_at DESC
            """,
            [user_id, user_id],
        )
    return [DBTierlist(**row) for row in result]


# Router setup
ar_tierlist = APIRouter(prefix="/tierlist")
ar_tierlist.name = "Tierlist"
ar_tierlist.show = True


# TODO: Move to a separate module later as more generic utility functions
def make_draggable(element):
    """Make an element draggable with drag and drop events using Alpine.js"""
    return element(
        **{
            "x-on:dragstart": "dragging = $el",
            "x-on:dragend": "dragging = null",
        },
        draggable="true",
    )


def make_container(element, can_edit, background_color="#f5f5f5"):
    """Create a draggable container with drop zone functionality using Alpine.js"""
    return element(
        **{
            "x-on:dragover": "$event.preventDefault()",
            "x-on:drop": """
                $event.preventDefault();
                const target = $event.target.closest('article');
                if (dragging && target) {
                    target.parentNode.insertBefore(dragging, target);
                    hasUnsavedChanges = true;
                } else if (dragging) {
                    $event.currentTarget.insertBefore(dragging, $event.currentTarget.firstChild);
                    hasUnsavedChanges = true;
                }
            """
            if can_edit
            else "",
        },
        style=(element.style if element.style else "")
        + f"""
            grid-template-columns: repeat(auto-fill, 130px);
            min-height: 120px;
            background-color: {background_color};
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 1rem;
            margin: 0.1rem 0;
        """,
    )


# Routes
@ar_tierlist.get("/new", name="Make new tierlist")
def create_new_tierlist(htmx, request, session):
    from .images_router import category_input
    from .category_utils import get_all_categories

    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)
    categories = get_all_categories()

    content = Div(
        H1("Create New Tierlist"),
        Form(
            Fieldset(
                Label(
                    "Name",
                    Input(
                        name="name",
                        required=True,
                        placeholder="My Tierlist",
                    ),
                ),
                category_input(
                    categories, input_id="new-tierlist-category", required=True
                ),
                Button("Create", type="submit"),
            ),
            hx_post=f"{ar_tierlist.prefix}/new",
            hx_target="#main",
            hx_push_url="true",
        ),
    )
    return get_full_layout(content, htmx, is_admin)


@ar_tierlist.post("/new")
def post_new_tierlist(name: str, category: str, htmx, request, session):
    from .category_utils import validate_and_get_category

    owner_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    try:
        validated_category = validate_and_get_category(category)
    except ValueError as e:
        return get_full_layout(P(f"Category error: {e}", style="color: red;"), htmx, is_admin)

    tierlist = DBTierlist(
        id=None,
        owner_id=owner_id,
        category=validated_category,
        name=name,
        data=json.dumps({tier: [] for tier in DBTierlist.TIERS}),
        created_at=datetime.now().isoformat(),
    )
    tierlist = tierlists.insert(tierlist)

    return get_tierlist_editor(tierlist.id, htmx, request, session)


@ar_tierlist.get("/id/{id}")
def get_tierlist_editor(id: int, htmx, request, session):
    from .images_router import get_accessible_images

    tierlist = tierlists[id]
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    accessible_tierlists = get_accessible_tierlists(user_id, is_admin)
    if not any(tl.id == id for tl in accessible_tierlists):
        return get_full_layout(
            H1("Access Denied"),
            P("You don't have access to this tierlist."),
            htmx,
            is_admin,
        )

    can_edit = tierlist.owner_id == user_id or is_admin

    user_groups = db.q(
        """
        SELECT user_group.*
        FROM user_group
        JOIN user_group_membership ON user_group.id = user_group_membership.group_id
        WHERE user_group_membership.user_id = ?
        """,
        [user_id],
    )

    shared_group_ids = [
        row["user_group_id"]
        for row in db.q(
            "SELECT user_group_id FROM tierlist_share WHERE tierlist_id = ?", [id]
        )
    ]

    images_query = get_accessible_images(user_id, is_admin, with_blobs=False)
    logger.debug(f"Loaded {len(images_query)} images for tierlist")

    content = tierlist.render_page(
        images_query, can_edit, user_groups, shared_group_ids
    )
    logger.info("Tierlist page rendered successfully")

    return get_full_layout(content, htmx, is_admin)


@ar_tierlist.post("/id/{id}")
def save_tierlist(
    id: int,
    tierlist_data: str,
    name: str,
    shared_groups: str,
    htmx,
    request,
    session,
):
    owner_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)
    logger.debug(f"Saving tierlist. ID: {id}, Data: {tierlist_data}")

    tierlist = tierlists[id]

    if tierlist.owner_id != owner_id and not is_admin:
        logger.warning(
            f"User {owner_id} attempted to update tierlist {id} owned by {tierlist.owner_id}"
        )
        return RedirectResponse("/unauthorized", status_code=303)

    tierlist.data = tierlist_data
    tierlist.name = name
    tierlists.update(tierlist)

    db.q("DELETE FROM tierlist_share WHERE tierlist_id = ?", [id])
    if shared_groups:
        for group_id in shared_groups.split(","):
            if group_id:
                tierlist_shares.insert(
                    {"tierlist_id": id, "user_group_id": int(group_id)}
                )

    main_content = get_tierlist_editor(id, htmx, request, session)
    toast = Div(
        Ins("Saved successfully"),
        Script("""
            setTimeout(() => {
                const toast = document.getElementById('toast');
                if (toast) toast.classList.remove('show');
            }, 3000);
        """),
        id="toast",
        cls="show",
        **{"hx-swap-oob": "true"},
    )

    return main_content, toast


@ar_tierlist.get("/list", name="Browse Tierlists")
def list_tierlists(htmx, request, session, category: str = "", mine_only: str = ""):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)
    tierlist_list = get_accessible_tierlists(user_id, is_admin)

    categories = sorted(set(tl.category for tl in tierlist_list if tl.category))

    if category and category != "All":
        filtered_tierlists = [tl for tl in tierlist_list if tl.category == category]
    else:
        filtered_tierlists = tierlist_list

    if mine_only == "true":
        filtered_tierlists = [tl for tl in filtered_tierlists if tl.owner_id == user_id]

    content = DBTierlist.render_list(
        filtered_tierlists, user_id, categories, category, mine_only == "true"
    )
    return get_full_layout(content, htmx, is_admin)


@ar_tierlist.delete("/id/{id}")
def delete_tierlist(id: str, htmx, request, session):
    owner_id = session.get("user_id")
    tierlist = tierlists[id]

    if tierlist.owner_id != owner_id:
        logger.warning(
            f"User {owner_id} attempted to delete tierlist {id} owned by {tierlist.owner_id}"
        )
        return RedirectResponse("/unauthorized", status_code=303)

    tierlists.delete(id)
    return list_tierlists(htmx, request, session)


def get_rating_counts(tierlist_id: int):
    love_count = db.q(
        "SELECT COUNT(*) as count FROM tierlist_rating WHERE tierlist_id = ? AND rating = 1",
        [tierlist_id],
    )[0]["count"]
    tomato_count = db.q(
        "SELECT COUNT(*) as count FROM tierlist_rating WHERE tierlist_id = ? AND rating = -1",
        [tierlist_id],
    )[0]["count"]
    return love_count, tomato_count


def get_user_rating(tierlist_id: int, user_id: str):
    result = db.q(
        "SELECT rating FROM tierlist_rating WHERE tierlist_id = ? AND user_id = ?",
        [tierlist_id, user_id],
    )
    return result[0]["rating"] if result else None


def rating_button(
    emoji: str, count: int, rating_value: int, tierlist_id: int, is_active: bool
):
    return Button(
        f"{emoji} {count}",
        hx_post=f"{ar_tierlist.prefix}/id/{tierlist_id}/rate",
        hx_vals=f'{{"rating": {rating_value}}}',
        hx_target=f"#ratings-{tierlist_id}",
        hx_swap="outerHTML",
        cls=f"rating-button {'' if is_active else 'outline secondary'}",
    )


def get_comment_count(tierlist_id: int):
    return db.q(
        "SELECT COUNT(*) as count FROM tierlist_comment WHERE tierlist_id = ?",
        [tierlist_id],
    )[0]["count"]


def rating_display(tierlist_id: int, user_id: str):
    love_count, tomato_count = get_rating_counts(tierlist_id)
    user_rating = get_user_rating(tierlist_id, user_id)
    comment_count = get_comment_count(tierlist_id)

    return Div(
        rating_button("👎", tomato_count, -1, tierlist_id, user_rating == -1),
        rating_button("❤️", love_count, 1, tierlist_id, user_rating == 1),
        Button(
            f"💬 {comment_count}",
            hx_get=f"{ar_tierlist.prefix}/id/{tierlist_id}/comments",
            hx_target=f"#comments-modal-{tierlist_id}",
            hx_swap="innerHTML",
            onclick=f"document.getElementById('comments-modal-{tierlist_id}').showModal()",
            cls="rating-button outline secondary",
        ),
        Dialog(id=f"comments-modal-{tierlist_id}", style="width: 600px;"),
        id=f"ratings-{tierlist_id}",
        cls="rating-container",
    )


@ar_tierlist.post("/id/{id}/rate")
def rate_tierlist(id: int, rating: int, session):
    user_id = session.get("user_id")

    if rating not in [-1, 1]:
        return rating_display(id, user_id)

    existing = db.q(
        "SELECT * FROM tierlist_rating WHERE tierlist_id = ? AND user_id = ?",
        [id, user_id],
    )

    if existing:
        existing_rating = TierlistRating(**existing[0])
        if existing_rating.rating == rating:
            tierlist_ratings.delete(existing_rating.id)
        else:
            existing_rating.rating = rating
            tierlist_ratings.update(existing_rating)
    else:
        tierlist_ratings.insert(
            {"tierlist_id": id, "user_id": user_id, "rating": rating}
        )

    return rating_display(id, user_id)


def render_comment(comment: TierlistComment):
    from .users_router import get_user_avatar

    username, avatar_url = get_user_avatar(comment.user_id)
    user_rating = get_user_rating(comment.tierlist_id, comment.user_id)

    vote_indicator = ""
    if user_rating == 1:
        vote_indicator = " ❤️"
    elif user_rating == -1:
        vote_indicator = " 👎"

    return Article(
        Div(
            Img(src=avatar_url, alt="avatar", cls="avatar"),
            Div(
                Strong(username + vote_indicator),
                Small(comment.created_at[:16], cls="text-muted"),
            ),
            cls="user-info",
        ),
        P(comment.comment),
        cls="comment-item",
    )


@ar_tierlist.get("/id/{id}/comments")
def get_comments(id: int, session):
    user_id = session.get("user_id")
    comments = db.q(
        "SELECT * FROM tierlist_comment WHERE tierlist_id = ? ORDER BY created_at DESC",
        [id],
    )
    comment_list = [TierlistComment(**c) for c in comments]

    return Div(
        Article(
            H3("Comments"),
            Div(
                *[render_comment(c) for c in comment_list]
                if comment_list
                else [P("No comments yet")],
                cls="comments-list",
            ),
            Form(
                Fieldset(
                    Textarea(
                        name="comment",
                        placeholder="Write a comment...",
                        required=True,
                        rows="3",
                    ),
                    Button("Post Comment", type="submit"),
                ),
                hx_post=f"{ar_tierlist.prefix}/id/{id}/comments",
                hx_target=f"#comments-modal-{id}",
                hx_swap="innerHTML",
            ),
        ),
    )


@ar_tierlist.post("/id/{id}/comments")
def post_comment(id: int, comment: str, session):
    user_id = session.get("user_id")

    tierlist_comments.insert(
        {
            "tierlist_id": id,
            "user_id": user_id,
            "comment": comment,
            "created_at": datetime.now().isoformat(),
        }
    )

    return get_comments(id, session), Div(
        rating_display(id, user_id),
        **{"hx-swap-oob": f"true:#{f'ratings-{id}'}"},
    )


tierlist_router = ar_tierlist
