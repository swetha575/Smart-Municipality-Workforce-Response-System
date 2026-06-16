import base64
import binascii


class WebcamImageError(ValueError):
    pass


def extract_image_bytes(file_storage=None, captured_data_url=None):
    if file_storage and getattr(file_storage, "filename", ""):
        return file_storage.read()

    data_url = (captured_data_url or "").strip()
    if not data_url:
        raise WebcamImageError("No image data was provided.")

    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise WebcamImageError("Captured webcam image format is invalid.")

    _, encoded = data_url.split(";base64,", 1)
    try:
        return base64.b64decode(encoded)
    except (ValueError, binascii.Error) as exc:
        raise WebcamImageError("Unable to decode captured webcam image.") from exc
