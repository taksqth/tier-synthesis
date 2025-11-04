from fasthtml.common import *
from .base_layout import get_full_layout, tag
from .images_router import get_accessible_images
from .users_router import get_user_avatar, get_anonymous_avatar
import numpy as np
import os
import json
import logging

logger = logging.getLogger(__name__)

db = database(os.environ.get("DB_PATH", "app/database.db"))

ar_latent = APIRouter(prefix="/insights")
ar_latent.name = "Taste Insights"
ar_latent.show = True

TIER_TO_RATING = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
DEFAULT_AVATAR = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48'%3E%3Crect width='48' height='48' fill='%23ccc'/%3E%3C/svg%3E"


def tierlist_to_ratings(tierlist_data):
    """Convert tierlist JSON data to a ratings dictionary."""
    data = json.loads(tierlist_data)
    ratings = {}
    for tier, image_ids in data.items():
        rating = TIER_TO_RATING.get(tier, 0)
        for image_id in image_ids:
            ratings[int(image_id)] = rating
    return ratings


def build_ratings_matrix(category, user_id, is_admin):
    from .tierlist_router import get_accessible_tierlists
    from .users_router import users_share_group

    accessible_images = get_accessible_images(user_id, is_admin)
    category_images = [img for img in accessible_images if img.category == category]

    if not category_images:
        return None, None, None

    image_ids = [img.id for img in category_images]
    image_id_to_idx = {img_id: idx for idx, img_id in enumerate(image_ids)}

    tierlists = get_accessible_tierlists(user_id, is_admin, fetch_all=True)
    category_tierlists = [tl for tl in tierlists if tl.category == category]

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
            tierlist_labels.append(
                (
                    tierlist.owner_id,
                    tierlist.name,
                    users_share_group(user_id, tierlist.owner_id),
                )
            )
            ratings_list.append(rating_vector)

    if len(ratings_list) < 2:
        return None, None, None

    ratings_matrix = np.array(ratings_list)
    return ratings_matrix, tierlist_labels, category_images


def perform_nmf(ratings_matrix, n_components=3):
    """Perform Non-negative Matrix Factorization on ratings matrix."""
    from sklearn.decomposition import NMF

    n_users, n_images = ratings_matrix.shape
    n_components = min(n_components, n_users, n_images)

    model = NMF(n_components=n_components, random_state=42, max_iter=500)
    W = model.fit_transform(ratings_matrix)
    H = model.components_

    return W, H.T, model


def get_user_avatars_map(owner_ids):
    return {owner_id: get_user_avatar(owner_id)[1] for owner_id in set(owner_ids)}


def get_display_labels(tierlist_labels, user_map):
    return [
        f"{user_map.get(owner_id, owner_id) if share_group else 'Anonymous'} - {tierlist_name}"
        for owner_id, tierlist_name, share_group in tierlist_labels
    ]


def calculate_similarities(W_normalized):
    from sklearn.metrics.pairwise import cosine_similarity

    return (
        cosine_similarity(W_normalized)
        if W_normalized.shape[0] > 1
        else np.array([[1.0]])
    )


def get_top_images_per_theme(H, images, n_components, top_n=5):
    return [
        [
            (images[idx], H[idx, theme_idx])
            for idx in np.argsort(H[:, theme_idx])[-top_n:][::-1]
        ]
        for theme_idx in range(n_components)
    ]


def find_similar_tierlists(current_user_indices, similarities, display_labels, top_n=3):
    return [
        (display_labels[sim_idx], int(similarities[user_idx, sim_idx] * 100))
        for user_idx in current_user_indices
        for sim_idx in np.argsort(similarities[user_idx])[::-1][1 : top_n + 1]
        if sim_idx != user_idx
    ]


def render_taste_profile_card(preferences, label, avatar_url, n_components):
    return Card(
        Div(
            Img(src=avatar_url or DEFAULT_AVATAR, alt="avatar", cls="avatar"),
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


def render_image_latent_card(image, latent_scores, n_components, user_id):
    import base64
    from .base_layout import tag
    from .users_router import get_user_avatar

    username, avatar_url = get_user_avatar(image.owner_id)
    thumbnail_data = image.thumbnail_data or image.image_data

    return Card(
        Div(
            Img(
                src=avatar_url,
                alt="avatar",
                cls="avatar",
                style="width: 24px; height: 24px; border-radius: 50%; vertical-align: middle;",
            ),
            Small(username, style="margin-left: 0.5em;"),
            style="display: flex; align-items: center; margin-bottom: 0.5em;",
        ),
        A(
            Img(
                src=f"data:{image.content_type};base64,{base64.b64encode(thumbnail_data).decode()}",
                alt=image.name,
                style="width: 100%; cursor: pointer;",
            ),
            href=f"/images/id/{image.id}",
            hx_boost="true",
            hx_target="#main",
        ),
        P(image.name, style="margin: 0.5em 0;"),
        tag("Owned" if image.owner_id == user_id else "Shared"),
        Div(
            *[
                Div(
                    Small(f"Theme {i + 1}: {int(latent_scores[i] * 100)}%"),
                    Progress(value=max(latent_scores[i], 0.01), max=1)
                    if latent_scores[i] > 0
                    else Div(cls="static-progress"),
                    style="margin-top: 0.3em;",
                )
                for i in range(n_components)
            ],
            style="margin-top: 0.5em; font-size: 0.9em;",
        ),
    )


def render_theme_images(top_images_per_theme, n_components, category):
    import base64

    return [
        Article(
            H3(f"Theme {i + 1}"),
            P("Top representatives:"),
            Div(
                *[
                    Img(
                        src=f"data:{img.content_type};base64,{base64.b64encode(img.thumbnail_data or img.image_data).decode()}",
                        alt=img.name,
                        cls="theme-thumbnail",
                    )
                    for img, _ in top_images_per_theme[i]
                ],
                cls="theme-grid",
            ),
            A(
                "View full gallery →",
                href=f"{ar_latent.prefix}/gallery?category={category}&theme={i}",
                hx_boost="true",
                hx_target="#main",
                role="button",
                cls="secondary outline",
                style="margin-top: 1rem;",
            ),
        )
        for i in range(n_components)
    ]


def _get_avatar_for_profile(tierlist_label, user_avatars):
    owner_id, _, share_group = tierlist_label
    return user_avatars.get(owner_id) if share_group else get_anonymous_avatar()[1]


def render_your_profiles_section(
    current_user_indices,
    W_normalized,
    display_labels,
    tierlist_labels,
    user_avatars,
    n_components,
    similar_tierlists,
):
    if not current_user_indices:
        return None

    your_profiles = [
        render_taste_profile_card(
            W_normalized[i],
            display_labels[i],
            _get_avatar_for_profile(tierlist_labels[i], user_avatars),
            n_components,
        )
        for i in current_user_indices
    ]

    return Div(
        H2("Your Taste Profile"),
        Div(*your_profiles, cls="grid"),
        H3("Similar Tastes"),
        Ul(*[Li(f"{label} ({sim}% similar)") for label, sim in similar_tierlists[:3]])
        if similar_tierlists
        else P("No other tierlists to compare with."),
    )


def render_all_profiles_section(
    W_normalized, display_labels, tierlist_labels, user_avatars, n_components
):
    return Details(
        Summary("Everyone's Taste Profiles"),
        Div(
            *[
                render_taste_profile_card(
                    W_normalized[i],
                    display_labels[i],
                    _get_avatar_for_profile(tierlist_labels[i], user_avatars),
                    n_components,
                )
                for i in range(len(display_labels))
            ],
            cls="grid",
            style="grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));",
        ),
    )


def render_insufficient_data_page(category, htmx, is_admin):
    return get_full_layout(
        Div(
            H1(f"Taste Insights: {category}"),
            P(
                "Not enough data to perform analysis. Need at least 2 tierlists with ratings in this category."
            ),
            A(
                "Back to category selection",
                href=f"{ar_latent.prefix}/list",
                hx_boost="true",
                hx_target="#main",
                role="button",
            ),
        ),
        htmx,
        is_admin,
    )


def get_category_stats(category, user_id, is_admin):
    """Get statistics for a category (image count, tierlist count, contributor count)."""
    from .tierlist_router import get_accessible_tierlists

    accessible_images = get_accessible_images(user_id, is_admin)
    image_count = len([img for img in accessible_images if img.category == category])

    tierlists = get_accessible_tierlists(user_id, is_admin, fetch_all=True)
    category_tierlists = [tl for tl in tierlists if tl.category == category]
    tierlist_count = len(category_tierlists)

    contributor_count = len(set(tl.owner_id for tl in category_tierlists))

    return image_count, tierlist_count, contributor_count


@ar_latent.get("/list", name="View Insights")
def select_category(htmx, request, session):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)
    accessible_images = get_accessible_images(user_id, is_admin)
    categories = sorted(set(img.category for img in accessible_images if img.category))

    category_cards = []
    for cat in categories:
        img_count, tierlist_count, people_count = get_category_stats(
            cat, user_id, is_admin
        )
        category_cards.append(
            Article(
                A(
                    Div(
                        H3(cat),
                        P(
                            f"{img_count} images · {tierlist_count} tierlists · {people_count} contributors",
                            style="color: var(--muted-color); font-size: 0.9em;",
                        ),
                    ),
                    href=f"{ar_latent.prefix}/analyze?category={cat}",
                    hx_boost="true",
                    hx_target="#main",
                    style="text-decoration: none;",
                )
            )
        )

    content = Div(
        H1("Taste Insights"),
        P(
            "Select a category to discover taste themes and see how preferences compare."
        ),
        *category_cards
        if category_cards
        else [P("No categories available for analysis.")],
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
        return render_insufficient_data_page(category, htmx, is_admin)

    n_components = min(3, ratings_matrix.shape[0], ratings_matrix.shape[1])
    W, H, _ = perform_nmf(ratings_matrix, n_components)
    W_normalized = W / W.sum(axis=1, keepdims=True)

    owner_ids = [label[0] for label in tierlist_labels]
    unique_owner_ids = list(set(owner_ids))
    users_db = db.q(
        f"SELECT id, username FROM user WHERE id IN ({','.join(['?'] * len(unique_owner_ids))})",
        unique_owner_ids,
    )
    user_map = {u["id"]: u["username"] for u in users_db}

    display_labels = get_display_labels(tierlist_labels, user_map)
    user_avatars = get_user_avatars_map(owner_ids)
    similarities = calculate_similarities(W_normalized)

    current_user_indices = [
        i for i, (owner_id, _, _) in enumerate(tierlist_labels) if owner_id == user_id
    ]
    similar_tierlists = find_similar_tierlists(
        current_user_indices, similarities, display_labels
    )
    top_images_per_theme = get_top_images_per_theme(H, images, n_components)

    your_profiles_section = render_your_profiles_section(
        current_user_indices,
        W_normalized,
        display_labels,
        tierlist_labels,
        user_avatars,
        n_components,
        similar_tierlists,
    )
    all_profiles_section = render_all_profiles_section(
        W_normalized, display_labels, tierlist_labels, user_avatars, n_components
    )
    theme_articles = render_theme_images(top_images_per_theme, n_components, category)

    content = Div(
        Header(
            H1(f"Taste Insights: {category}"),
            A(
                "Back",
                href=f"{ar_latent.prefix}/list",
                hx_boost="true",
                hx_target="#main",
                cls="secondary",
                role="button",
            ),
            cls="flex-row",
        ),
        P(
            f"Analyzed {len(tierlist_labels)} tierlists with {len(images)} images across {n_components} themes."
        ),
        your_profiles_section,
        H2("The Themes"),
        P("These are the underlying styles that explain different preferences:"),
        *theme_articles,
        all_profiles_section,
    )

    return get_full_layout(content, htmx, is_admin)


@ar_latent.get("/gallery")
def image_latent_gallery(category: str, theme: int, htmx, request, session):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    ratings_matrix, tierlist_labels, images = build_ratings_matrix(
        category, user_id, is_admin
    )
    if ratings_matrix is None:
        return render_insufficient_data_page(category, htmx, is_admin)

    n_components = min(3, ratings_matrix.shape[0], ratings_matrix.shape[1])
    if theme < 0 or theme >= n_components:
        return get_full_layout(
            Div(
                H1("Invalid Theme"),
                P(f"Theme must be between 0 and {n_components - 1}."),
                A(
                    "Back to insights",
                    href=f"{ar_latent.prefix}/analyze?category={category}",
                    hx_boost="true",
                    hx_target="#main",
                    role="button",
                ),
            ),
            htmx,
            is_admin,
        )

    W, H, _ = perform_nmf(ratings_matrix, n_components)
    H_normalized = H / H.max(axis=0, keepdims=True)

    image_index = {id(img): i for i, img in enumerate(images)}
    sorted_images = sorted(
        [(img, H_normalized[i, theme]) for i, img in enumerate(images)],
        key=lambda x: x[1],
        reverse=True,
    )

    content = Div(
        Header(
            H1(f"Theme {theme + 1} Gallery: {category}"),
            A(
                "Back to insights",
                href=f"{ar_latent.prefix}/analyze?category={category}",
                hx_boost="true",
                hx_target="#main",
                cls="secondary",
                role="button",
            ),
            cls="flex-row",
        ),
        P(f"Images sorted by Theme {theme + 1} strength ({len(sorted_images)} total)"),
        Div(
            *[
                render_image_latent_card(
                    img, H_normalized[image_index[id(img)]], n_components, user_id
                )
                for img, _ in sorted_images
            ],
            cls="grid",
            style="grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));",
        ),
    )

    return get_full_layout(content, htmx, is_admin)


latent_router = ar_latent
