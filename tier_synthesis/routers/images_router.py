import uuid
import base64
from datetime import datetime
from io import BytesIO
from PIL import Image
from fasthtml.common import *
from dataclasses import dataclass
from .base_layout import get_full_layout


@dataclass
class DBImage:
    id: int
    owner_id: str
    name: str
    category: str
    image_data: bytes
    thumbnail_data: bytes
    content_type: str
    created_at: str


@dataclass
class ImageShare:
    id: int
    image_id: int
    user_group_id: int


db = database(os.environ.get("DB_PATH", "app/database.db"))
images = db.create(
    DBImage,
    pk="id",
    foreign_keys=[("owner_id", "user")],
    transform=True,
)
image_shares = db.create(
    ImageShare,
    pk="id",
    foreign_keys=(("image_id", "db_image"), ("user_group_id", "user_group")),
    transform=True,
)


# Router setup
ar_images = APIRouter(prefix="/images")
ar_images.name = "Images"
ar_images.show = True


def category_input(
    categories, input_id="category-input", value="", readonly=False, required=False
):
    return Label(
        "Category",
        Input(
            name="category",
            value=value,
            placeholder="example: 'Genshin', 'HSR', etc.",
            readonly=readonly,
            required=required,
            id=input_id,
        ),
        Small(
            *[
                Span(
                    cat,
                    cls="tag clickable",
                    onclick=f"document.getElementById('{input_id}').value = '{cat}'",
                )
                for cat in categories
            ]
        )
        if not readonly and categories
        else None,
    )


# Access control
def get_accessible_images(user_id: str, is_admin: bool):
    """Get images the user can access (owned, shared with their groups, or user is admin)"""
    if is_admin:
        result = db.q("SELECT * FROM db_image ORDER BY created_at DESC")
    else:
        result = db.q(
            """
            SELECT DISTINCT db_image.*
            FROM db_image
            LEFT JOIN image_share ON db_image.id = image_share.image_id
            LEFT JOIN user_group_membership ON image_share.user_group_id = user_group_membership.group_id
            WHERE db_image.owner_id = ?
               OR user_group_membership.user_id = ?
            ORDER BY db_image.created_at DESC
            """,
            [user_id, user_id],
        )
    return [DBImage(**row) for row in result]


# Utility and component functions
def process_image(img_data):
    img = Image.open(BytesIO(img_data))
    format = img.format

    width, height = img.size
    crop_size = min(width, height)
    left = (width - crop_size) // 2
    top = (height - crop_size) * 2 // 10
    img = img.crop((left, top, left + crop_size, top + crop_size))

    img.thumbnail((128, 128), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    img.save(buffer, format=format)
    return buffer.getvalue()


def get_image_thumbnail(image):
    """Get thumbnail for an image, generating and caching if needed"""
    if image.thumbnail_data:
        return image.thumbnail_data

    thumbnail = process_image(image.image_data)
    image.thumbnail_data = thumbnail
    images.update(image)
    return thumbnail


def get_image_card(image, user_id: str):
    from .base_layout import tag
    from .users_router import get_user_avatar

    thumbnail = get_image_thumbnail(image)
    username, avatar_url = get_user_avatar(image.owner_id)

    is_owner = image.owner_id == user_id
    return Card(
        Div(
            Img(
                src=avatar_url,
                alt="avatar",
                cls="avatar",
                style="width: 24px; height: 24px; border-radius: 50%; vertical-align: middle;",
            ),
            Small(username, style="margin-left: 0.5em;"),
            style="display: flex; align-items: center; margin-bottom: 0.5em;",
        ),
        Img(
            src=f"data:{image.content_type};base64,{base64.b64encode(thumbnail).decode()}",
            alt=image.name,
        ),
        P(image.name),
        tag("Owned" if is_owner else "Shared"),
    )


def get_image_cards(images, user_id: str):
    return [
        Article(
            get_image_card(image, user_id),
            hx_get=f"/images/id/{image.id}",
            hx_target="#main",
            hx_push_url="true",
            style="cursor: pointer;",
        )
        for image in images
    ]


def get_image_grid(images, user_id: str):
    return Div(
        *get_image_cards(images, user_id),
        cls="grid",
        style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));",
    )


# Routes
@ar_images.get("/id/{id}")
def get_image_edit_form(id: int, htmx, request, session):
    from .users_router import get_user_avatar

    image = images[id]
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    accessible_images = get_accessible_images(user_id, is_admin)
    if not any(img.id == id for img in accessible_images):
        return get_full_layout(
            H1("Access Denied"),
            P("You don't have access to this image."),
            htmx,
            is_admin,
        )

    can_edit = image.owner_id == user_id or is_admin

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
            "SELECT user_group_id FROM image_share WHERE image_id = ?", [id]
        )
    ]

    categories = sorted(set(img.category for img in accessible_images if img.category))
    username, avatar_url = get_user_avatar(image.owner_id)

    content = (
        Header(
            H1("Edit image"),
            Button(
                "Delete",
                hx_delete=f"{ar_images.prefix}/id/{id}",
                hx_confirm="Delete this image?",
                hx_target="#main",
                hx_push_url="true",
                cls="secondary outline",
            ),
            cls="flex-row",
        ),
        Div(
            Img(
                src=avatar_url,
                alt="avatar",
                cls="avatar",
                style="width: 32px; height: 32px; border-radius: 50%; vertical-align: middle;",
            ),
            Strong(username, style="margin-left: 0.5em;"),
            style="display: flex; align-items: center; margin-bottom: 1em;",
        ),
        Img(
            src=f"data:{image.content_type};base64,{base64.b64encode(image.image_data).decode()}",
            alt=image.name,
            style="max-width: 200px; display: block; margin: 0 auto;",
        ),
        Form(
            Fieldset(
                Label(
                    "Name",
                    Input(
                        name="name",
                        value=image.name,
                        required=True,
                        placeholder="example: 'Klee', 'Albedo', 'Ganyu', etc.",
                        readonly=not can_edit,
                    ),
                ),
                category_input(categories, value=image.category, readonly=not can_edit),
                (
                    Label(
                        "Share with groups",
                        *[
                            Label(
                                Input(
                                    type="checkbox",
                                    name="shared_groups",
                                    value=str(group["id"]),
                                    checked=group["id"] in shared_group_ids,
                                    disabled=not can_edit,
                                ),
                                group["groupname"],
                            )
                            for group in user_groups
                        ],
                    )
                    if user_groups
                    else None
                ),
                Input(
                    type="submit",
                    value="Submit",
                    hx_post=f"{ar_images.prefix}/id/{id}",
                    hx_target="#main",
                    hx_push_url="true",
                    disabled=not can_edit,
                )
                if can_edit
                else None,
            ),
        ),
    )
    return get_full_layout(content, htmx, is_admin)


@ar_images.post("/id/{id}")
def post_image_edit_form(
    id: int,
    name: str,
    category: str,
    htmx,
    request,
    session,
    shared_groups: list[str] = None,
):
    image = images[id]
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    if image.owner_id != user_id and not is_admin:
        return get_full_layout(
            H1("Access Denied"),
            P("You don't have permission to edit this image."),
            htmx,
            is_admin,
        )

    image.name = name
    image.category = category
    images.update(image)

    db.q("DELETE FROM image_share WHERE image_id = ?", [id])
    if shared_groups:
        for group_id in shared_groups:
            image_shares.insert({"image_id": id, "user_group_id": int(group_id)})

    return get_image_gallery(htmx, request, session)


@ar_images.delete("/id/{id}")
def delete_image(id: int, htmx, request, session):
    owner_id = session.get("user_id")
    image = images[id]

    if image.owner_id != owner_id:
        logger.warning(
            f"User {owner_id} attempted to delete image {id} owned by {image.owner_id}"
        )
        return RedirectResponse("/unauthorized", status_code=303)

    images.delete(id)
    return get_image_gallery(htmx, request, session)


@ar_images.get("/new", name="Upload Images")
def get_image_upload_form(htmx, session, request):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    accessible_images = get_accessible_images(user_id, is_admin)
    categories = sorted(set(img.category for img in accessible_images if img.category))

    user_groups = db.q(
        """
        SELECT user_group.*
        FROM user_group
        JOIN user_group_membership ON user_group.id = user_group_membership.group_id
        WHERE user_group_membership.user_id = ?
        """,
        [user_id],
    )

    add = Form(
        Card(
            P(Strong("Drag and drop images here")),
            Input(
                type="file",
                name="uploaded_images",
                multiple=True,
                required=True,
                accept="image/*",
            ),
            align="center",
        ),
        Fieldset(
            category_input(categories, input_id="upload-category-input", required=True),
            (
                Label(
                    "Share with groups",
                    *[
                        Label(
                            Input(
                                type="checkbox",
                                name="shared_groups",
                                value=str(group["id"]),
                            ),
                            group["groupname"],
                        )
                        for group in user_groups
                    ],
                )
                if user_groups
                else None
            ),
            Button("Upload"),
        ),
        enctype="multipart/form-data",
        hx_post=f"{ar_images.prefix}/new",
        hx_target="#image-list",
        hx_swap="afterbegin",
        hx_on__after_request="this.reset()",
    )
    content = (
        H1("Upload Image"),
        add,
        H2("👇 Uploaded images 👇", align="center"),
        Div(
            id="image-list",
            cls="grid",
            style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));",
        ),
    )
    return get_full_layout(content, htmx, is_admin)


@ar_images.post("/new")
async def post_image_upload_form(
    uploaded_images: list[UploadFile],
    category: str = "",
    shared_groups: list[str] = None,
    session = None,
):
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    MAX_IMAGE_SIZE = 10 * 1024 * 1024
    owner_id = session.get("user_id")

    try:
        valid_images = []
        for image in uploaded_images:
            if image.content_type not in ALLOWED_MIME_TYPES:
                raise ValueError(f"Invalid file type: {image.content_type}")

            image_data = await image.read()

            if len(image_data) > MAX_IMAGE_SIZE:
                raise ValueError(f"File too large: {image.filename}")

            img = Image.open(BytesIO(image_data))
            img.verify()

            img = Image.open(BytesIO(image_data))
            img.load()

            thumbnail_data = process_image(image_data)

            valid_images.append(
                DBImage(
                    owner_id=owner_id,
                    name=f"Image_{uuid.uuid4().hex[:8]}",
                    image_data=image_data,
                    thumbnail_data=thumbnail_data,
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    content_type=image.content_type,
                    category=category or "unclassified",
                )
            )

        images_to_insert = [images.insert(image) for image in valid_images]

        if shared_groups:
            for img in images_to_insert:
                for group_id in shared_groups:
                    image_shares.insert({"image_id": img.id, "user_group_id": int(group_id)})

        return get_image_cards(images_to_insert, owner_id)

    except Exception as e:
        return Div(
            P(f"Error: {str(e)}", style="color: red; text-align: center;"),
            cls="alert alert-error",
        )


@ar_images.get("/list", name="View Gallery")
def get_image_gallery(htmx, request, session, category: str = ""):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)
    accessible_images = get_accessible_images(user_id, is_admin)

    categories = sorted(set(img.category for img in accessible_images if img.category))

    if category:
        filtered_images = [img for img in accessible_images if img.category == category]
    else:
        filtered_images = accessible_images

    grid = get_image_grid(filtered_images, user_id)
    content = (
        H1("Image Gallery"),
        Label(
            "Filter by category",
            Select(
                Option("All", value="", selected=(not category)),
                *[
                    Option(cat, value=cat, selected=(cat == category))
                    for cat in categories
                ],
                name="category",
                hx_get=f"{ar_images.prefix}/list",
                hx_target="#main",
                hx_push_url="true",
                hx_include="this",
            ),
        ),
        grid,
    )

    return get_full_layout(content, htmx, is_admin)


@ar_images.get("/categories")
def get_categories(request, session):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)
    accessible_images = get_accessible_images(user_id, is_admin)

    categories = sorted(set(img.category for img in accessible_images if img.category))
    return categories


images_router = ar_images
