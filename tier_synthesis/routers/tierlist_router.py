from fasthtml.common import *
from .base_layout import get_full_layout, list_item, tag
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
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

    def get_tier_data(self, images: list) -> tuple[dict[str, list[Any]], list[Any]]:
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
        user_groups: list | None = None,
        shared_group_ids: list | None = None,
    ) -> Any:
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

    def _get_image_element(self, image) -> Any:
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

    def _create_tier_row(self, tier: str, can_edit: bool, images: list | None = None):
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
                            **{"@input": "hasUnsavedChanges = true"}
                            if can_edit
                            else {},
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
        categories: list | None = None,
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
                        rating_display(tierlist, user_id),
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


@lru_cache(maxsize=256)
def get_user_rating(tierlist_id: int, user_id: str):
    return next(
        iter(
            tierlist_ratings("tierlist_id = ? and user_id = ?", (tierlist_id, user_id))
        ),
        None,
    )


def get_tierlist_metadata(tierlist_ids: list[int], user_id: str | None = None):
    if not tierlist_ids:
        return {}

    placeholders = ','.join('?' * len(tierlist_ids))

    rating_result = db.q(
        f"""
        SELECT
            tierlist_id,
            SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as love_count,
            SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) as tomato_count
        FROM tierlist_rating
        WHERE tierlist_id IN ({placeholders})
        GROUP BY tierlist_id
        """,
        tierlist_ids
    )

    comment_result = db.q(
        f"""
        SELECT tierlist_id, COUNT(*) as count
        FROM tierlist_comment
        WHERE tierlist_id IN ({placeholders})
        GROUP BY tierlist_id
        """,
        tierlist_ids
    )

    result = {tid: {"love_count": 0, "tomato_count": 0, "user_rating": None, "comment_count": 0}
              for tid in tierlist_ids}

    for row in rating_result:
        result[row["tierlist_id"]]["love_count"] = row["love_count"] or 0
        result[row["tierlist_id"]]["tomato_count"] = row["tomato_count"] or 0

    for row in comment_result:
        result[row["tierlist_id"]]["comment_count"] = row["count"]

    if user_id:
        user_rating_result = db.q(
            f"""
            SELECT tierlist_id, rating
            FROM tierlist_rating
            WHERE tierlist_id IN ({placeholders}) AND user_id = ?
            """,
            [*tierlist_ids, user_id]
        )
        for row in user_rating_result:
            result[row["tierlist_id"]]["user_rating"] = row["rating"]

    return result


def enrich_tierlists_with_ratings(tierlist_list: list[DBTierlist], user_id: str | None = None):
    if not tierlist_list:
        return tierlist_list

    metadata = get_tierlist_metadata([tl.id for tl in tierlist_list], user_id)

    for tierlist in tierlist_list:
        data = metadata[tierlist.id]
        tierlist.love_count = data["love_count"]
        tierlist.tomato_count = data["tomato_count"]
        tierlist.user_rating = data["user_rating"]
        tierlist.comment_count = data["comment_count"]

    return tierlist_list


def get_rating_repr(rating: int) -> str:
    if rating == 1:
        return " ❤️"
    if rating == -1:
        return " 👎"
    return ""


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
def create_new_tierlist(htmx, req):
    from .images_router import category_input
    from .category_utils import get_all_categories

    is_admin = req.scope.get("is_admin", False)
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
def post_new_tierlist(name: str, category: str, htmx, req):
    from .category_utils import validate_and_get_category

    owner_id = req.scope["auth"]
    is_admin = req.scope.get("is_admin", False)

    try:
        validated_category = validate_and_get_category(category)
    except ValueError as e:
        return get_full_layout(
            P(f"Category error: {e}", style="color: red;"), htmx, is_admin
        )

    tierlist = tierlists.insert(
        owner_id=owner_id,
        category=validated_category,
        name=name,
        data=json.dumps({tier: [] for tier in DBTierlist.TIERS}),
        created_at=datetime.now().isoformat(),
    )

    return get_tierlist_editor(tierlist.id, htmx, req)


@ar_tierlist.get("/id/{id}")
def get_tierlist_editor(id: int, htmx, req):
    from .images_router import get_accessible_images

    logger.info(tierlists)
    tierlist = tierlists[id]
    is_admin = req.scope.get("is_admin", False)
    user_id = req.scope["auth"]

    accessible_tierlists = get_accessible_tierlists(user_id, is_admin)
    if not any(tl.id == id for tl in accessible_tierlists):
        return get_full_layout(
            (
                H1("Access Denied"),
                P("You don't have access to this tierlist."),
            ),
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
    content = tierlist.render_page(
        images_query, can_edit, user_groups, shared_group_ids
    )

    return get_full_layout(content, htmx, is_admin)


@ar_tierlist.post("/id/{id}")
def save_tierlist(
    id: int,
    tierlist_data: str,
    name: str,
    shared_groups: str,
    htmx,
    req,
):
    owner_id = req.scope["auth"]
    is_admin = req.scope.get("is_admin", False)
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

    main_content = get_tierlist_editor(id, htmx, req)
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
def list_tierlists(htmx, req, category: str = "", mine_only: str = ""):
    user_id = req.scope["auth"]
    is_admin = req.scope.get("is_admin", False)
    tierlist_list = get_accessible_tierlists(user_id, is_admin)

    categories = sorted(set(tl.category for tl in tierlist_list if tl.category))

    if category and category != "All":
        filtered_tierlists = [tl for tl in tierlist_list if tl.category == category]
    else:
        filtered_tierlists = tierlist_list

    if mine_only == "true":
        filtered_tierlists = [tl for tl in filtered_tierlists if tl.owner_id == user_id]

    enrich_tierlists_with_ratings(filtered_tierlists, user_id)

    content = DBTierlist.render_list(
        filtered_tierlists, user_id, categories, category, mine_only == "true"
    )
    return get_full_layout(content, htmx, is_admin)


@ar_tierlist.delete("/id/{id}")
def delete_tierlist(id: str, htmx, req):
    owner_id = req.scope["user_id"]
    is_admin = req.scope.get("is_admin", False)
    tierlist = tierlists[id]

    if not is_admin and owner_id != tierlist.owner_id:
        logger.warning(
            f"User {owner_id} attempted to delete tierlist {id} owned by {tierlist.owner_id}"
        )
        return RedirectResponse("/unauthorized", status_code=303)

    tierlists.delete(id)

    return list_tierlists(htmx, req)


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


def rating_display(tierlist: DBTierlist, user_id: str):
    return Div(
        rating_button(
            emoji=get_rating_repr(-1),
            count=tierlist.tomato_count,
            rating_value=-1,
            tierlist_id=tierlist.id,
            is_active=(tierlist.user_rating == -1),
        ),
        rating_button(
            emoji=get_rating_repr(1),
            count=tierlist.love_count,
            rating_value=1,
            tierlist_id=tierlist.id,
            is_active=(tierlist.user_rating == 1),
        ),
        Button(
            f"💬 {tierlist.comment_count}",
            hx_get=f"{ar_tierlist.prefix}/id/{tierlist.id}/comments",
            hx_target=f"#comments-modal-{tierlist.id}",
            hx_swap="innerHTML",
            onclick=f"document.getElementById('comments-modal-{tierlist.id}').showModal()",
            cls="rating-button outline secondary",
        ),
        Dialog(id=f"comments-modal-{tierlist.id}", style="width: 600px;"),
        id=f"ratings-{tierlist.id}",
        cls="rating-container",
    )


@ar_tierlist.post("/id/{id}/rate")
def rate_tierlist(id: int, rating: int, req):
    user_id = req.scope["auth"]

    if rating not in [-1, 1]:
        tierlist = tierlists[id]
        enrich_tierlists_with_ratings([tierlist], user_id)
        return rating_display(tierlist, user_id)

    user_rating = get_user_rating(id, user_id)
    if user_rating:
        if user_rating.rating == rating:
            tierlist_ratings.delete(user_rating.id)
        else:
            user_rating.rating = rating
            tierlist_ratings.update(user_rating)
    else:
        tierlist_ratings.insert(
            {"tierlist_id": id, "user_id": user_id, "rating": rating}
        )

    get_user_rating.cache_clear()
    tierlist = tierlists[id]
    enrich_tierlists_with_ratings([tierlist], user_id)
    return rating_display(tierlist, user_id)


def render_comment(comment: TierlistComment):
    from .users_router import get_user_avatar

    username, avatar_url = get_user_avatar(comment.user_id)
    user_rating = get_user_rating(comment.tierlist_id, comment.user_id)
    vote_indicator = get_rating_repr(user_rating.rating) if user_rating else ""

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
def get_comments(id: int):
    comment_list = tierlist_comments(
        "tierlist_id = ?", (id,), order_by="created_at DESC"
    )

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
def post_comment(id: int, comment: str, req):
    user_id = req.scope["auth"]

    tierlist_comments.insert(
        tierlist_id=id,
        user_id=user_id,
        comment=comment,
        created_at=datetime.now().isoformat(),
    )

    tierlist = tierlists[id]
    enrich_tierlists_with_ratings([tierlist], user_id)

    return get_comments(id), Div(
        rating_display(tierlist, user_id),
        hx_swap_oob=f"true:#ratings-{id}",
    )


tierlist_router = ar_tierlist
