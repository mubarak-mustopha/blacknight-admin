import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from starlette.middleware.sessions import SessionMiddleware

from app.admin import (
    OrderAdmin,
    OrderItemAdmin,
    OrderReport,
    ProductAdmin,
    SupplierAdmin,
    UserAdmin,
    ReturnOrderItemAdin,
)
from app.auth import AdminAuth
import db

load_dotenv()


class CustomAdmin(Admin):
    @staticmethod
    def get_save_redirect_url(request, form, model_view, obj):
        identity = request.path_params["identity"]
        if identity == "order":
            return request.url_for(
                "admin:details", identity=request.path_params["identity"], pk=obj.id
            )
        else:
            return Admin.get_save_redirect_url(request, form, model_view, obj)


app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SECRET_KEY"],
    max_age=int(os.environ["SESSION_COOKIE_AGE"]),
)

auth_backend = AdminAuth(os.environ["SECRET_KEY"])
admin = CustomAdmin(
    app,
    db.get_engine(),
    authentication_backend=auth_backend,
    session_maker=db.get_session_factory(),
    title="Blacknight Admin",
    templates_dir="app/templates",
)
admin.admin.mount(
    "/custom-statics",
    StaticFiles(directory="app/templates/sqladmin/static"),
    name="custom-statics",
)

admin.add_view(UserAdmin)
admin.add_view(SupplierAdmin)
admin.add_view(ProductAdmin)
admin.add_view(OrderAdmin)
admin.add_view(OrderItemAdmin)
admin.add_view(ReturnOrderItemAdin)
admin.add_view(OrderReport)
