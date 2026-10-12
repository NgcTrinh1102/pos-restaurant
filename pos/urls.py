from django.urls import path

from . import views

urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path("products/new/", views.product_create, name="product_create"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/new/", views.order_create, name="order_create"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/pay/", views.order_pay_cash, name="order_pay_cash"),
    path("orders/<int:pk>/paid/", views.order_paid, name="order_paid"),
    path("orders/<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path("reports/revenue/", views.revenue_report, name="revenue_report"),
]
