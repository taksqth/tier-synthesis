from fasthtml.common import *
from .base_layout import get_full_layout, tag
from .images_router import get_accessible_images
import numpy as np
import os
import json
import logging

logger = logging.getLogger(__name__)

db = database(os.environ.get("DB_PATH", "app/database.db"))

ar_latent = APIRouter(prefix="/insights")
ar_latent.name = "Taste Insights"
ar_latent.show = True


def tierlist_to_ratings(tierlist_data):
    tier_to_rating = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
    data = json.loads(tierlist_data)
    ratings = {}
    for tier, image_ids in data.items():
        rating = tier_to_rating.get(tier, 0)
        for image_id in image_ids:
            ratings[int(image_id)] = rating
    return ratings


def build_ratings_matrix(category, user_id, is_admin):
    from .tierlist_router import get_accessible_tierlists

    accessible_images = get_accessible_images(user_id, is_admin)
    category_images = [img for img in accessible_images if img.category == category]

    if not category_images:
        return None, None, None

    image_ids = [img.id for img in category_images]
    image_id_to_idx = {img_id: idx for idx, img_id in enumerate(image_ids)}

    accessible_tierlists = get_accessible_tierlists(user_id, is_admin)
    category_tierlists = [tl for tl in accessible_tierlists if tl.category == category]

    if not category_tierlists:
        return None, None, None

    tierlist_labels = []
    ratings_list = []

    for tierlist in category_tierlists:
        ratings_dict = tierlist_to_ratings(tierlist.data)
        rating_vector = [0] * len(image_ids)

        has_ratings = False
        for img_id, rating in ratings_dict.items():
            if img_id in image_id_to_idx:
                rating_vector[image_id_to_idx[img_id]] = rating
                has_ratings = True

        if has_ratings:
            tierlist_labels.append((tierlist.owner_id, tierlist.name))
            ratings_list.append(rating_vector)

    if len(ratings_list) < 2:
        return None, None, None

    ratings_matrix = np.array(ratings_list)
    return ratings_matrix, tierlist_labels, category_images


def perform_nmf(ratings_matrix, n_components=3):
    from sklearn.decomposition import NMF

    n_users, n_images = ratings_matrix.shape
    n_components = min(n_components, n_users, n_images)

    model = NMF(n_components=n_components, random_state=42, max_iter=500)
    W = model.fit_transform(ratings_matrix)
    H = model.components_

    return W, H.T, model


@ar_latent.get("/select", name="Taste Insights")
def select_category(htmx, request, session):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)
    accessible_images = get_accessible_images(user_id, is_admin)
    categories = sorted(set(img.category for img in accessible_images if img.category))

    content = Div(
        H1("Taste Insights"),
        P(
            "Select a category to discover taste themes and see how preferences compare."
        ),
        *[
            Article(
                A(
                    cat,
                    hx_get=f"{ar_latent.prefix}/analyze?category={cat}",
                    hx_target="#main",
                    hx_push_url="true",
                )
            )
            for cat in categories
        ]
        if categories
        else P("No categories available for analysis."),
    )

    return get_full_layout(content, htmx, is_admin)


@ar_latent.get("/analyze")
def analyze_category(category: str, htmx, request, session):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    ratings_matrix, tierlist_labels, images = build_ratings_matrix(
        category, user_id, is_admin
    )

    if ratings_matrix is None:
        content = Div(
            H1(f"Taste Insights: {category}"),
            P(
                "Not enough data to perform analysis. Need at least 2 tierlists with ratings in this category."
            ),
            A(
                "Back to category selection",
                hx_get=f"{ar_latent.prefix}/select",
                hx_target="#main",
                hx_push_url="true",
            ),
        )
        return get_full_layout(content, htmx, is_admin)

    n_components = min(3, ratings_matrix.shape[0], ratings_matrix.shape[1])
    W, H, model = perform_nmf(ratings_matrix, n_components)

    owner_ids = [label[0] for label in tierlist_labels]
    users_db = db.q(
        f"SELECT id, username FROM user WHERE id IN ({','.join(['?'] * len(set(owner_ids)))})",
        list(set(owner_ids)),
    )
    user_map = {u["id"]: u["username"] for u in users_db}

    display_labels = [
        f"{user_map.get(owner_id, owner_id)} - {tierlist_name}"
        for owner_id, tierlist_name in tierlist_labels
    ]

    W_normalized = W / W.sum(axis=1, keepdims=True)

    top_images_per_theme = []
    for theme_idx in range(n_components):
        latent_values = H[:, theme_idx]
        top_indices = np.argsort(latent_values)[-5:][::-1]
        top_images_per_theme.append(
            [(images[idx], latent_values[idx]) for idx in top_indices]
        )

    current_user_indices = [
        i for i, (owner_id, _) in enumerate(tierlist_labels) if owner_id == user_id
    ]

    from sklearn.metrics.pairwise import cosine_similarity

    if len(tierlist_labels) > 1:
        similarities = cosine_similarity(W_normalized)
    else:
        similarities = np.array([[1.0]])

    def create_taste_profile(preferences, label, avatar_url=None):
        return Card(
            Div(
                Img(
                    src=avatar_url
                    if avatar_url
                    else "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48'%3E%3Crect width='48' height='48' fill='%23ccc'/%3E%3C/svg%3E",
                    alt="avatar",
                    cls="avatar",
                ),
                H3(label),
                cls="profile-header",
            ),
            *[
                Div(
                    P(f"Theme {i + 1}: {int(preferences[i] * 100)}%"),
                    Progress(value=max(preferences[i], 0.01), max=1)
                    if preferences[i] > 0
                    else Div(cls="static-progress"),
                )
                for i in range(n_components)
            ],
        )

    user_avatars = {}
    for owner_id in set(owner_ids):
        user_data = db.q("SELECT avatar FROM user WHERE id = ?", [owner_id])
        if user_data and user_data[0]["avatar"]:
            avatar_hash = user_data[0]["avatar"]
            user_avatars[owner_id] = (
                f"https://cdn.discordapp.com/avatars/{owner_id}/{avatar_hash}.png?size=128"
            )
        else:
            user_avatars[owner_id] = None

    your_profiles = (
        [
            create_taste_profile(
                W_normalized[i],
                display_labels[i],
                user_avatars.get(tierlist_labels[i][0]),
            )
            for i in current_user_indices
        ]
        if current_user_indices
        else []
    )

    similar_tierlists = []
    if current_user_indices:
        for user_idx in current_user_indices:
            similar_indices = np.argsort(similarities[user_idx])[::-1][1:4]
            for sim_idx in similar_indices:
                if sim_idx != user_idx:
                    similarity_pct = int(similarities[user_idx, sim_idx] * 100)
                    similar_tierlists.append((display_labels[sim_idx], similarity_pct))

    content = Div(
        Header(
            H1(f"Taste Insights: {category}"),
            A(
                "Back",
                hx_get=f"{ar_latent.prefix}/select",
                hx_target="#main",
                hx_push_url="true",
                cls="secondary",
                role="button",
            ),
            cls="flex-row",
        ),
        P(
            f"Analyzed {len(tierlist_labels)} tierlists with {len(images)} images across {n_components} themes."
        ),
        (
            Div(
                H2("Your Taste Profile"),
                Div(*your_profiles, cls="grid"),
                H3("Similar Tastes"),
                Ul(
                    *[
                        Li(f"{label} ({sim}% similar)")
                        for label, sim in similar_tierlists[:3]
                    ]
                )
                if similar_tierlists
                else P("No other tierlists to compare with."),
            )
            if your_profiles
            else None
        ),
        H2("The Themes"),
        P("These are the underlying styles that explain different preferences:"),
        *[
            Article(
                H3(f"Theme {i + 1}"),
                P("Top representatives:"),
                Div(
                    *[
                        Img(
                            src=f"data:{img.content_type};base64,{__import__('base64').b64encode(img.thumbnail_data or img.image_data).decode()}",
                            alt=img.name,
                            cls="theme-thumbnail",
                        )
                        for img, score in top_images_per_theme[i]
                    ],
                    cls="theme-grid",
                ),
            )
            for i in range(n_components)
        ],
        Details(
            Summary("Everyone's Taste Profiles"),
            Div(
                *[
                    create_taste_profile(
                        W_normalized[i],
                        display_labels[i],
                        user_avatars.get(tierlist_labels[i][0]),
                    )
                    for i in range(len(display_labels))
                ],
                cls="grid",
            ),
        ),
    )

    return get_full_layout(content, htmx, is_admin)


latent_router = ar_latent
