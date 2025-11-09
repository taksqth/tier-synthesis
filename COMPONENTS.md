# Component Architecture

This document describes the component structure of the tier-synthesis application.

## Philosophy

Components follow FastHTML conventions:
- **PascalCase** naming for all public components
- **snake_case** with `_` prefix for private helpers
- Self-contained: logic + rendering together
- Database access within components is acceptable (fastlite handles connection pooling)

## Shared Utilities

### `services/storage.py`
- `get_storage_service()` - Singleton for file storage with HMAC-signed URLs
- `StorageService.generate_signed_url()` - Generate time-limited signed URLs
- `StorageService.save_image()` - Save images to filesystem
- `StorageService.delete_image()` - Delete images from filesystem

### `routers/tierlist_router.py`
- `TIER_TO_RATING` - Mapping of tier letters to numeric ratings (S=5, A=4, B=3, C=2, D=1)
- `tierlist_to_ratings(tierlist_data)` - Convert tierlist JSON to image ID → rating dict

## Base Components

### `components/image_card.py`
**Purpose**: Reusable image card with flexible metadata and footer sections

```python
ImageCard(image, metadata=None, footer=None, show_name=True)
```

Used by: `DivergentImage`, `_PopularityCard`, `ImageLatentCard`

### `components/image_grid.py`
**Purpose**: Unified grid/row layout for image collections

```python
ImageGrid(title, description="", images=[], action_button=None, render_card=None, single_row=False)
```

**Layout Modes**:
- `single_row=True` - Single row showcase, hides overflow (hot takes, favorites, theme previews)
- `single_row=False` - Gallery grid with wrapping (image gallery, full theme view)

Used by: `HotTakes`, `PopularImages`, `ThemeImages`

### `components/user_display.py`
**Purpose**: User avatar + name display with optional profile link

```python
UserDisplay(owner_id, viewer_id, clickable=True)
```

Used by: `TierlistPage`, `ImageEditPage`

## CSS Layout Classes

### `.image-row`
- Single-row showcase with overflow hidden
- Fixed 150px column width
- Auto-flow columns, no wrapping
- Used by showcase components (hot takes, community favorites, etc.)

### `.flex-wrap`
- Multi-row gallery grid with wrapping
- Responsive columns with `minmax(200px, 1fr)`
- Used by browsable galleries (image gallery, tierlist editor, full theme gallery)

## Analysis Components (`components/`)

### `hot_takes.py`
**Public**:
- `HotTakes(user_id, category, images_map)` - Shows user's contrarian opinions in a category
- `DivergentImage(div, images_map)` - Single divergent opinion card

**Private**:
- `_calculate_divergence(user_id, category)` - Calculate opinion divergence scores

### `popular_images.py`
**Public**:
- `PopularImages(category, images_map, limit=6)` - Shows most/least popular images

**Private**:
- `_PopularityCard(item, images_map, is_popular)` - Single popularity card
- `_get_popular_images(category, limit)` - Get ranked images by average rating

## Profile Components (`routers/profile_router.py`)

- `StatCard(title, value, subtitle="")` - Metric display card
- `RecentTierlists(tierlists)` - List of recent tierlists with links
- `CategoryInsights(category_profiles)` - Grid of category taste profiles
- `ProfilePage(profile_user_id, viewer_id, is_admin, htmx, is_own_profile)` - Complete profile page

## Tierlist Components (`routers/tierlist_router.py`)

- `DraggableImage(image, can_edit)` - Image with drag/drop capability for tier editor
- `TierRow(tier, images, can_edit)` - Single tier row (S/A/B/C/D) with images
- `SaveForm(tierlist, can_edit, user_groups, shared_group_ids)` - Tierlist save form with sharing
- `Comment(comment)` - Single comment display with user info
- `TierlistPage(tierlist, images, can_edit, user_groups, shared_group_ids, viewer_id)` - Complete tierlist editor
- `TierlistList(tierlist_list, user_id, categories, selected_category, mine_only)` - Filtered list of tierlists

## Image Components (`routers/images_router.py`)

- `ImageEditPage(image, can_edit, user_groups, shared_group_ids, categories, viewer_id)` - Image editor page
- `ImageUploadPage(categories, user_groups)` - Image upload form
- `ImageGalleryPage(filtered_images, user_id, categories, selected_category, mine_only)` - Image gallery grid

## Latent Analysis Components (`routers/latent_router.py`)

- `TasteProfileCard(profile, label, avatar_url, n_components, owner_id, make_clickable)` - Taste profile display
- `ImageLatentCard(image, latent_scores, n_components, user_id)` - Image with theme scores
- `ThemeImages(top_images_per_theme, n_components, category)` - Theme-organized image grid
- `YourProfilesSection(W_normalized, tierlist_labels, n_components, current_user_indices, category)` - User's taste profiles
- `AllProfilesSection(W_normalized, tierlist_labels, n_components)` - All community profiles
- `InsufficientDataPage(category, htmx, is_admin)` - Error state for insufficient data

## Component Hierarchy

```
Base Components
├── ImageCard - Reusable image card
└── UserDisplay - User avatar + name

Analysis Components
├── HotTakes
│   └── DivergentImage (uses ImageCard)
└── PopularImages
    └── _PopularityCard (uses ImageCard)

Profile Components
├── StatCard
├── RecentTierlists
├── CategoryInsights
└── ProfilePage (uses all above)

Tierlist Components
├── DraggableImage
├── TierRow (uses DraggableImage)
├── SaveForm
├── Comment
├── TierlistPage (uses TierRow, SaveForm, UserDisplay)
└── TierlistList

Image Components
├── ImageEditPage (uses UserDisplay)
├── ImageUploadPage
└── ImageGalleryPage

Latent Analysis Components
├── TasteProfileCard
├── ImageLatentCard (uses ImageCard)
├── ThemeImages
├── YourProfilesSection (uses TasteProfileCard)
├── AllProfilesSection (uses TasteProfileCard)
└── InsufficientDataPage
```

## Design Patterns

### Component Composition
Components accept other components as parameters (metadata/footer in ImageCard) rather than using inheritance.

### Conditional Rendering
Components return `None` for missing data, allowing parent components to filter with:
```python
*[Component(item) for item in items if Component(item) is not None]
```

### Location Strategy
- **Shared base components** → `components/` directory
- **Domain-specific page components** → stay in respective `routers/` files
- **Reusable across multiple domains** → extract to `components/`

### Database Access
Components can directly access database via `db.q()` - fastlite handles connection pooling, no need for dependency injection.

## Future Consolidation Opportunities

1. **ThemeImages** could potentially use ImageCard base
2. **TasteProfileCard** shares pattern with StatCard - possible unification
3. Consider extracting form components (SaveForm, upload forms) to shared location if pattern repeats
