from django.urls import path

from . import views

urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path("orders/new/", views.order_create, name="order_create"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/pay/", views.order_pay_cash, name="order_pay_cash"),
    path("reports/revenue/", views.revenue_report, name="revenue_report"),
]