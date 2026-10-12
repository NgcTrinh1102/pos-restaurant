from datetime import date

from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Order, OrderItem, Product, Transaction


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

@login_required
def order_pay_cash(request, pk):
    order = get_object_or_404(Order, pk=pk)

    # Đơn đã thanh toán hoặc đã xóa thì không thanh toán nữa
    if order.is_paid or order.status == Order.Status.DELETED:
        return redirect("order_detail", pk=order.pk)

    error = None
    if request.method == "POST":
        raw = request.POST.get("amount_paid", "").strip()
        try:
            amount_paid = int(raw)
        except ValueError:
            amount_paid = None

        if amount_paid is None or amount_paid < 0:
            error = "Vui lòng nhập số tiền hợp lệ."
        elif amount_paid < order.total:
            error = "Số tiền khách đưa chưa đủ. Vui lòng yêu cầu khách trả thêm."
        else:
            with transaction.atomic():
                Transaction.objects.create(
                    order=order,
                    method=Transaction.Method.CASH,
                    amount_paid=amount_paid,
                    change_returned=amount_paid - order.total,
                )
                order.is_paid = True
                order.status = Order.Status.COMPLETED
                order.save()
            return redirect("order_detail", pk=order.pk)

    return render(request, "pos/order_pay_cash.html", {"order": order, "error": error})

@login_required
@permission_required("pos.view_transaction", raise_exception=True)
def revenue_report(request):
    today = timezone.localdate()
    error = None

    # Đọc ngày người dùng chọn, mặc định là hôm nay
    raw = request.GET.get("date", "")
    try:
        selected = date.fromisoformat(raw) if raw else today
    except ValueError:
        selected = today
        error = "Ngày không hợp lệ."

    # Không cho xem ngày trong tương lai
    if selected > today:
        selected = today
        error = "Không thể xem báo cáo của ngày trong tương lai."

    transactions = Transaction.objects.filter(created_at__date=selected)

    # Tiền thực thu = tiền khách đưa - tiền thừa trả lại
    real_amount = F("amount_paid") - F("change_returned")
    total_revenue = transactions.aggregate(s=Sum(real_amount))["s"] or 0
    cash_revenue = (
        transactions.filter(method=Transaction.Method.CASH)
        .aggregate(s=Sum(real_amount))["s"]
        or 0
    )
    total_orders = transactions.values("order").distinct().count()

    # 5 món bán chạy nhất trong ngày
    top_products = (
        OrderItem.objects.filter(order__transactions__created_at__date=selected)
        .values("product__name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")[:5]
    )

    context = {
        "selected": selected.isoformat(),
        "today": today.isoformat(),
        "error": error,
        "total_revenue": total_revenue,
        "cash_revenue": cash_revenue,
        "total_orders": total_orders,
        "top_products": top_products,
    }
    return render(request, "pos/revenue_report.html", context)
