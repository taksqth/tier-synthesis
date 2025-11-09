from fasthtml.common import database
from dataclasses import dataclass
import os


@dataclass
class Category:
    name: str
    normalized: str


db = database(os.environ.get("DB_PATH", "app/database.db"))
categories = db.create(Category, pk="normalized", transform=True)


def validate_and_get_category(category_name: str):
    if not category_name or not category_name.strip():
        raise ValueError("Category name cannot be empty")

    category_name = category_name.strip()
    normalized = category_name.lower()

    if normalized == "all":
        raise ValueError("'All' is a reserved category name")

    try:
        existing = categories[normalized]
        if existing.name != category_name:
            raise ValueError(
                f"Category already exists as '{existing.name}' (case-sensitive)"
            )
        return existing.name
    except NotFoundError:
        categories.insert(Category(name=category_name, normalized=normalized))
        return category_name


def get_all_categories():
    return [cat.name for cat in categories(order_by="name")]
