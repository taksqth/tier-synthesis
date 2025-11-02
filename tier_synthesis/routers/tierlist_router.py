from fasthtml.common import *
from .base_layout import get_full_layout
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime
import os
import uuid
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class DBTierlist:
    TIERS = ["S", "A", "B", "C", "D"]

    id: int
    owner_id: str
    selected_groups: str
    name: str
    data: str
    created_at: str

    @classmethod
    def create_empty(cls, selected_groups: str = "") -> "DBTierlist":
        """Create a new empty tierlist"""
        logger.info(
            f"Creating new empty tierlist with selected_groups: {selected_groups}"
        )
        tierlist = cls(
            id=0,
            owner_id="",
            selected_groups=selected_groups,
            name="New Tierlist",
            data=json.dumps({tier: [] for tier in cls.TIERS}),
            created_at=datetime.now().isoformat(),
        )
        logger.debug(f"Created empty tierlist: {tierlist}")
        return tierlist

    def get_selected_groups(self) -> list[str]:
        """Get list of selected groups"""
        return self.selected_groups.split(",") if self.selected_groups else []

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

    def _get_selected_groups_js(self) -> str:
        """Get JavaScript to extract selected groups from the DOM"""
        return """Array.from(
            document.querySelector('details[name="selected_groups"]')
                .querySelectorAll('input[type="checkbox"]:checked')
        ).map(cb => cb.value).join(',')"""

    def _get_tierlist_data_js(self) -> str:
        """Get JavaScript to extract tierlist data from the DOM"""
        return """Object.fromEntries(
            Array.from(document.querySelectorAll('[data-tier]')).map(tier => [
                tier.dataset.tier,
                Array.from(tier.querySelectorAll('div'))
                    .map(div => div.dataset.imageId)
            ])
        )"""

    def render_page(self, images: list) -> Container:
        """Render the full tierlist editor page"""
        groups = set(image.group for image in images)
        selected_groups = self.get_selected_groups()

        filtered_images = [
            image
            for image in images
            if not selected_groups or image.group in selected_groups
        ]

        tierlist_data, leftover_images = self.get_tier_data(filtered_images)

        return Div(
            H1("Image Tier List"),
            self._create_save_form(),
            self._create_group_selector(groups, selected_groups),
            P(
                "Currently filtering: ",
                Em(", ".join(selected_groups) if selected_groups else "All groups"),
            ),
            *[
                self._create_tier_row(tier, tierlist_data[tier])
                for tier in tierlist_data.keys()
            ],
            H2("Available Images"),
            make_container(
                Div(
                    *leftover_images,
                    cls="grid",
                )
            ),
            **{
                "x-data": f"{{ dragging: null, selectedGroups: {json.dumps(selected_groups)} }}"
            },
        )

    def _get_image_element(self, image):
        """Create image element for tierlist"""
        from .images_router import process_image
        import base64

        image_thumbnail = process_image(image.image_data)
        return make_draggable(
            Div(
                Img(
                    src=f"data:{image.content_type};base64,{base64.b64encode(image_thumbnail).decode()}",
                    alt=image.name,
                    draggable="false",
                    style="pointer-events: none;",
                ),
                data_image_id=str(image.id),
            )
        )

    def _create_tier_row(self, tier: str, images: list = None):
        """Create a tier row"""
        return Div(
            H3(tier),
            make_container(
                Div(
                    *(images or []),
                    cls="grid",
                    data_tier=tier,
                ),
            ),
        )

    def _create_save_form(self):
        return (
            Label(
                "Name",
                Group(
                    Input(
                        name="tierlist_name",
                        value=self.name,
                        placeholder="My Tierlist",
                        id="tierlist-name-input",
                    ),
                    Button(
                        "Save",
                        hx_post="/tierlist/save",
                        hx_vals=f"""js:{{
                            tierlist: {self._get_tierlist_data_js()},
                            selected_groups: {self._get_selected_groups_js()},
                            tierlist_id: {self.id if self.id else 0},
                            name: document.getElementById('tierlist-name-input').value,
                        }}""",
                        hx_target="#main",
                        cls="primary",
                    ),
                    cls="flex-row",
                    style="margin-bottom: 2rem;",
                ),
            ),
        )

    def _create_group_selector(self, groups, selected_groups):
        """Create group selector using Alpine.js for state management"""
        return Group(
            Details(
                Summary("Select Groups"),
                Ul(
                    *[
                        Li(
                            Label(
                                Input(
                                    type="checkbox",
                                    name="group",
                                    value=group,
                                    **{"x-model": "selectedGroups"},
                                ),
                                group,
                            )
                        )
                        for group in groups
                    ]
                ),
                name="selected_groups",
                cls="dropdown",
            ),
            Button(
                "Apply",
                hx_get="/tierlist/edit",
                hx_vals=f"""js:{{
                    selected_groups: {self._get_selected_groups_js()}
                }}""",
                hx_target="#main",
            ),
        )

    @staticmethod
    def render_list(tierlist_list: list["DBTierlist"]):
        """Render list of tierlists for the current user"""
        return Div(
            Header(
                H1("My Tierlists"),
                A(
                    "Create New",
                    hx_get="/tierlist/edit",
                    hx_target="#main",
                    hx_push_url="true",
                    cls="primary",
                    role="button",
                ),
                cls="flex-row",
                style="margin-bottom: 2rem;",
            ),
            Ul(
                *[
                    Li(
                        A(
                            f"{tierlist.name} - {tierlist.created_at[:10]}",
                            href=f"/tierlist/edit?tierlist_id={tierlist.id}",
                            hx_get=f"/tierlist/edit?tierlist_id={tierlist.id}",
                            hx_target="#main",
                            hx_push_url="true",
                        ),
                        Button(
                            "Delete",
                            hx_delete=f"/tierlist/id/{tierlist.id}",
                            hx_confirm="Delete this tierlist?",
                            hx_target="#main",
                            cls="secondary outline",
                        ),
                        cls="flex-row clickable-list-item",
                    )
                    for tierlist in tierlist_list
                ],
                style="list-style: none; padding: 0;",
            )
            if tierlist_list
            else P(
                "No tierlists yet. Create one to get started!",
                style="text-align: center; margin: 2rem 0;",
            ),
        )


db = database(os.environ.get("DB_PATH", "app/database.db"))
tierlists = db.create(
    DBTierlist,
    pk="id",
    foreign_keys=[("owner_id", "user")],
    transform=True,
)


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


def make_container(element, background_color="#f5f5f5"):
    """Create a draggable container with drop zone functionality using Alpine.js"""
    return element(
        **{
            "x-on:dragover": "$event.preventDefault()",
            "x-on:drop": """
                $event.preventDefault();
                const target = $event.target.closest('article');
                if (dragging && target) {
                    target.parentNode.insertBefore(dragging, target);
                } else if (dragging) {
                    $event.currentTarget.insertBefore(dragging, $event.currentTarget.firstChild);
                }
            """,
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
@ar_tierlist.get("/edit", name="Tierlist Editor")
def get_tierlist_editor(htmx, request, selected_groups: str = "", tierlist_id: int = 0):
    from .images_router import images

    logger.info(
        f"Loading tierlist editor. Tierlist ID: {tierlist_id}, Selected groups: {selected_groups}"
    )

    if tierlist_id:
        logger.info(f"Attempting to load existing tierlist with id: {tierlist_id}")
        tierlist = tierlists[tierlist_id]
        logger.debug(f"Loaded tierlist: {tierlist}")
    else:
        logger.info("Creating new tierlist")
        tierlist = DBTierlist.create_empty(selected_groups)

    images_query = images(order_by="-created_at")
    logger.debug(f"Loaded {len(images_query)} images for tierlist")

    content = tierlist.render_page(images_query)
    logger.info("Tierlist page rendered successfully")

    return get_full_layout(content, htmx, request.scope.get("is_admin", False))


@ar_tierlist.post("/save")
def save_tierlist(
    htmx,
    request,
    session,
    tierlist: str,
    selected_groups: str,
    name: str,
    tierlist_id: int = 0,
):
    owner_id = session.get("user_id")
    logger.info(
        f"Saving tierlist. ID: {tierlist_id}, Data: {tierlist}, Groups: {selected_groups}"
    )

    if tierlist_id:
        existing = tierlists[tierlist_id]
        existing.data = tierlist
        existing.selected_groups = selected_groups
        existing.name = name
        tierlists.update(existing)
    else:
        result = tierlists.insert(
            {
                "owner_id": owner_id,
                "name": name,
                "data": tierlist,
                "selected_groups": selected_groups,
                "created_at": datetime.now().isoformat(),
            }
        )
        tierlist_id = result.id

    return get_tierlist_editor(
        htmx, request, tierlist_id=tierlist_id, selected_groups=selected_groups
    )


@ar_tierlist.get("/list", name="My Tierlists")
def list_tierlists(htmx, request, session):
    owner_id = session.get("user_id")
    tierlist_list = tierlists(where=f"owner_id = '{owner_id}'", order_by="-created_at")
    content = DBTierlist.render_list(tierlist_list)
    return get_full_layout(content, htmx, request.scope.get("is_admin", False))


@ar_tierlist.delete("/id/{tierlist_id}")
def delete_tierlist(tierlist_id: str, htmx, request, session):
    tierlists.delete(tierlist_id)
    return list_tierlists(htmx, request, session)


tierlist_router = ar_tierlist
