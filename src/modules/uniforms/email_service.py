"""
Cerasus Hub -- Uniforms Module: Email Service
Sends uniform-related email notifications (low stock alerts, order confirmations, etc.).
"""


def send_low_stock_alert(item_name: str, current_qty: int, reorder_point: int, recipients: list = None):
    """Send a low-stock alert email for a uniform item."""
    try:
        from src.email_service import send_email
        subject = f"[Cerasus Hub] Low Stock Alert: {item_name}"
        body = (
            f"The following uniform item is running low:\n\n"
            f"  Item: {item_name}\n"
            f"  Current Stock: {current_qty}\n"
            f"  Reorder Point: {reorder_point}\n\n"
            f"Please reorder soon."
        )
        if recipients:
            for addr in recipients:
                send_email(addr, subject, body)
    except Exception:
        pass


def send_order_confirmation(officer_name: str, items: list, recipient: str = ""):
    """Send an order confirmation email."""
    try:
        from src.email_service import send_email
        subject = f"[Cerasus Hub] Uniform Order Confirmation for {officer_name}"
        lines = [f"  - {i}" for i in items]
        body = (
            f"Uniform order placed for {officer_name}:\n\n"
            + "\n".join(lines)
            + "\n\nYou will be notified when the order is fulfilled."
        )
        if recipient:
            send_email(recipient, subject, body)
    except Exception:
        pass
