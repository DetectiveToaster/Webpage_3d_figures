import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, models, schemas


class SecurityFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        models.Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()

        self.user_one = models.User(email="one@example.com", password="hash")
        self.user_two = models.User(email="two@example.com", password="hash")
        self.product = models.Product(
            type="base",
            name="Figure",
            quantity=5,
            price=20,
            discounted_price=15,
            is_visible=True,
            status="published",
        )
        self.hidden_product = models.Product(
            type="base",
            name="Hidden",
            quantity=5,
            price=10,
            is_visible=False,
            status="draft",
        )
        self.db.add_all([self.user_one, self.user_two, self.product, self.hidden_product])
        self.db.commit()
        for item in (self.user_one, self.user_two, self.product, self.hidden_product):
            self.db.refresh(item)

    def tearDown(self):
        self.db.close()
        models.Base.metadata.drop_all(bind=self.engine)

    def test_guest_order_calculates_total_from_catalog_price(self):
        order = schemas.GuestOrderBase(
            guest_email="buyer@example.com",
            guest_address="Street 1",
            currency="usd",
            products=[
                {"product_id": self.product.id, "quantity": 2, "unit_price": 0.01},
            ],
        )

        created = crud.create_guest_order(self.db, order)

        self.assertEqual(float(created.subtotal), 30.0)
        self.assertEqual(float(created.total_cost), 35.0)
        self.assertEqual(created.status, "AWAITING_PAYMENT")
        self.assertEqual(created.payment_status, "PENDING")
        self.assertEqual(float(created.products[0].unit_price), 15.0)
        self.db.refresh(self.product)
        self.assertEqual(self.product.quantity, 3)

    def test_guest_order_rejects_hidden_product(self):
        order = schemas.GuestOrderBase(
            guest_email="buyer@example.com",
            guest_address="Street 1",
            currency="USD",
            products=[{"product_id": self.hidden_product.id, "quantity": 1}],
        )

        with self.assertRaises(ValueError):
            crud.create_guest_order(self.db, order)

    def test_paid_order_updates_sold_count_once(self):
        order = schemas.OrderCreate(
            currency="USD",
            products=[{"product_id": self.product.id, "quantity": 2}],
        )
        created = crud.create_order_for_user(self.db, self.user_one.id, order)

        crud.update_order_admin(self.db, created.id, schemas.OrderAdminUpdate(payment_status="PAID"))
        crud.update_order_status(self.db, created.id, "COMPLETED")
        self.db.refresh(self.product)

        self.assertEqual(self.product.quantity, 3)
        self.assertEqual(self.product.sold_count, 2)

    def test_cancelled_order_releases_reserved_inventory(self):
        order = schemas.OrderCreate(
            currency="USD",
            products=[{"product_id": self.product.id, "quantity": 2}],
        )
        created = crud.create_order_for_user(self.db, self.user_one.id, order)

        crud.update_order_status(self.db, created.id, "CANCELLED")
        self.db.refresh(self.product)

        self.assertEqual(self.product.quantity, 5)

    def test_cart_updates_are_scoped_to_owner(self):
        cart_item = crud.add_to_cart(
            self.db,
            self.user_one.id,
            schemas.CartBase(product_id=self.product.id, quantity=1),
        )

        other_user_update = crud.update_cart_item(self.db, self.user_two.id, cart_item.id, 2)

        self.assertIsNone(other_user_update)
        self.db.refresh(cart_item)
        self.assertEqual(cart_item.quantity, 1)


if __name__ == "__main__":
    unittest.main()
