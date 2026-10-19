from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from db import OrderItem
from .conf_timeseries import REPORT_OPTIONS
from . import orders_count_report, revenue_report, status_report
import db


def report_return_rate(session: Session):
    return_rate = func.sum(OrderItem.quantity_returned) / func.sum(OrderItem.count)
    stmt = select(func.coalesce(return_rate * 100, 0.00))

    return session.scalar(stmt)


def get_report_context(request: Request):
    report_option = request.query_params.get("report-option", "daily")

    SessionLocal = db.get_session_factory()
    with SessionLocal() as session:
        order_status_report = status_report.generate_report(session, "order_status")
        order_payment_report = status_report.generate_report(session, "payment_status")

        context = {
            "report_options": list(REPORT_OPTIONS),
            "report_option": report_option,
            "return_rate": report_return_rate(session),
            "revenue_data": revenue_report.generate_report(session, report_option),
            "orders_count_data": orders_count_report.generate_report(
                session, report_option
            ),
            **dict(order_status_report),
            **dict(order_payment_report),
        }
        
        return context
