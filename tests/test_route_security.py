import os
import tempfile
import unittest
from io import BytesIO

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import auth, models
from app import main as routes


class DummyUpload:
    def __init__(self, filename: str, content_type: str, data: bytes = b"solid test\nendsolid test\n"):
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(data)


class RouteSecurityTests(unittest.TestCase):
    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.db_file.close()
        self.engine = create_engine(f"sqlite:///{self.db_file.name}")
        self.Session = sessionmaker(bind=self.engine)
        models.Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

        self.user = models.User(email="user@example.com", password="hash", is_admin=False)
        self.other_user = models.User(email="other@example.com", password="hash", is_admin=False)
        self.admin = models.User(email="admin@example.com", password="hash", is_admin=True)
        self.product = models.Product(
            type="base",
            name="Visible Figure",
            quantity=5,
            price=25,
            discounted_price=20,
            is_visible=True,
            status="published",
        )
        self.hidden_product = models.Product(
            type="base",
            name="Hidden Figure",
            quantity=5,
            price=10,
            is_visible=False,
            status="draft",
        )
        self.db.add_all([self.user, self.other_user, self.admin, self.product, self.hidden_product])
        self.db.commit()
        for item in (self.user, self.other_user, self.admin, self.product, self.hidden_product):
            self.db.refresh(item)

        self.hidden_media = models.ProductMedia(
            product_id=self.hidden_product.id,
            kind="image",
            filename="hidden.png",
            content_type="image/png",
            data=b"hidden",
        )
        self.db.add(self.hidden_media)
        self.db.commit()
        self.db.refresh(self.hidden_media)

    def tearDown(self):
        self.db.close()
        models.Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        os.unlink(self.db_file.name)

    def test_admin_required_blocks_non_admins(self):
        with self.assertRaises(HTTPException) as ctx:
            auth.admin_required(self.user)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIs(auth.admin_required(self.admin), self.admin)

    def test_guest_order_ignores_client_prices_and_status(self):
        order = routes.create_guest_order(
            routes.schemas.GuestOrderBase(
                guest_email="buyer@example.com",
                guest_address="Street 1",
                currency="usd",
                products=[
                    {"product_id": self.product.id, "quantity": 2, "unit_price": 0.01},
                ],
            ),
            db=self.db,
        )

        self.assertEqual(order.status, "AWAITING_PAYMENT")
        self.assertEqual(float(order.subtotal), 40.0)
        self.assertEqual(float(order.total_cost), 45.0)
        self.assertEqual(order.payment_status, "PENDING")
        self.assertEqual(order.payment_reference, order.order_number)
        self.assertIsNone(order.paypal_order_id)

    def test_hidden_product_and_media_are_not_public(self):
        with self.assertRaises(HTTPException) as product_ctx:
            routes.get_product(self.hidden_product.id, db=self.db)
        with self.assertRaises(HTTPException) as media_ctx:
            routes.get_media_file(self.hidden_media.id, db=self.db)

        self.assertEqual(product_ctx.exception.status_code, 404)
        self.assertEqual(media_ctx.exception.status_code, 404)

    def test_cart_mutation_requires_owner(self):
        cart_item = routes.add_to_cart(
            routes.schemas.CartBase(product_id=self.product.id, quantity=1),
            db=self.db,
            current_user=self.user,
        )

        with self.assertRaises(HTTPException) as ctx:
            routes.update_cart_item(cart_item.id, quantity=2, db=self.db, current_user=self.other_user)

        self.assertEqual(ctx.exception.status_code, 404)
        self.db.refresh(cart_item)
        self.assertEqual(cart_item.quantity, 1)

    def test_stl_upload_metadata_is_allowed_and_normalised(self):
        filename, content_type = routes.normalise_upload_metadata(
            DummyUpload("figure.STL", "application/octet-stream")
        )

        self.assertEqual(filename, "figure.STL")
        self.assertEqual(content_type, "model/stl")

    def test_stl_upload_rejects_mismatched_content_type(self):
        with self.assertRaises(HTTPException) as ctx:
            routes.normalise_upload_metadata(DummyUpload("figure.stl", "image/png"))

        self.assertEqual(ctx.exception.status_code, 400)

    def test_upload_rejects_unsupported_extensions(self):
        with self.assertRaises(HTTPException) as ctx:
            routes.normalise_upload_metadata(DummyUpload("script.exe", "application/octet-stream"))

        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
