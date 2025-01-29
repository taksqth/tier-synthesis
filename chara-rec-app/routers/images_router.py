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
    name: str
    group: str
    image_data: bytes
    content_type: str
    created_at: str


db = database(os.environ.get("DB_PATH", "app/database.db"))
images = db.create(
    DBImage,
    pk="id",
    transform=True,
)


# Router setup
ar_images = APIRouter(prefix="/images")
ar_images.name = "Images"


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


def get_image_card(image):
    image_thumbnail = process_image(image.image_data)
    return Card(
        Img(
            src=f"data:{image.content_type};base64,{base64.b64encode(image_thumbnail).decode()}",
            alt=image.name,
        ),
        P(image.name),
    )


def get_image_grid(images):
    def create_link(content, page_path):
        return A(content, hx_get=page_path, hx_target="#main", hx_push_url="true")

    return (
        Div(
            *[
                create_link(get_image_card(image), f"/images/id/{image.id}")
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
def get_image_edit_form(id: int, htmx):
    image = images[id]
    content = Card(
        H1("Edit Image", align="center"),
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
                    ),
                ),
                Label(
                    "Group",
                    Input(
                        name="group",
                        value=image.group,
                        placeholder="example: 'Genshin', 'HSR', etc.",
                    ),
                ),
                Input(
                    type="submit",
                    value="Submit",
                    hx_post=f"/images/id/{id}",
                    hx_target="#main",
                ),
            ),
        ),
    )
    if htmx.request is None:
        return get_full_layout(content)
    return content


@ar_images.post("/id/{id}")
def post_image_edit_form(id: int, name: str, group: str, htmx):
    image = images[id]
    image.name = name
    image.group = group
    images.update(image)
    return get_image_gallery(htmx)


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
    content = Container(
        H1("Upload Image"),
        add,
        H3("👇 Uploaded images 👇", align="center"),
        Div(id="image-list"),
    )
    if htmx.request is None:
        return get_full_layout(content)
    return content


@ar_images.post("/add")
async def post_image_upload_form(uploaded_images: list[UploadFile]):
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB limit

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
                    name=f"Image_{uuid.uuid4().hex[:8]}",
                    image_data=image_data,
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    content_type=image.content_type,
                    group="<no group>",
                )
            )

        images_to_insert = [images.insert(image) for image in valid_images]
        return get_image_grid(images_to_insert)

    except Exception as e:
        return Div(
            P(f"Error: {str(e)}", style="color: red; text-align: center;"),
            cls="alert alert-error",
        )


@ar_images.get("/all", name="View Gallery")
def get_image_gallery(htmx):
    grid = get_image_grid(images(order_by="-created_at"))
    content = Container(H1("Image Gallery"), grid)

    if htmx.request is None:
        return get_full_layout(content)
    return content


images_router = ar_images
