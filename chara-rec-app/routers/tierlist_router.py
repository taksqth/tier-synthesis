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


def create_group_selector(groups, selected_groups):
    """Create the group selection dropdown with checkboxes"""
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
                                checked=(group in selected_groups),
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
            hx_vals="""js:{
                selected_groups: Array.from(
                    document.querySelector('details[name="selected_groups"]')
                        .querySelectorAll('input[type="checkbox"]:checked')
                ).map(cb => cb.value).join(',')
            }""",
            hx_target="#main",
        ),
    )


def create_tier_rows(tiers):
    """Create the tier list rows"""
    return [TierRow(tier) for tier in tiers]


def create_images_container(images):
    """Create the container for available images"""
    return make_container(
        Div(
            *[get_image_element(image) for image in images],
            cls="grid",
        )
    )


# Routes
@ar_tierlist.get("/edit", name="Tierlist Editor")
def get_tierlist_editor(htmx, selected_groups: str = ""):
    from .images_router import images

    tiers = ["S", "A", "B", "C", "D"]
    selected_groups = selected_groups.split(",") if selected_groups else []
    images_query = images(order_by="-created_at")

    groups = set(image.group for image in images_query)
    filtered_images = [
        image
        for image in images_query
        if (len(selected_groups) == 0 or image.group in selected_groups)
    ]

    content = Container(
        H1("Image Tier List"),
        create_group_selector(groups, selected_groups),
        P(
            "Currently filtering: ",
            Em(", ".join(selected_groups) if selected_groups else "All groups"),
        ),
        *create_tier_rows(tiers),
        H3("Available Images"),
        create_images_container(filtered_images),
    )

    return get_full_layout(content) if htmx.request is None else content


tierlist_router = ar_tierlist
