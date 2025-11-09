from fasthtml.common import *  # type: ignore
from routers.base_layout import tag
from routers.tierlist_router import TIER_TO_RATING, tierlist_to_ratings
from components.image_grid import ImageGrid
import os

db = database(os.environ.get("DB_PATH", "app/database.db"))


def HotTakes(user_id: str, category: str, images_map: dict, limit: int = 8):
    """Render user's contrarian opinions in a category"""
    divergences = _calculate_divergence(user_id, category, limit)
    if not divergences:
        return None

    return ImageGrid(
        title="🔥 Your Hot Takes",
        description=f"Where you differ most from the crowd in {category}",
        images=divergences,
        render_card=lambda div: DivergentImage(div, images_map),
        single_row=True,
    )


def DivergentImage(div: dict, images_map: dict):
    """Render a single divergent opinion card"""
    from components.image_card import ImageCard

    image = images_map.get(div["image_id"])
    if not image:
        return None

    footer = Div(
        P(
            f"{'⬆️' if div['is_higher'] else '⬇️'} You: ",
            Strong(
                [k for k, v in TIER_TO_RATING.items() if v == div["user_rating"]][0]
            ),
            f" | Everyone: {[k for k, v in TIER_TO_RATING.items() if v == round(div['avg_rating'])][0]}",
        ),
        Small("Higher than average" if div["is_higher"] else "Lower than average"),
    )

    return ImageCard(image, footer=footer)


def _calculate_divergence(user_id: str, category: str, limit: int = 8) -> list[dict]:
    """Calculate opinion divergence for a user in a category"""
    tierlists = db.q(
        "SELECT id, owner_id, data FROM db_tierlist WHERE category = ?", [category]
    )

    if len(tierlists) < 2:
        return []

    image_ratings = {}
    user_ratings = {}

    for tl in tierlists:
        ratings = tierlist_to_ratings(tl["data"])
        owner_id = tl["owner_id"]

        for img_id, rating in ratings.items():
            if img_id not in image_ratings:
                image_ratings[img_id] = []
            image_ratings[img_id].append(rating)

            if owner_id == user_id:
                user_ratings[img_id] = rating

    divergences = []
    for img_id, user_rating in user_ratings.items():
        if img_id in image_ratings and len(image_ratings[img_id]) > 1:
            others_ratings = [r for r in image_ratings[img_id]]
            avg_rating = sum(others_ratings) / len(others_ratings)

            divergence = abs(user_rating - avg_rating)
            is_higher = user_rating > avg_rating

            if divergence > 1.0:
                divergences.append(
                    {
                        "image_id": img_id,
                        "user_rating": user_rating,
                        "avg_rating": avg_rating,
                        "divergence": divergence,
                        "is_higher": is_higher,
                    }
                )

    return sorted(divergences, key=lambda x: x["divergence"], reverse=True)[:limit]
