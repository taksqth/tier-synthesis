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


def get_image_card(image, user_id: str):
    from .base_layout import tag

    image_thumbnail = process_image(image.image_data)
    is_owner = image.owner_id == user_id
    return Card(
        Img(
            src=f"data:{image.content_type};base64,{base64.b64encode(image_thumbnail).decode()}",
            alt=image.name,
        ),
        P(image.name),
        tag("Owned" if is_owner else "Shared"),
    )


def get_image_grid(images, user_id: str):
    def create_link(content, page_path):
        return A(content, hx_get=page_path, hx_target="#main", hx_push_url="true")

    return (
        Div(
            *[
                create_link(get_image_card(image, user_id), f"/images/id/{image.id}")
                for image in images
            ],
            cls="grid",
            style="""
                grid-template-columns: repeat(auto-fill, 150px);
            """,
        ),
    )


# Routes
@ar_images.get("/id/{id}")
def get_image_edit_form(id: int, htmx, request, session):
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
        for row in db.q("SELECT user_group_id FROM image_share WHERE image_id = ?", [id])
    ]

    content = (
        H1("Edit Image"),
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
                Label(
                    "Category",
                    Input(
                        name="category",
                        value=image.category,
                        placeholder="example: 'Genshin', 'HSR', etc.",
                        readonly=not can_edit,
                    ),
                ),
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
                    hx_post=f"/images/id/{id}",
                    hx_target="#main",
                    disabled=not can_edit,
                ) if can_edit else None,
            ),
        ),
    )
    return get_full_layout(content, htmx, is_admin)


@ar_images.post("/id/{id}")
def post_image_edit_form(
    id: int, name: str, category: str, shared_groups: list[str] = None, htmx=None, request=None, session=None
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


@ar_images.get("/add", name="Upload Images")
def get_image_upload_form(htmx):
    inp = Card(
        H3("Drag and drop images here"),
        Input(
            type="file",
            name="uploaded_images",
            multiple=True,
            required=True,
            accept="image/*",
        ),
        Button("Upload"),
        align="center",
    )
    add = Form(
        inp,
        enctype="multipart/form-data",
        hx_post="/images/add",
        hx_target="#image-list",
        hx_swap="afterbegin",
    )
    content = (
        H1("Upload Image"),
        add,
        H2("👇 Uploaded images 👇", align="center"),
        Div(id="image-list"),
    )
    return get_full_layout(content, htmx)


@ar_images.post("/add")
async def post_image_upload_form(uploaded_images: list[UploadFile], session):
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB limit
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

            valid_images.append(
                DBImage(
                    owner_id=owner_id,
                    name=f"Image_{uuid.uuid4().hex[:8]}",
                    image_data=image_data,
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    content_type=image.content_type,
                    category="<no category>",
                )
            )

        images_to_insert = [images.insert(image) for image in valid_images]
        return get_image_grid(images_to_insert, owner_id)

    except Exception as e:
        return Div(
            P(f"Error: {str(e)}", style="color: red; text-align: center;"),
            cls="alert alert-error",
        )


@ar_images.get("/all", name="View Gallery")
def get_image_gallery(htmx, request, session):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)
    accessible_images = get_accessible_images(user_id, is_admin)

    grid = get_image_grid(accessible_images, user_id)
    content = (H1("Image Gallery"), grid)

    return get_full_layout(content, htmx, is_admin)


images_router = ar_images
