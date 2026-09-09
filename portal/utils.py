import base64
from io import BytesIO


def qr_data_uri(text: str, box_size: int = 4) -> str:
    """Return a base64 PNG data URI for a QR code, or '' if qrcode isn't installed."""
    try:
        import qrcode
    except Exception:  # pragma: no cover - optional dependency
        return ""
    img = qrcode.make(text, box_size=box_size, border=1)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
