from fasthtml.common import *  # type: ignore


def ImageGrid(
    title: str,
    description: str = "",
    images: list = [],
    action_button: Any = None,
    render_card = None,
    single_row: bool = False,
) -> Any:
    """Unified image grid component for displaying collections of images.

    Args:
        title: Section title
        description: Optional description text
        images: List of items to render (images or data dicts)
        action_button: Optional button/link in header
        render_card: Optional custom card renderer function, otherwise uses simple image display
        single_row: If True, displays in single row with horizontal scroll (showcase mode)
                    If False, wraps to multiple rows (gallery mode)
    """
    if not images:
        return None

    grid_class = "image-row" if single_row else "flex-wrap"

    return Article(
        Header(
            H2(title),
            action_button if action_button else None,
            cls="flex-row" if action_button else None,
        ),
        P(description) if description else None,
        Div(
            *[
                render_card(item) if render_card else item
                for item in images
                if (render_card(item) if render_card else item) is not None
            ],
            cls=grid_class,
        ),
    )
