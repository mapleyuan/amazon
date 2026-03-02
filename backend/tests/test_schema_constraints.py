from __future__ import annotations

import sqlite3
import unittest

from tests.test_helpers import isolated_env


class SchemaConstraintTests(unittest.TestCase):
    def test_product_unique_site_asin_constraint(self) -> None:
        with isolated_env():
            from app.db.connection import get_connection
            from app.db.schema import init_db

            conn = get_connection()
            init_db(conn)

            conn.execute(
                """
                INSERT INTO products (site, asin, title, brand, image_url, detail_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("amazon.com", "B0001", "A", "Brand", "", ""),
            )

            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO products (site, asin, title, brand, image_url, detail_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("amazon.com", "B0001", "B", "Brand", "", ""),
                )


if __name__ == "__main__":
    unittest.main()
