from django.shortcuts import render

from .models import Product


def product_list(request):
    products = Product.objects.select_related("category").order_by("category__name", "name")
    return render(request, "pos/product_list.html", {"products": products})