from fasthtml.common import database
from dataclasses import dataclass
import os
import logging

logger = logging.getLogger(__name__)

@dataclass
class Category:
    name: str
    normalized: str

def run_migrations():
    db = database(os.environ.get("DB_PATH", "app/database.db"))

    logger.info("Running migrations...")
    migrate_categories(db)
    migrate_image_file_paths(db)
    logger.info("Migrations complete")


def migrate_categories(db):
    categories = db.create(Category, pk='normalized', transform=True)

    existing_count = len(categories())
    if existing_count > 0:
        logger.info(f"Categories table already populated with {existing_count} entries, skipping migration")
        return

    logger.info("Migrating categories from existing data...")

    existing_categories = set()
    migrated = 0

    images = db.q("SELECT DISTINCT category FROM db_image WHERE category IS NOT NULL AND category != ''")
    for row in images:
        cat = row['category']
        normalized = cat.lower()
        if normalized not in existing_categories and normalized != 'all':
            existing_categories.add(normalized)
            try:
                categories.insert(Category(name=cat, normalized=normalized))
                migrated += 1
                logger.debug(f"  Created category: {cat}")
            except Exception as e:
                logger.warning(f"  Skipped {cat}: {e}")

    tierlists = db.q("SELECT DISTINCT category FROM db_tierlist WHERE category IS NOT NULL AND category != ''")
    for row in tierlists:
        cat = row['category']
        normalized = cat.lower()
        if normalized not in existing_categories and normalized != 'all':
            existing_categories.add(normalized)
            try:
                categories.insert(Category(name=cat, normalized=normalized))
                migrated += 1
                logger.debug(f"  Created category: {cat}")
            except Exception as e:
                logger.warning(f"  Skipped {cat}: {e}")

    logger.info(f"Category migration complete: {migrated} categories created")


def migrate_image_file_paths(db):
    from services.storage import get_storage_service
    from routers.images_router import process_image, DBImage

    images_table = db.create(
        DBImage,
        pk="id",
        foreign_keys=[("owner_id", "user")],
        transform=True,
    )

    all_images = list(images_table())
    logger.info(f"Found {len(all_images)} total images in database")

    for img in all_images[:3]:
        logger.info(f"Image {img.id}: thumbnail_path='{img.thumbnail_path}', has_image_data={len(img.image_data) if img.image_data else 0} bytes")

    unmigrated = [img for img in all_images if not img.thumbnail_path and img.image_data]

    if not unmigrated:
        logger.info("All images already migrated to filesystem")
        return

    logger.info(f"Migrating {len(unmigrated)} images from database to filesystem...")
    storage = get_storage_service()

    for image in unmigrated:
        try:
            thumbnail_data = image.thumbnail_data if image.thumbnail_data else process_image(image.image_data)

            thumbnail_path = storage.save_image(thumbnail_data, image.id, image.content_type, is_thumbnail=True)
            full_image_path = storage.save_image(image.image_data, image.id, image.content_type, is_thumbnail=False)

            image.thumbnail_path = thumbnail_path
            image.full_image_path = full_image_path
            image.image_data = b""
            image.thumbnail_data = b""

            images_table.update(image)
            logger.info(f"Migrated image {image.id}: {image.name}")
        except Exception as e:
            logger.error(f"Failed to migrate image {image.id}: {e}")

    logger.info("Image file path migration complete")
