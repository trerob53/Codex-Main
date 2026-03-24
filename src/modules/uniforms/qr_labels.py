"""
Cerasus Hub -- Uniforms Module: QR Label Generator
Generates QR-code labels for uniform items and issuances.
"""

import os


def generate_item_label(item_id: str, item_name: str, size: str = "", output_dir: str = "") -> str:
    """Generate a QR-code label for a catalog item. Returns the file path."""
    try:
        import qrcode
        data = f"cerasus:uniform:{item_id}:{size}"
        img = qrcode.make(data)
        if not output_dir:
            from src.config import LABELS_DIR
            output_dir = LABELS_DIR
        os.makedirs(output_dir, exist_ok=True)
        filename = f"uni_{item_id}_{size}.png" if size else f"uni_{item_id}.png"
        path = os.path.join(output_dir, filename)
        img.save(path)
        return path
    except ImportError:
        # qrcode library not installed
        return ""
    except Exception:
        return ""


def generate_issuance_label(issuance_id: str, officer_name: str, item_name: str,
                            output_dir: str = "") -> str:
    """Generate a QR-code label for a specific issuance."""
    try:
        import qrcode
        data = f"cerasus:issuance:{issuance_id}"
        img = qrcode.make(data)
        if not output_dir:
            from src.config import LABELS_DIR
            output_dir = LABELS_DIR
        os.makedirs(output_dir, exist_ok=True)
        filename = f"iss_{issuance_id}.png"
        path = os.path.join(output_dir, filename)
        img.save(path)
        return path
    except ImportError:
        return ""
    except Exception:
        return ""
