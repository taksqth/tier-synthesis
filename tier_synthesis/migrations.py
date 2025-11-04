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
