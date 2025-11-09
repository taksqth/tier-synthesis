from fasthtml.common import *  # type: ignore
from .base_layout import get_full_layout, tag
from .images_router import DBImage, get_category_images, get_accessible_images
from .tierlist_router import tierlist_to_ratings, get_category_tierlists
from .users_router import get_user_avatar, get_anonymous_avatar, get_shared_group_users
from services.storage import get_storage_service
from components.hot_takes import HotTakes
from components.popular_images import PopularImages
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_AVATAR = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48'%3E%3Crect width='48' height='48' fill='%23ccc'/%3E%3C/svg%3E"


# ============================================================================
# DATABASE SETUP
# ============================================================================

db = database(os.environ.get("DB_PATH", "app/database.db"))


# ============================================================================
# ROUTER SETUP
# ============================================================================

ar_latent = APIRouter(prefix="/insights")
ar_latent.name = "Taste Insights"  # type: ignore
ar_latent.show = True  # type: ignore


# ============================================================================
# DATA TRANSFORMATION
# ============================================================================


def build_ratings_matrix(
    category: str, user_id: str, is_admin: bool
) -> Tuple[np.ndarray | None, list[tuple[str, str, bool]] | None, list[DBImage] | None]:
    category_images = get_category_images(category, user_id, is_admin)
    if not category_images:
        return None, None, None

    category_tierlists = get_category_tierlists(category, user_id, is_admin)
    if not category_tierlists:
        return None, None, None

    image_ids = [img.id for img in category_images]
    image_id_to_idx = {img_id: idx for idx, img_id in enumerate(image_ids)}

    shared_users = get_shared_group_users(user_id)
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
            shares_group = (
                tierlist.owner_id in shared_users or tierlist.owner_id == user_id
            )
            tierlist_labels.append((tierlist.owner_id, tierlist.name, shares_group))
            ratings_list.append(rating_vector)

    if len(ratings_list) < 2:
        return None, None, None

    ratings_matrix = np.array(ratings_list)
    return ratings_matrix, tierlist_labels, category_images


# ============================================================================
# ANALYSIS
# ============================================================================


def perform_nmf(ratings_matrix, n_components=3):
    from sklearn.decomposition import NMF

    n_users, n_images = ratings_matrix.shape
    n_components = min(n_components, n_users, n_images)

    model = NMF(n_components=n_components, random_state=42, max_iter=500)  # type: ignore
    W = model.fit_transform(ratings_matrix)
    H = model.components_

    return W, H.T, model


def calculate_similarities(W_normalized):
    from sklearn.metrics.pairwise import cosine_similarity

    return (
        cosine_similarity(W_normalized)
        if W_normalized.shape[0] > 1
        else np.array([[1.0]])
    )


def get_top_images_per_theme(H, images, n_components, top_n=8):
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


def get_display_label(owner_id, tierlist_name, share_group):
    if share_group:
        username, _ = get_user_avatar(owner_id)
        return f"{username} - {tierlist_name}"
    return f"Anonymous - {tierlist_name}"


# ============================================================================
# RENDERING COMPONENTS
# ============================================================================


def TasteProfileCard(
    preferences, label, avatar_url, n_components, owner_id=None, make_clickable=False
):
    if make_clickable and owner_id:
        user_display = Header(
            A(
                Img(src=avatar_url or DEFAULT_AVATAR, alt="avatar", cls="avatar"),
                H3(label),
                href=f"/profiles/user/{owner_id}",
                hx_boost="true",
                hx_target="#main",
            ),
            cls="profile-header",
        )
    else:
        user_display = Header(
            Img(src=avatar_url or DEFAULT_AVATAR, alt="avatar", cls="avatar"),
            H3(label),
            cls="profile-header",
        )

    return Card(
        user_display,
        *[
            Div(
                A(
                    P(f"Theme {i + 1}: {int(preferences[i] * 100)}%"),
                    href=f"#theme-{i}",
                ),
                Progress(value=max(preferences[i], 0.01), max=1)
                if preferences[i] > 0
                else Div(cls="static-progress"),
            )
            for i in range(n_components)
        ],
    )


def ImageLatentCard(image, latent_scores, n_components, user_id):
    from .users_router import get_user_avatar
    from components.image_card import ImageCard

    username, avatar_url = get_user_avatar(image.owner_id)

    metadata = Div(
        Img(src=avatar_url, alt="avatar", cls="avatar small"),
        Small(username),
        cls="user-info",
    )

    footer = Div(
        tag("Owned" if image.owner_id == user_id else "Shared"),
        Div(
            *[
                Div(
                    Small(f"Theme {i + 1}: {int(latent_scores[i] * 100)}%"),
                    Progress(value=max(latent_scores[i], 0.01), max=1)
                    if latent_scores[i] > 0
                    else Div(cls="static-progress"),
                )
                for i in range(n_components)
            ],
            cls="mt-2",
        ),
    )

    # Wrap ImageCard in Card to maintain same styling
    return Card(ImageCard(image, metadata=metadata, footer=footer, show_name=True))


def ThemeImages(top_images_per_theme, n_components, category):
    from components.image_grid import ImageGrid

    storage = get_storage_service()

    def render_simple_image(item):
        img, _ = item
        return Img(
            src=storage.generate_signed_url(img.thumbnail_path),
            alt=img.name,
        )

    return [
        Div(
            ImageGrid(
                title=f"Theme {i + 1}",
                description="Top representatives:",
                images=top_images_per_theme[i],
                action_button=A(
                    "View full gallery →",
                    href=f"{ar_latent.prefix}/gallery?category={category}&theme={i}",
                    hx_boost="true",
                    hx_target="#main",
                    role="button",
                    cls="secondary outline",
                ),
                render_card=render_simple_image,
                single_row=True,
            ),
            id=f"theme-{i}",
        )
        for i in range(n_components)
    ]


def get_avatar_for_profile(owner_id, share_group):
    if share_group:
        _, avatar_url = get_user_avatar(owner_id)
        return avatar_url
    return get_anonymous_avatar()[1]


def YourProfilesSection(
    current_user_indices,
    W_normalized,
    tierlist_labels,
    n_components,
    similar_tierlists,
):
    if not current_user_indices:
        return None

    total = len(current_user_indices)
    shown_indices = current_user_indices[:5]

    your_profiles = [
        TasteProfileCard(
            W_normalized[i],
            get_display_label(*tierlist_labels[i]),
            get_avatar_for_profile(tierlist_labels[i][0], tierlist_labels[i][2]),
            n_components,
            owner_id=tierlist_labels[i][0],
            make_clickable=tierlist_labels[i][2],
        )
        for i in shown_indices
    ]

    title = (
        f"Your Taste Profile ({len(shown_indices)} of {total})"
        if total > 5
        else "Your Taste Profile"
    )

    return Div(
        H2(title),
        Grid(*your_profiles, cls="flex-wrap"),
        H3("Similar Tastes"),
        Ul(*[Li(f"{label} ({sim}% similar)") for label, sim in similar_tierlists[:3]])
        if similar_tierlists
        else P("No other tierlists to compare with."),
    )


def AllProfilesSection(W_normalized, tierlist_labels, n_components):
    return Article(
        Details(
            Summary(Header(H2("Everyone's Taste Profiles"))),
            Grid(
                *[
                    TasteProfileCard(
                        W_normalized[i],
                        get_display_label(*tierlist_labels[i]),
                        get_avatar_for_profile(
                            tierlist_labels[i][0], tierlist_labels[i][2]
                        ),
                        n_components,
                        owner_id=tierlist_labels[i][0],
                        make_clickable=tierlist_labels[i][2],
                    )
                    for i in range(len(tierlist_labels))
                ],
                cls="flex-wrap",
            ),
        )
    )


def InsufficientDataPage(category, htmx, is_admin):
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


# ============================================================================
# FEATURE: INSIGHTS ANALYSIS
# ============================================================================


@ar_latent.get("/list", name="View Insights")
def select_category(htmx, request, session):
    from .tierlist_router import get_accessible_tierlists
    from .category_utils import get_all_categories

    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)
    accessible_tierlists = get_accessible_tierlists(user_id, is_admin, fetch_all=True)
    categories = get_all_categories()

    if is_admin:
        img_counts = {
            row["category"]: row["count"]
            for row in db.q(
                "SELECT category, COUNT(*) as count FROM db_image WHERE category IS NOT NULL GROUP BY category"
            )
        }
    else:
        img_counts = {
            row["category"]: row["count"]
            for row in db.q(
                """
            SELECT i.category, COUNT(DISTINCT i.id) as count
            FROM db_image i
            LEFT JOIN image_share s ON i.id = s.image_id
            LEFT JOIN user_group_membership m ON s.user_group_id = m.group_id
            WHERE (i.owner_id = ? OR m.user_id = ?) AND i.category IS NOT NULL
            GROUP BY i.category
            """,
                [user_id, user_id],
            )
        }

    category_cards = []
    for cat in categories:
        cat_tierlists = [tl for tl in accessible_tierlists if tl.category == cat]
        img_count = img_counts.get(cat, 0)
        tierlist_count = len(cat_tierlists)
        people_count = len(set(tl.owner_id for tl in cat_tierlists))

        category_cards.append(
            Card(
                A(
                    Div(
                        H3(cat),
                        Small(
                            f"{img_count} images · {tierlist_count} tierlists · {people_count} contributors"
                        ),
                    ),
                    href=f"{ar_latent.prefix}/analyze?category={cat}",
                    hx_boost="true",
                    hx_target="#main",
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
    if ratings_matrix is None or tierlist_labels is None or images is None:
        return InsufficientDataPage(category, htmx, is_admin)

    n_components = min(3, ratings_matrix.shape[0], ratings_matrix.shape[1])
    W, H, _ = perform_nmf(ratings_matrix, n_components)
    W_normalized = W / W.sum(axis=1, keepdims=True)

    display_labels = [get_display_label(*label) for label in tierlist_labels]
    similarities = calculate_similarities(W_normalized)

    current_user_indices = [
        i for i, (owner_id, _, _) in enumerate(tierlist_labels) if owner_id == user_id
    ]
    similar_tierlists = find_similar_tierlists(
        current_user_indices, similarities, display_labels
    )
    top_images_per_theme = get_top_images_per_theme(H, images, n_components)

    images_map = {img.id: img for img in get_accessible_images(user_id, is_admin)}
    popular_images = PopularImages(category, images_map, limit=8)

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
        YourProfilesSection(
            current_user_indices,
            W_normalized,
            tierlist_labels,
            n_components,
            similar_tierlists,
        ),
        AllProfilesSection(W_normalized, tierlist_labels, n_components),
        HotTakes(user_id, category, images_map, limit=8),
        *(popular_images if popular_images else []),
        Article(
            Details(
                Summary(Header(H2("The Themes"))),
                P("These are the underlying styles that explain different preferences:"),
                *ThemeImages(top_images_per_theme, n_components, category),
            )
        ),
    )

    return get_full_layout(content, htmx, is_admin)


@ar_latent.get("/gallery")
def image_latent_gallery(category: str, theme: int, htmx, request, session):
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    ratings_matrix, _, images = build_ratings_matrix(category, user_id, is_admin)
    if ratings_matrix is None or images is None:
        return InsufficientDataPage(category, htmx, is_admin)

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

    _, H, _ = perform_nmf(ratings_matrix, n_components)
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
        Grid(
            *[
                ImageLatentCard(
                    img, H_normalized[image_index[id(img)]], n_components, user_id
                )
                for img, _ in sorted_images
            ],
            cls="flex-wrap",
        ),
    )

    return get_full_layout(content, htmx, is_admin)


# ============================================================================
# EXPORT
# ============================================================================

latent_router = ar_latent
