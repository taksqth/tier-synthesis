from fasthtml.common import *  # type: ignore
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from PIL import Image
from dataclasses import dataclass
from .base_layout import get_full_layout, tag
from services.storage import get_storage_service
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# MODELS
# ============================================================================


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
    thumbnail_path: str = ""
    full_image_path: str = ""


@dataclass
class ImageShare:
    id: int
    image_id: int
    user_group_id: int


# ============================================================================
# DATABASE SETUP
# ============================================================================

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


# ============================================================================
# ROUTER SETUP
# ============================================================================

ar_images = APIRouter(prefix="/images")
ar_images.name = "Images"  # type: ignore
ar_images.show = True  # type: ignore


# ============================================================================
# DATA ACCESS LAYER
# ============================================================================


def get_user_groups_for_user(user_id: str) -> list[dict]:
    return db.q(
        """
        SELECT user_group.*
        FROM user_group
        JOIN user_group_membership ON user_group.id = user_group_membership.group_id
        WHERE user_group_membership.user_id = ?
        """,
        [user_id],
    )


def get_shared_group_ids(image_id: int) -> list[int]:
    return [
        row["user_group_id"]
        for row in db.q(
            "SELECT user_group_id FROM image_share WHERE image_id = ?", [image_id]
        )
    ]


def can_access_image(image_id: int, user_id: str, is_admin: bool):
    if is_admin:
        return True

    result = db.q(
        """
        SELECT 1 FROM db_image i
        LEFT JOIN image_share s ON i.id = s.image_id
        LEFT JOIN user_group_membership m ON s.user_group_id = m.group_id
        WHERE i.id = ? AND (i.owner_id = ? OR m.user_id = ?)
        LIMIT 1
        """,
        [image_id, user_id, user_id],
    )
    return len(result) > 0


def get_accessible_images(user_id: str, is_admin: bool):
    if is_admin:
        result = db.q("SELECT * FROM db_image ORDER BY created_at DESC")
    else:
        result = db.q(
            """
            SELECT DISTINCT i.*
            FROM db_image i
            LEFT JOIN image_share s ON i.id = s.image_id
            LEFT JOIN user_group_membership m ON s.user_group_id = m.group_id
            WHERE i.owner_id = ? OR m.user_id = ?
            ORDER BY i.created_at DESC
            """,
            [user_id, user_id],
        )

    return [DBImage(**row) for row in result]


def get_category_images(category: str, user_id: str, is_admin: bool) -> list[DBImage]:
    accessible_images = get_accessible_images(user_id, is_admin)
    return [img for img in accessible_images if img.category == category]


# ============================================================================
# RENDERING COMPONENTS
# ============================================================================


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


def get_image_card(image, user_id: str):
    from .users_router import get_user_avatar

    username, avatar_url = get_user_avatar(image.owner_id)
    storage = get_storage_service()
    thumbnail_url = storage.generate_signed_url(image.thumbnail_path)

    is_owner = image.owner_id == user_id
    return Card(
        Header(
            Img(src=avatar_url, alt="avatar", cls="avatar small"),
            Small(username),
            tag("Owned" if is_owner else "Shared"),
            cls="user-info",
        ),
        Div(
            Img(
                src=thumbnail_url,
                alt=image.name,
                loading="lazy",
            ),
            P(image.name),
            align="center",
        ),
    )


def get_image_cards(images, user_id: str):
    return [
        A(
            get_image_card(image, user_id),
            href=f"/images/id/{image.id}",
            hx_boost="true",
            hx_target="#main",
        )
        for image in images
    ]


def get_image_grid(images, user_id: str):
    return Grid(
        *get_image_cards(images, user_id),
        cls="flex-wrap",
    )


def ImageEditPage(
    image: Any,
    can_edit: bool,
    user_groups: list[dict],
    shared_group_ids: list[int],
    categories: list[str],
    viewer_id: str,
) -> Any:
    from components.user_display import UserDisplay

    storage = get_storage_service()
    full_image_url = storage.generate_signed_url(image.full_image_path)

    return (
        Header(
            H1("Edit image"),
            Button(
                "Delete",
                hx_delete=f"{ar_images.prefix}/id/{image.id}",
                hx_confirm="Delete this image?",
                hx_target="#main",
                cls="secondary outline",
            )
            if can_edit
            else None,
            cls="flex-row",
        ),
        Div(
            UserDisplay(image.owner_id, viewer_id),
            cls="user-info header",
        ),
        Img(
            src=full_image_url,
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
                Label(
                    "Change image",
                    Input(
                        type="file",
                        name="new_uploaded_image",
                        accept="image/*",
                    ),
                ),
                category_input(categories, value=image.category, readonly=not can_edit),
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
                            )
                            for group in user_groups
                        ],
                    )
                    if user_groups
                    else None
                ),
                Button("Submit") if can_edit else None,
            ),
            enctype="multipart/form-data",
            hx_post=f"{ar_images.prefix}/id/{image.id}",
            hx_target="#main",
            hx_vals="""js:{
                shared_groups: Array.from(document.querySelectorAll('input[name="shared_groups"]:checked')).map(cb => cb.value).join(',')
            }""",
        ),
    )


def ImageUploadPage(categories: list[str], user_groups: list[dict]) -> Any:
    return (
        H1("Upload Image"),
        Form(
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
                category_input(
                    categories, input_id="upload-category-input", required=True
                ),
                (
                    Label(
                        "Share with groups",
                        *[
                            CheckboxX(
                                name="shared_groups",
                                value=str(group["id"]),
                                label=group["groupname"],
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
            hx_vals="""js:{
                shared_groups: Array.from(document.querySelectorAll('input[name="shared_groups"]:checked')).map(cb => cb.value).join(',')
            }""",
            hx_target="#image-list",
            hx_swap="afterbegin",
            hx_on__after_request="this.reset()",
        ),
        H2("👇 Uploaded images 👇", align="center"),
        Grid(id="image-list", cls="flex-wrap"),
    )


def ImageGalleryPage(
    filtered_images: list[Any],
    user_id: str,
    categories: list[str],
    selected_category: str,
    mine_only: bool,
) -> Any:
    return (
        H1("Image Gallery"),
        Div(
            Label(
                "Filter by category",
                Select(
                    Option("All", value="", selected=(not selected_category)),
                    *[
                        Option(cat, value=cat, selected=(cat == selected_category))
                        for cat in categories
                    ],
                    name="category",
                    hx_get=f"{ar_images.prefix}/list",
                    hx_target="#main",
                    hx_include="[name='mine_only']",
                ),
            ),
            CheckboxX(
                name="mine_only",
                value="true",
                checked=mine_only,
                label="Show only mine",
                hx_get=f"{ar_images.prefix}/list",
                hx_target="#main",
                hx_include="[name='category']",
            ),
            style="display: flex; gap: 1rem; align-items: center; margin-bottom: 1rem;",
        ),
        get_image_grid(filtered_images, user_id),
    )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


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


async def get_safe_image_data(image: UploadFile) -> tuple[bytes, str]:
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    MAX_IMAGE_SIZE = 10 * 1024 * 1024

    if image.content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Invalid file type: {image.content_type}")

    image_data = await image.read()

    if len(image_data) > MAX_IMAGE_SIZE:
        raise ValueError(f"File too large: {image.filename}")

    img = Image.open(BytesIO(image_data))
    img.verify()

    img = Image.open(BytesIO(image_data))
    img.load()

    return image_data, image.content_type


async def save_uploaded_image(image: DBImage, uploaded_file: UploadFile) -> None:
    storage = get_storage_service()

    if image.thumbnail_path:
        storage.delete_image(image.thumbnail_path)
    if image.full_image_path:
        storage.delete_image(image.full_image_path)

    image_data, content_type = await get_safe_image_data(uploaded_file)
    thumbnail_data = process_image(image_data)

    image.thumbnail_path = storage.save_image(
        thumbnail_data, image.id, content_type, is_thumbnail=True
    )
    image.full_image_path = storage.save_image(
        image_data, image.id, content_type, is_thumbnail=False
    )
    image.image_data = b""
    image.thumbnail_data = b""


# ============================================================================
# FEATURE: IMAGE SERVING
# ============================================================================


@ar_images.get("/img")
def serve_image(path: str, expires: int, sig: str):
    storage = get_storage_service()

    if not storage.validate_signature(path, expires, sig):
        return Response("Forbidden", status_code=403)

    safe_path = Path(path).as_posix()
    if ".." in safe_path or safe_path.startswith("/"):
        logger.warning(f"Path traversal attempt detected: {path}")
        return Response("Invalid path", status_code=400)

    full_path = os.path.join(storage.storage_path, safe_path)

    try:
        real_full_path = os.path.realpath(full_path)
        real_storage_path = os.path.realpath(storage.storage_path)
        if not real_full_path.startswith(real_storage_path + os.sep):
            logger.warning(f"Path traversal attempt blocked: {path}")
            return Response("Forbidden", status_code=403)
    except (OSError, ValueError) as e:
        logger.error(f"Path validation error: {e}")
        return Response("Invalid path", status_code=400)

    if not os.path.exists(full_path):
        return Response("Not found", status_code=404)

    return FileResponse(
        full_path, headers={"Cache-Control": "public, max-age=31536000, immutable"}
    )


# ============================================================================
# FEATURE: IMAGE CRUD
# ============================================================================


@ar_images.get("/id/{id}")
def get_image_edit_form(id: int, htmx, request, session):
    from .category_utils import get_all_categories

    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    if not can_access_image(id, user_id, is_admin):
        return get_full_layout(
            (
                H1("Access Denied"),
                P("You don't have access to this image."),
            ),
            htmx,
            is_admin,
        )

    image = images[id]
    can_edit = image.owner_id == user_id or is_admin

    user_groups = get_user_groups_for_user(user_id)
    shared_group_ids = get_shared_group_ids(id)
    categories = get_all_categories()

    content = ImageEditPage(
        image, can_edit, user_groups, shared_group_ids, categories, user_id
    )
    return get_full_layout(content, htmx, is_admin)


@ar_images.post("/id/{id}")
async def post_image_edit_form(
    id: int,
    name: str,
    category: str,
    htmx,
    request,
    session,
    shared_groups: str | None = None,
    new_uploaded_image: UploadFile | None = None,
) -> Any:
    from .category_utils import validate_and_get_category

    image = images[id]
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    if image.owner_id != user_id and not is_admin:
        return get_full_layout(
            (
                H1("Access Denied"),
                P("You don't have permission to edit this image."),
            ),
            htmx,
            is_admin,
        )

    try:
        validated_category = validate_and_get_category(category)
    except ValueError as e:
        return get_full_layout(
            P(f"Category error: {e}", cls="error-text"), htmx, is_admin
        )

    image.name = name
    image.category = validated_category

    if new_uploaded_image:
        await save_uploaded_image(image, new_uploaded_image)

    images.update(image)

    db.q("DELETE FROM image_share WHERE image_id = ?", [id])
    if shared_groups:
        for group_id in shared_groups.split(","):
            if group_id:
                image_shares.insert(image_id=id, user_group_id=int(group_id))

    return get_image_edit_form(id, htmx, request, session)


@ar_images.delete("/id/{id}")
def delete_image(id: int, htmx, request, session):
    owner_id = session.get("user_id")
    image = images[id]

    if image.owner_id != owner_id:
        return RedirectResponse("/unauthorized", status_code=303)

    storage = get_storage_service()
    if image.thumbnail_path:
        storage.delete_image(image.thumbnail_path)
    if image.full_image_path:
        storage.delete_image(image.full_image_path)

    images.delete(id)
    return get_image_gallery(htmx, request, session)


# ============================================================================
# FEATURE: IMAGE UPLOAD
# ============================================================================


@ar_images.get("/new", name="Upload Images")
def get_image_upload_form(htmx, session, request):
    from .category_utils import get_all_categories

    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    categories = get_all_categories()
    user_groups = get_user_groups_for_user(user_id)

    content = ImageUploadPage(categories, user_groups)
    return get_full_layout(content, htmx, is_admin)


@ar_images.post("/new")
async def post_image_upload_form(
    uploaded_images: list[UploadFile],
    session,
    category: str = "",
    shared_groups: str | None = None,
):
    from .category_utils import validate_and_get_category

    owner_id = session.get("user_id")

    try:
        validated_category = validate_and_get_category(category or "unclassified")
    except ValueError as e:
        return P(f"Category error: {e}", style="color: red;")

    images_to_insert = []

    for image in uploaded_images:
        img = images.insert(
            owner_id=owner_id,
            name=f"Image_{uuid.uuid4().hex[:8]}",
            image_data=b"",
            thumbnail_data=b"",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            content_type="",
            category=validated_category,
            thumbnail_path="",
            full_image_path="",
        )

        await save_uploaded_image(img, image)
        images.update(img)

        images_to_insert.append(img)

    if shared_groups:
        for group_id in shared_groups.split(","):
            if group_id:
                image_shares.insert(image_id=id, user_group_id=int(group_id))

    return get_image_cards(images_to_insert, owner_id)


# ============================================================================
# FEATURE: IMAGE GALLERY
# ============================================================================


@ar_images.get("/list", name="View Gallery")
def get_image_gallery(htmx, request, session, category: str = "", mine_only: str = ""):
    from .category_utils import get_all_categories

    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    accessible_images = get_accessible_images(user_id, is_admin)
    categories = get_all_categories()

    if category and category != "All":
        filtered_images = [img for img in accessible_images if img.category == category]
    else:
        filtered_images = accessible_images

    if mine_only == "true":
        filtered_images = [img for img in filtered_images if img.owner_id == user_id]

    content = ImageGalleryPage(
        filtered_images, user_id, categories, category, mine_only == "true"
    )
    return get_full_layout(content, htmx, is_admin)


@ar_images.get("/categories")
def get_categories():
    from .category_utils import get_all_categories

    return get_all_categories()


# ============================================================================
# EXPORT
# ============================================================================

images_router = ar_images
