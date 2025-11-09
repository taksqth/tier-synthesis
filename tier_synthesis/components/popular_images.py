from fasthtml.common import *  # type: ignore
from routers.tierlist_router import TIER_TO_RATING, tierlist_to_ratings
from components.image_grid import ImageGrid
import os

db = database(os.environ.get("DB_PATH", "app/database.db"))


def PopularImages(category: str, images_map: dict, limit: int = 8) -> Any:
    """Render most and least popular images in a category"""
    popular, unpopular = _get_popular_images(category, limit)

    if not popular and not unpopular:
        return None

    results = []

    if popular:
        results.append(
            ImageGrid(
                title="⭐ Crowd Favorites",
                description="What everyone loves",
                images=popular,
                render_card=lambda p: _PopularityCard(p, images_map, is_popular=True),
                single_row=True,
            )
        )

    if unpopular:
        results.append(
            ImageGrid(
                title="💩 The Unwanted",
                description="What everyone dislikes",
                images=unpopular,
                render_card=lambda u: _PopularityCard(u, images_map, is_popular=False),
                single_row=True,
            )
        )

    return results if results else None


def _PopularityCard(item: dict, images_map: dict, is_popular: bool) -> Any:
    """Render a single popularity card"""
    from components.image_card import ImageCard

    image = images_map.get(item["image_id"])
    if not image:
        return None

    footer = Div(
        Div(
            Small(
                f"Avg: {[k for k, v in TIER_TO_RATING.items() if v == round(item['avg_rating'])][0]} ({item['avg_rating']:.1f})"
            ),
            Small(f"{item['rating_count']} ratings"),
        ),
        Small("Community Favorite" if is_popular else "Underrated Pick"),
    )

    return ImageCard(image, footer=footer)


def _get_popular_images(
    category: str, limit: int = 10
) -> tuple[list[dict], list[dict]]:
    """Get most and least popular images by average rating"""
    tierlists = db.q(
        "SELECT id, owner_id, data FROM db_tierlist WHERE category = ?", [category]
    )

    if not tierlists:
        return [], []

    image_ratings = {}

    for tl in tierlists:
        ratings = tierlist_to_ratings(tl["data"])
        for img_id, rating in ratings.items():
            if img_id not in image_ratings:
                image_ratings[img_id] = []
            image_ratings[img_id].append(rating)

    image_averages = []
    for img_id, ratings in image_ratings.items():
        if len(ratings) >= 2:
            avg_rating = sum(ratings) / len(ratings)
            image_averages.append(
                {
                    "image_id": img_id,
                    "avg_rating": avg_rating,
                    "rating_count": len(ratings),
                }
            )

    sorted_images = sorted(image_averages, key=lambda x: x["avg_rating"], reverse=True)

    popular = sorted_images[:limit]
    unpopular = sorted_images[-limit:][::-1]

    return popular, unpopular
