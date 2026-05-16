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

    def test_openapi_exposes_manual_checkout_contract(self):
        routes.app.openapi_schema = None
        schema = routes.app.openapi()

        required_paths = {
            "/shipping/estimate",
            "/admin/orders",
            "/admin/orders/{order_id}/payment-received",
            "/admin/orders/{order_id}/move-to-production",
            "/admin/orders/{order_id}/ready",
            "/admin/orders/{order_id}/shipped",
            "/admin/orders/{order_id}/cancel",
        }
        self.assertTrue(required_paths.issubset(schema["paths"].keys()))

        order_create = schema["components"]["schemas"]["OrderCreate"]["properties"]
        guest_order = schema["components"]["schemas"]["GuestOrderBase"]["properties"]
        order_response = schema["components"]["schemas"]["Order"]["properties"]
        product_base = schema["components"]["schemas"]["ProductBase"]["properties"]

        checkout_fields = {
            "payment_method",
            "phone",
            "customer_notes",
            "shipping_address_line1",
            "shipping_address_line2",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country_code",
            "products",
        }
        self.assertTrue(checkout_fields.issubset(order_create.keys()))
        self.assertTrue(checkout_fields.issubset(guest_order.keys()))
        self.assertTrue(
            {
                "order_number",
                "payment_method",
                "payment_status",
                "payment_reference",
                "payment_instructions",
                "subtotal",
                "shipping_cost",
                "total_cost",
                "customer_notes",
                "phone",
                "tracking_number",
                "shipping_carrier",
                "admin_notes",
            }.issubset(order_response.keys())
        )
        self.assertEqual(order_create["payment_method"]["enum"], ["bizum", "bank_transfer", "manual"])
        self.assertEqual(product_base["production_type"]["enum"], ["in_stock", "made_to_order", "custom"])

    def test_shipping_estimate_does_not_create_order(self):
        estimate = routes.estimate_checkout_shipping(
            routes.schemas.ManualShippingEstimateRequest(
                currency="USD",
                products=[{"product_id": self.product.id, "quantity": 2}],
            ),
            db=self.db,
        )

        self.assertEqual(estimate["subtotal"], 40.0)
        self.assertEqual(estimate["shipping_cost"], 5.0)
        self.assertEqual(estimate["total_cost"], 45.0)
        self.assertEqual(self.db.query(models.Order).count(), 0)

    def test_admin_order_lifecycle_endpoints(self):
        order = routes.create_guest_order(
            routes.schemas.GuestOrderBase(
                guest_email="buyer@example.com",
                guest_address="Street 1",
                currency="USD",
                products=[{"product_id": self.product.id, "quantity": 1}],
            ),
            db=self.db,
        )

        filtered = routes.read_admin_orders(
            status="AWAITING_PAYMENT",
            payment_status="PENDING",
            db=self.db,
            current_user=self.admin,
        )
        self.assertEqual([item.id for item in filtered], [order.id])

        paid = routes.mark_order_payment_received(
            order.id,
            routes.schemas.AdminOrderNotesUpdate(admin_notes="Bizum received"),
            db=self.db,
            current_user=self.admin,
        )
        self.assertEqual(paid.status, "PAYMENT_RECEIVED")
        self.assertEqual(paid.payment_status, "PAID")
        self.assertEqual(paid.admin_notes, "Bizum received")

        production = routes.move_order_to_production(order.id, db=self.db, current_user=self.admin)
        self.assertEqual(production.status, "IN_PRODUCTION")

        ready = routes.mark_order_ready(order.id, db=self.db, current_user=self.admin)
        self.assertEqual(ready.status, "READY")

        shipped = routes.mark_order_shipped(
            order.id,
            routes.schemas.AdminOrderShippedUpdate(
                tracking_number="TRACK123",
                shipping_carrier="manual",
                admin_notes="Handed to carrier",
            ),
            db=self.db,
            current_user=self.admin,
        )
        self.assertEqual(shipped.status, "SHIPPED")
        self.assertEqual(shipped.tracking_number, "TRACK123")
        self.assertEqual(shipped.shipping_carrier, "manual")
        self.assertIsNotNone(shipped.shipped_at)

    def test_admin_cancel_endpoint_releases_inventory(self):
        order = routes.create_guest_order(
            routes.schemas.GuestOrderBase(
                guest_email="buyer@example.com",
                guest_address="Street 1",
                currency="USD",
                products=[{"product_id": self.product.id, "quantity": 2}],
            ),
            db=self.db,
        )
        self.db.refresh(self.product)
        self.assertEqual(self.product.quantity, 3)

        cancelled = routes.cancel_order(
            order.id,
            routes.schemas.AdminOrderNotesUpdate(admin_notes="Customer changed mind"),
            db=self.db,
            current_user=self.admin,
        )
        self.db.refresh(self.product)

        self.assertEqual(cancelled.status, "CANCELLED")
        self.assertEqual(cancelled.admin_notes, "Customer changed mind")
        self.assertEqual(self.product.quantity, 5)

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
