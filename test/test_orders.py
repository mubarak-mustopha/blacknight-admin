import os
import pytest

from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqladmin import Admin
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session
from testcontainers.community.postgres import PostgresContainer

from app.admin import OrderAdmin, OrderItemAdmin
from db import (
    Base,
    Product,
    Order,
    OrderItem,
    PaymentStatus,
    Platform,
    OrderStatus,
    Supplier,
)

from .baseline import create_baseline

UPDATE_ENPOINT = "/admin/order/edit/{pk}"

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres

@pytest.fixture(scope="session")
def engine(postgres_container):
    engine = create_engine(postgres_container.get_connection_url())
    yield engine
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def baseline(engine):
    Base.metadata.create_all(engine)
    try:
        create_baseline(engine)
        yield
    finally:
        Base.metadata.drop_all(engine)


@pytest.fixture(scope="session", autouse=True)
def verified_baseline(baseline, engine):
    with Session(engine) as session:
        products_exist = select(1).where(select(Product.id).exists())
        orders_exist = select(1).where(select(Order.id).exists())
        orderitems_exist = select(1).where(select(OrderItem.id).exists())

        if any(
            session.execute(stmt).scalar_one_or_none() is None
            for stmt in [products_exist, orders_exist, orderitems_exist]
        ):
            pytest.exit(
                "Test cannot proceed with empty product, order or orderitem table in the test database.",
                returncode=1,
            )


@pytest.fixture
def session_factory(engine):
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield SessionLocal
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(session_factory, engine, monkeypatch):
    import db

    monkeypatch.setattr(db, "get_session_factory", lambda: session_factory)

    app = FastAPI()
    admin = Admin(
        app, engine=engine, session_maker=session_factory, templates_dir="app/templates"
    )
    admin.add_view(OrderAdmin)
    admin.add_view(OrderItemAdmin)

    return TestClient(app)


@pytest.fixture
def get_an_order_by_status():
    def _query(status: OrderStatus):
        return select(Order).filter_by(status=status).order_by(Order.id).limit(1)

    return _query


@pytest.fixture
def insufficient_stock_order():
    supplier = Supplier(name="Apple Stores", platform=Platform.eBay)
    product1 = Product(
        name="Iphone 16", price=Decimal(1350000), stock_count=4, supplier=supplier
    )
    product2 = Product(
        name="Mac Book Pro", price=Decimal(1350000), stock_count=1, supplier=supplier
    )

    item1 = OrderItem(count=10, price=Decimal(1600000), product=product1)
    item2 = OrderItem(count=1, price=Decimal(1600000), product=product1)
    order = Order(
        status=OrderStatus.Pending,
        payment_status=PaymentStatus.Unpaid,
        order_items=[item1, item2],
    )
    return supplier, [product1, product2], order, [item1, item2]


def test_pending_to_shipped_decrements_product_count(
    session_factory, client, get_an_order_by_status
):
    with session_factory() as session:
        stmt = get_an_order_by_status(OrderStatus.Pending)
        order = session.execute(stmt).scalar_one_or_none()
        assert order is not None
        initial_prod_counts = [item.product.stock_count for item in order.order_items]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "status": OrderStatus.Shipped.name,
            "payment_status": order.payment_status.name,
        }
        response = client.post(endpoint, data=form_data)
        assert response.status_code == 200

        session.refresh(order)
        actual_final_counts = [item.product.stock_count for item in order.order_items]
        expected_final_counts = [
            initial - item.count
            for initial, item in zip(initial_prod_counts, order.order_items)
        ]
        assert order.status == OrderStatus.Shipped
        assert actual_final_counts == expected_final_counts


def test_pending_to_delivered_decrements_product_count(
    session_factory, client, get_an_order_by_status
):
    with session_factory() as session:
        stmt = get_an_order_by_status(OrderStatus.Pending)
        order = session.execute(stmt).scalar_one_or_none()
        assert order is not None
        initial_prod_counts = [item.product.stock_count for item in order.order_items]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "status": OrderStatus.Delivered.name,
            "payment_status": PaymentStatus.Paid.name,
        }
        response = client.post(endpoint, data=form_data)
        assert response.status_code == 200

        session.refresh(order)
        actual_final_counts = [item.product.stock_count for item in order.order_items]
        expected_final_counts = [
            initial - item.count
            for initial, item in zip(initial_prod_counts, order.order_items)
        ]
        assert order.status == OrderStatus.Delivered
        assert order.payment_status == PaymentStatus.Paid
        assert actual_final_counts == expected_final_counts


def test_pending_to_cancelled_keeps_product_count_unchanged(
    session_factory, client, get_an_order_by_status
):
    with session_factory() as session:
        stmt = get_an_order_by_status(OrderStatus.Pending)
        order = session.execute(stmt).scalar_one_or_none()
        assert order is not None
        initial_prod_counts = [item.product.stock_count for item in order.order_items]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "status": OrderStatus.Cancelled.name,
            "payment_status": order.payment_status.name,
        }
        response = client.post(endpoint, data=form_data)
        assert response.status_code == 200

        session.refresh(order)
        final_prod_counts = [item.product.stock_count for item in order.order_items]
        assert order.status == OrderStatus.Cancelled
        assert final_prod_counts == initial_prod_counts


def test_shipped_to_cancelled_increments_product_count(
    session_factory, client, get_an_order_by_status
):
    with session_factory() as session:
        stmt = get_an_order_by_status(OrderStatus.Shipped)
        order = session.execute(stmt).scalar_one_or_none()
        assert order is not None
        initial_prod_counts = [item.product.stock_count for item in order.order_items]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "status": OrderStatus.Cancelled.name,
            "payment_status": order.payment_status.name,
        }
        response = client.post(endpoint, data=form_data)
        assert response.status_code == 200

        session.refresh(order)
        actual_final_counts = [item.product.stock_count for item in order.order_items]
        expected_final_counts = [
            initial + item.count
            for initial, item in zip(initial_prod_counts, order.order_items)
        ]
        assert order.status == OrderStatus.Cancelled
        assert actual_final_counts == expected_final_counts


def test_shipped_to_delivered_keeps_product_count_unchanged(
    session_factory, client, get_an_order_by_status
):
    with session_factory() as session:
        stmt = get_an_order_by_status(OrderStatus.Shipped)
        order = session.execute(stmt).scalar_one_or_none()
        assert order is not None
        initial_prod_counts = [item.product.stock_count for item in order.order_items]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "status": OrderStatus.Delivered.name,
            "payment_status": order.payment_status.name,
        }
        response = client.post(endpoint, data=form_data)
        assert response.status_code == 200

        session.refresh(order)
        final_prod_counts = [item.product.stock_count for item in order.order_items]
        assert order.status == OrderStatus.Delivered
        assert final_prod_counts == initial_prod_counts


def test_shipped_to_pending_invalid(session_factory, client, get_an_order_by_status):
    with session_factory() as session:
        stmt = get_an_order_by_status(OrderStatus.Shipped)
        order = session.execute(stmt).scalar_one_or_none()
        assert order is not None

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "status": OrderStatus.Pending.name,
            "payment_status": order.payment_status.name,
        }
        response = client.post(endpoint, data=form_data)
        assert response.status_code == 400


def test_shipped_to_pending_keeps_prod_counts_unchanged(
    session_factory, client, get_an_order_by_status
):
    with session_factory() as session:
        stmt = get_an_order_by_status(OrderStatus.Shipped)
        order = session.execute(stmt).scalar_one_or_none()
        assert order is not None
        initial_prod_counts = [item.product.stock_count for item in order.order_items]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "status": OrderStatus.Pending.name,
            "payment_status": order.payment_status.name,
        }
        response = client.post(endpoint, data=form_data)
        assert response.status_code == 400

        session.refresh(order)
        final_prod_counts = [item.product.stock_count for item in order.order_items]
        assert initial_prod_counts == final_prod_counts


def test_delivered_is_a_final_state(session_factory, client, get_an_order_by_status):
    with session_factory() as session:
        stmt = get_an_order_by_status(OrderStatus.Delivered)
        order = session.execute(stmt).scalar_one_or_none()
        assert order is not None
        initial_prod_counts = [item.product.stock_count for item in order.order_items]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "payment_status": order.payment_status.name,
        }
        states = set(OrderStatus) - {OrderStatus.Delivered}
        for state in states:
            form_data["status"] = state.name
            response = client.post(endpoint, data=form_data)

            session.refresh(order)
            final_prod_counts = [item.product.stock_count for item in order.order_items]

            assert response.status_code == 400
            assert initial_prod_counts == final_prod_counts


def test_cancelled_is_a_final_state(session_factory, client, get_an_order_by_status):
    with session_factory() as session:
        stmt = get_an_order_by_status(OrderStatus.Cancelled)
        order = session.execute(stmt).scalar_one_or_none()
        assert order is not None
        initial_prod_counts = [item.product.stock_count for item in order.order_items]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "payment_status": order.payment_status.name,
        }
        states = set(OrderStatus) - {OrderStatus.Cancelled}
        for state in states:
            form_data["status"] = state.name
            response = client.post(endpoint, data=form_data)

            session.refresh(order)
            final_prod_counts = [item.product.stock_count for item in order.order_items]

            assert response.status_code == 400
            assert initial_prod_counts == final_prod_counts


def test_pending_to_shipped_fails_on_low_stock_count(
    session_factory, client, insufficient_stock_order
):
    with session_factory() as session:
        _, products, order, items = insufficient_stock_order
        assert order.status == OrderStatus.Pending

        session.add_all([*products, order, *items])
        session.commit()
        initial_stock_counts = [product.stock_count for product in products]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "status": OrderStatus.Shipped.name,
            "payment_status": PaymentStatus.Paid,
        }
        response = client.post(endpoint, data=form_data)

        session.refresh(order)
        for product in products:
            session.refresh(product)
        final_stock_counts = [product.stock_count for product in products]

        assert response.status_code == 400
        assert order.status == OrderStatus.Pending
        assert initial_stock_counts == final_stock_counts


def test_pending_to_delivered_fails_on_low_stock_count(
    session_factory, client, insufficient_stock_order
):
    with session_factory() as session:
        _, products, order, items = insufficient_stock_order
        assert order.status == OrderStatus.Pending

        session.add_all([*products, order, *items])
        session.commit()
        initial_stock_counts = [product.stock_count for product in products]

        endpoint = UPDATE_ENPOINT.format(pk=order.id)
        form_data = {
            "status": OrderStatus.Delivered.name,
            "payment_status": PaymentStatus.Paid,
        }
        response = client.post(endpoint, data=form_data)

        session.refresh(order)
        for product in products:
            session.refresh(product)
        final_stock_counts = [product.stock_count for product in products]

        assert response.status_code == 400
        assert order.status == OrderStatus.Pending
        assert initial_stock_counts == final_stock_counts
