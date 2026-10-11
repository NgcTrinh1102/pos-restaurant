from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .models import Order, OrderItem, Product


def product_list(request):
    products = Product.objects.select_related("category").order_by("category__name", "name")
    return render(request, "pos/product_list.html", {"products": products})


@login_required
def order_create(request):
    # Chỉ cho gọi những món đang "Còn hàng" (BR_006)
    products = (
        Product.objects.filter(is_available=True)
        .select_related("category")
        .order_by("category__name", "name")
    )

    if request.method == "POST":
        order_type = request.POST.get("order_type", "")
        table_number = request.POST.get("table_number", "").strip()

        # Đọc số lượng của từng món từ form
        selected = []
        errors = []
        for p in products:
            raw = request.POST.get(f"qty_{p.id}", "0")
            try:
                qty = int(raw)
            except ValueError:
                qty = 0
            if qty > 999:
                errors.append(f"Số lượng món {p.name} tối đa là 999.")
            elif qty > 0:
                selected.append((p, qty))

        # Kiểm tra dữ liệu (validation)
        if order_type not in (Order.OrderType.DINE_IN, Order.OrderType.TAKE_AWAY):
            errors.append("Vui lòng chọn loại đơn hàng.")
        if order_type == Order.OrderType.DINE_IN and not table_number:
            errors.append("Đơn ăn tại chỗ cần nhập số bàn.")
        if not selected:
            errors.append("Vui lòng chọn ít nhất một món.")

        if errors:
            return render(request, "pos/order_create.html", {"products": products, "errors": errors})

        # Lưu đơn hàng và các dòng món trong một khối
        with transaction.atomic():
            order = Order.objects.create(
                order_type=order_type,
                table_number=table_number if order_type == Order.OrderType.DINE_IN else "",
                created_by=request.user,
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(order=order, product=p, quantity=qty, unit_price=p.price)
                    for p, qty in selected
                ]
            )
        return redirect("order_detail", pk=order.pk)

    return render(request, "pos/order_create.html", {"products": products})


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    items = order.items.select_related("product")
    return render(request, "pos/order_detail.html", {"order": order, "items": items})