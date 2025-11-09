from fasthtml.common import *  # type: ignore


def ImageCard(
    image: Any,
    metadata: Any = None,
    footer: Any = None,
    show_name: bool = True,
) -> Any:
    """Base image card component with optional metadata and footer sections."""
    from services.storage import get_storage_service

    storage = get_storage_service()
    thumbnail_url = storage.generate_signed_url(image.thumbnail_path)

    return Article(
        metadata if metadata else None,
        A(
            Img(
                src=thumbnail_url,
                alt=image.name,
                style="width: 100%; cursor: pointer;",
            ),
            href=f"/images/id/{image.id}",
            hx_boost="true",
            hx_target="#main",
        ),
        P(Strong(image.name)) if show_name else None,
        footer if footer else None,
    )
