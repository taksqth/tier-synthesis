from fasthtml.common import *
from .base_layout import get_full_layout


# Router setup
ar_tierlist = APIRouter(prefix="/tierlist")
ar_tierlist.name = "Tierlist"


# Drag and drop utility functions
def make_draggable(element):
    return element(
        On("event.target.classList.add('dragging')", "dragstart"),
        On("event.target.classList.remove('dragging')", "dragend"),
        draggable="true",
    )


def make_container(element, background_color="#f5f5f5"):
    return element(
        On("event.preventDefault()", "dragover"),
        On(
            """
            event.preventDefault();
            
            const source = document.querySelector('.dragging');
            const target = event.target.closest('article');
            
            if (source && target) {
                target.parentNode.insertBefore(source, target);
            } else if (source) {
                event.currentTarget.insertBefore(source, event.currentTarget.firstChild);  // Insert at start
            }
        """,
            "drop",
        ),
        style=(element.style if element.style else "")
        + f"""
            grid-template-columns: repeat(auto-fill, 186px);
            min-height: 120px;
            background-color: {background_color};
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 1rem;
            margin: 0.5rem 0;
        """,
    )


def get_image_element(image):
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
            )
        )
    )


def TierRow(tier):
    return Div(
        H3(tier),
        make_container(
            Div(
                cls="grid",
            ),
        ),
    )


# Routes
@ar_tierlist.get("/edit", name="Tierlist Editor")
def get_tierlist_editor(htmx):
    from .images_router import images

    tiers = ["S", "A", "B", "C", "D"]

    content = Container(
        H1("Image Tier List"),
        *[TierRow(tier) for tier in tiers],
        H3("Available Images"),
        make_container(
            Div(
                *[get_image_element(image) for image in images(order_by="-created_at")],
                cls="grid",
            )
        ),
    )

    if htmx.request is None:
        return get_full_layout(content)
    return content


tierlist_router = ar_tierlist
