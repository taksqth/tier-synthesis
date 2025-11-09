from fasthtml.common import *  # type: ignore
from .base_layout import get_full_layout, tag
from .users_router import get_user_avatar, users_share_group
from .tierlist_router import (
    TIER_TO_RATING,
    tierlist_to_ratings,
    get_accessible_tierlists,
    enrich_tierlists_with_ratings,
)
from .images_router import get_accessible_images
from components.hot_takes import DivergentImage, _calculate_divergence
import os
import json
import logging
from collections import Counter

logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE SETUP
# ============================================================================

db = database(os.environ.get("DB_PATH", "app/database.db"))


# ============================================================================
# ROUTER SETUP
# ============================================================================

ar_profile = APIRouter(prefix="/profiles")
ar_profile.name = "Profiles"  # type: ignore
ar_profile.show = True  # type: ignore


# ============================================================================
# DATA ACCESS LAYER
# ============================================================================


def get_user_stats(user_id: str) -> dict:
    """Calculate basic statistics for a user."""

    tierlist_count = db.q(
        "SELECT COUNT(*) as count FROM db_tierlist WHERE owner_id = ?", [user_id]
    )[0]["count"]

    tierlists = db.q("SELECT data FROM db_tierlist WHERE owner_id = ?", [user_id])
    unique_images = set()
    for tl in tierlists:
        data = json.loads(tl["data"]) if isinstance(tl["data"], str) else tl["data"]
        for _, img_list in data.items():
            unique_images.update(img_list)
    rated_images = len(unique_images)

    all_ratings = []
    tierlists = db.q("SELECT data FROM db_tierlist WHERE owner_id = ?", [user_id])
    for tl in tierlists:
        ratings = tierlist_to_ratings(tl["data"])
        all_ratings.extend(ratings.values())

    ratings_received = db.q(
        """
        SELECT COUNT(*) as count
        FROM tierlist_rating tr
        JOIN db_tierlist tl ON tr.tierlist_id = tl.id
        WHERE tl.owner_id = ?
        """,
        [user_id],
    )[0]["count"]

    comments_received = db.q(
        """
        SELECT COUNT(*) as count
        FROM tierlist_comment tc
        JOIN db_tierlist tl ON tc.tierlist_id = tl.id
        WHERE tl.owner_id = ?
        """,
        [user_id],
    )[0]["count"]

    return {
        "tierlist_count": tierlist_count,
        "rated_images": rated_images,
        "ratings_received": ratings_received,
        "comments_received": comments_received,
    }


# ============================================================================
# DATA ANALYSIS FUNCTIONS
# ============================================================================


def find_contrarian_opinions(user_id: str) -> list[dict]:
    """Find opinions where user differs most from the crowd across all categories."""
    categories = db.q(
        "SELECT DISTINCT category FROM db_tierlist WHERE category IS NOT NULL"
    )

    all_divergences = []
    for cat_row in categories:
        category = cat_row["category"]
        divergences = _calculate_divergence(user_id, category)
        for div in divergences[:3]:  # Top 3 per category
            div["category"] = category
            all_divergences.append(div)

    return sorted(all_divergences, key=lambda x: x["divergence"], reverse=True)[:8]


def get_taste_profile_summary(user_id: str) -> dict:
    """Get aggregated taste profile across all categories."""
    categories = db.q(
        "SELECT DISTINCT category FROM db_tierlist WHERE owner_id = ? AND category IS NOT NULL",
        [user_id],
    )

    category_profiles = []
    for cat_row in categories:
        category = cat_row["category"]
        tierlists = db.q(
            "SELECT id, name, data FROM db_tierlist WHERE owner_id = ? AND category = ?",
            [user_id, category],
        )

        if tierlists:
            category_profiles.append(
                {"category": category, "tierlist_count": len(tierlists)}
            )

    return {"categories": category_profiles}


# ============================================================================
# RENDERING FUNCTIONS
# ============================================================================


def StatCard(title: str, value: str, subtitle: str = "") -> Any:
    """Render a single stat card."""
    return Article(
        H3(value),
        P(Strong(title)),
        (Small(subtitle) if subtitle else None),
        align="center",
    )


def RecentTierlists(tierlists: list) -> Any:
    """Render recent tierlists section."""
    if not tierlists:
        return P("No tierlists yet.")

    return Div(
        *[
            Article(
                A(
                    Div(
                        Strong(tl.name),
                        Br(),
                        Small(f"{tl.category} • {tl.created_at[:10]}"),
                        tag(f"❤️ {tl.love_count}"),  # type: ignore
                        tag(f"👎 {tl.tomato_count}"),  # type: ignore
                    ),
                    href=f"/tierlist/id/{tl.id}",
                    hx_boost="true",
                    hx_target="#main",
                ),
            )
            for tl in tierlists[:5]
        ]
    )


def CategoryInsights(category_profiles: list) -> Any:
    """Render taste insights by category."""
    if not category_profiles:
        return P("Create tierlists to see your taste profile!")

    return Grid(
        *[
            Article(
                A(
                    Div(
                        H4(prof["category"]),
                        Small(f"{prof['tierlist_count']} tierlists"),
                    ),
                    href=f"/insights/analyze?category={prof['category']}",
                    hx_boost="true",
                    hx_target="#main",
                ),
            )
            for prof in category_profiles
        ],
    )


# ============================================================================
# ROUTES
# ============================================================================


@ar_profile.get("/me", name="My Profile")
def get_my_profile(htmx, request, session) -> Any:
    """Show current user's profile."""
    user_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    if not user_id:
        return get_full_layout(
            Div(
                H1("Not Logged In"),
                P("Please log in to view your profile."),
            ),
            htmx,
            is_admin,
        )

    return ProfilePage(user_id, user_id, is_admin, htmx, is_own_profile=True)


@ar_profile.get("/user/{profile_user_id}")
def get_user_profile(profile_user_id: str, htmx, request, session) -> Any:
    """Show another user's profile (if they share a group)."""
    viewer_id = session.get("user_id")
    is_admin = request.scope.get("is_admin", False)

    if not is_admin and viewer_id != profile_user_id:
        if not users_share_group(viewer_id, profile_user_id):
            return get_full_layout(
                Div(
                    H1("Access Denied"),
                    P("You can only view profiles of users in your groups."),
                ),
                htmx,
                is_admin,
            )

    return ProfilePage(profile_user_id, viewer_id, is_admin, htmx, is_own_profile=False)


def ProfilePage(
    profile_user_id: str,
    viewer_id: str,
    is_admin: bool,
    htmx,
    is_own_profile: bool = False,
) -> Any:
    """Render the complete profile page."""
    username, avatar_url = get_user_avatar(profile_user_id)

    stats = get_user_stats(profile_user_id)

    tierlists = get_accessible_tierlists(profile_user_id, is_admin)
    user_tierlists = [tl for tl in tierlists if tl.owner_id == profile_user_id]
    enrich_tierlists_with_ratings(user_tierlists[:5], viewer_id)

    contrarian = find_contrarian_opinions(profile_user_id)

    all_images = get_accessible_images(viewer_id, is_admin)
    images_map = {img.id: img for img in all_images}

    taste_summary = get_taste_profile_summary(profile_user_id)

    tier_distribution = Counter()
    for tl in user_tierlists:
        ratings = tierlist_to_ratings(tl.data)
        for rating in ratings.values():
            tier_name = [k for k, v in TIER_TO_RATING.items() if v == rating][0]
            tier_distribution[tier_name] += 1

    content = Div(
        Header(
            H1(f"{'My' if is_own_profile else username + "'s"} Profile"),
            cls="flex-row",
        ),
        # User info
        Div(
            Img(
                src=avatar_url,
                alt="avatar",
                cls="avatar large",
            ),
            Div(
                H2(username),
                (
                    Small(f"Member since {stats.get('member_since', 'recently')}")
                    if stats.get("member_since")
                    else None
                ),
            ),
            cls="user-info header",
        ),
        # Stats
        H3("Statistics"),
        Grid(
            StatCard("Tierlists Created", str(stats["tierlist_count"])),
            StatCard("Images Ranked", str(stats["rated_images"])),
            StatCard(
                "Community Engagement",
                str(stats["ratings_received"]),
            ),
        ),
        # Tier distribution
        (
            Div(
                H4("Rating Distribution"),
                Div(
                    *[
                        Div(
                            Small(f"{tier}: {tier_distribution[tier]} images"),
                            Progress(
                                value=tier_distribution[tier],
                                max=max(tier_distribution.values())
                                if tier_distribution
                                else 1,
                            ),
                        )
                        for tier in ["S", "A", "B", "C", "D"]
                        if tier_distribution[tier] > 0
                    ],
                ),
                cls="mt-2",
            )
            if tier_distribution
            else None
        ),
        # Contrarian opinions
        (
            Div(
                H3(
                    "🔥 "
                    + ("Your" if is_own_profile else f"{username}'s")
                    + ' "Hot Takes"'
                ),
                P(
                    "Where "
                    + ("you differ" if is_own_profile else "they differ")
                    + " most from the crowd:"
                ),
                Grid(
                    *[
                        DivergentImage(div, images_map)
                        for div in contrarian
                        if DivergentImage(div, images_map) is not None
                    ],
                ),
            )
            if contrarian
            else None
        ),
        # Recent tierlists
        Div(
            H3("Recent Tierlists"),
            RecentTierlists(user_tierlists),
        ),
        # Taste insights by category
        Div(
            H3("Taste Profile by Category"),
            P("Explore detailed taste analysis:"),
            CategoryInsights(taste_summary["categories"]),
        )
        if taste_summary["categories"]
        else None,
    )

    return get_full_layout(content, htmx, is_admin)


# ============================================================================
# EXPORT
# ============================================================================

profile_router = ar_profile
