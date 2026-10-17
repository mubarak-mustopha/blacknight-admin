import enum
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List

from dotenv import load_dotenv
from sqlalchemy import (
    CheckConstraint,
    DECIMAL,
    DateTime,
    Enum,
    ForeignKey,
    String,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"], echo=True)


def get_session_factory():
    return sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32))
    hash_password: Mapped[str]

    def __repr__(self):
        return self.username


class Platform(enum.Enum):
    Alibaba = "alibaba"
    Amazon = "amazon"
    eBay = "eBay"
    Local = "local"


class Supplier(Base):
    __tablename__ = "supplier"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    platform: Mapped[enum.Enum] = mapped_column(Enum(Platform))
    contact_info: Mapped[Optional[str]]

    products: Mapped[List["Product"]] = relationship(back_populates="supplier")

    def __str__(self):
        return self.name


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    # 9,999,999 ~ N 10million
    price: Mapped[Decimal] = mapped_column(DECIMAL(9, 2))
    stock_count: Mapped[int]

    supplier_id: Mapped[int] = mapped_column(ForeignKey(Supplier.id))
    supplier: Mapped[Supplier] = relationship(back_populates="products")

    __table_args__ = (CheckConstraint("stock_count >= 0", "ch_stock_count_nonneg"),)

    def __str__(self):
        return self.name


class OrderStatus(enum.Enum):
    Pending = "pending"
    Shipped = "shipped"
    Delivered = "delivered"
    Cancelled = "cancelled"


class PaymentStatus(enum.Enum):
    Unpaid = "unpaid"
    Paid = "paid"


class Order(Base):
    __tablename__ = "order"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(True), default=lambda: datetime.now(timezone.utc)
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(True), nullable=True
    )
    status: Mapped[enum.Enum] = mapped_column(Enum(OrderStatus))
    payment_status: Mapped[enum.Enum] = mapped_column(Enum(PaymentStatus))

    order_items: Mapped[List["OrderItem"]] = relationship(
        lazy="selectin", back_populates="order"
    )

    __table_args__ = (
        CheckConstraint("delivered_at > created_at", "ch_delivered_at_gt_created_at"),
    )

    def __str__(self):
        return f"Order #{str(self.id)}"


class OrderItem(Base):
    __tablename__ = "orderitem"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey(Order.id))
    product_id: Mapped[int] = mapped_column(ForeignKey(Product.id))
    count: Mapped[int] = mapped_column(default=1)
    quantity_returned: Mapped[int] = mapped_column(default=0)
    price: Mapped[Decimal] = mapped_column(DECIMAL(9, 2))

    order: Mapped[Order] = relationship(back_populates="order_items", lazy="selectin")
    product: Mapped[Product] = relationship(lazy="selectin")

    __table_args__ = (
        CheckConstraint("count >= 1", "ch_count_ge_1"),
        CheckConstraint("quantity_returned >= 0", "ch_quantity_returned_nonneg"),
        CheckConstraint("quantity_returned <= count", "ch_quantity_returned_le_count"),
    )

    def __str__(self):
        return f"{self.order} - {self.product}"
