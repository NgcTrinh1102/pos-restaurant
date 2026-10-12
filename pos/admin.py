from django.contrib import admin
from .models import Category, Product, Order, OrderItem, Transaction

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Transaction)
admin.site.site_header = "Xiaoyu Vietnam POS - Quản trị"
admin.site.site_title = "Xiaoyu POS"
admin.site.index_title = "Quản lý hệ thống bán hàng"