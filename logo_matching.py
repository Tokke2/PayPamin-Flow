"""Conservative visual matching of invoice logos against saved supplier SVGs.

The expensive imaging imports are lazy so text matching and the rest of the app
remain usable if OpenCV is unavailable. A visual match requires distinctive
SIFT features, a consistent projective transform and a clear winner between
supplier profiles. No invoice image or feature data leaves the computer.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import logging
from math import isfinite
from pathlib import Path

from app_info import APP_SLUG
from supplier_matching import SupplierMatch


logger = logging.getLogger(APP_SLUG)


_REFERENCE_CACHE = {}
_SUPPORTED_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class _VisualCandidate:
    vendor: str
    quality: float


def _safe_logo_path(svg_dir, filename):
    root = Path(svg_dir).resolve()
    # Supplier logos are rooted directly in svg/, just like the export workflow.
    basename = Path(str(filename or "").replace("\\", "/")).name
    if not basename or Path(basename).suffix.lower() not in _SUPPORTED_SUFFIXES:
        return None
    path = (root / basename).resolve()
    return path if path.parent == root and path.is_file() else None


def _crop_logo(image, cv2, np):
    mask = (image.min(axis=2) < 248).astype("uint8") * 255
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    if width < 12 or height < 8:
        return None
    cropped = image[y:y + height, x:x + width]
    if max(cropped.shape[:2]) > 800:
        scale = 800 / max(cropped.shape[:2])
        cropped = cv2.resize(
            cropped,
            (max(12, round(cropped.shape[1] * scale)), max(8, round(cropped.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return np.ascontiguousarray(cropped)


def _reference_image(path):
    path = Path(path)
    try:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None
    cached = _REFERENCE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        import fitz
        import cv2
        import numpy as np
        from PIL import Image

        if path.suffix.lower() == ".svg":
            from svglib.svglib import svg2rlg
            from reportlab.graphics import renderPDF

            drawing = svg2rlg(str(path))
            width = float(drawing.width)
            height = float(drawing.height)
            if not isfinite(width) or not isfinite(height) or width <= 0 or height <= 0:
                return None
            scale = max(0.1, min(4.0, 600 / max(width, height)))
            pdf_bytes = renderPDF.drawToString(drawing)
            with fitz.open("pdf", pdf_bytes) as document:
                pixmap = document[0].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
        else:
            image = Image.open(path)
        if image.mode in ("RGBA", "LA"):
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            image = background
        rgb = np.array(image.convert("RGB"))
        cropped = _crop_logo(rgb, cv2, np)
    except Exception:
        return None
    if cropped is not None:
        if len(_REFERENCE_CACHE) >= 32:
            _REFERENCE_CACHE.clear()
        _REFERENCE_CACHE[key] = cropped
    return cropped


def _page_image(path, page_index):
    try:
        import fitz
        import numpy as np
        from PIL import Image

        with fitz.open(path) as document:
            if page_index < 0 or page_index >= len(document):
                return None
            pixmap = document[page_index].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return np.array(Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB"))
    except Exception:
        return None


def _plausible_transform(matrix, reference_shape, page_shape, cv2, np):
    if matrix is None:
        return False
    height, width = reference_shape[:2]
    corners = np.float32([[[0, 0], [width, 0], [width, height], [0, height]]])
    try:
        projected = cv2.perspectiveTransform(corners, matrix)[0]
    except cv2.error:
        return False
    if not np.isfinite(projected).all():
        return False
    top, right, bottom, left = projected
    horizontal = (np.linalg.norm(right - top) + np.linalg.norm(bottom - left)) / (2 * width)
    vertical = (np.linalg.norm(left - top) + np.linalg.norm(bottom - right)) / (2 * height)
    if not (0.05 <= horizontal <= 12 and 0.05 <= vertical <= 12):
        return False
    if not 0.55 <= horizontal / vertical <= 1.8:
        return False
    area = abs(float(cv2.contourArea(projected)))
    page_area = page_shape[0] * page_shape[1]
    if area < 150 or area > page_area * 0.6:
        return False
    page_height, page_width = page_shape[:2]
    if not (-page_width * 0.1 <= projected[:, 0].mean() <= page_width * 1.1):
        return False
    if not (-page_height * 0.1 <= projected[:, 1].mean() <= page_height * 1.1):
        return False
    return True


def _feature_quality(reference, page, sift, page_keypoints, page_descriptors, cv2, np):
    reference_gray = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)
    reference_keypoints, reference_descriptors = sift.detectAndCompute(reference_gray, None)
    if (
        reference_descriptors is None
        or page_descriptors is None
        or len(reference_keypoints) < 12
        or len(reference_descriptors) < 2
        or len(page_descriptors) < 2
    ):
        return None
    pairs = cv2.BFMatcher().knnMatch(reference_descriptors, page_descriptors, k=2)
    good = []
    for pair in pairs:
        if len(pair) != 2:
            continue
        first, second = pair
        if first.distance < 0.70 * second.distance:
            good.append(first)
    if len(good) < 12:
        return None
    source = np.float32([reference_keypoints[match.queryIdx].pt for match in good]).reshape(-1, 1, 2)
    target = np.float32([page_keypoints[match.trainIdx].pt for match in good]).reshape(-1, 1, 2)
    try:
        matrix, inlier_mask = cv2.findHomography(source, target, cv2.RANSAC, 5.0)
    except cv2.error:
        return None
    if inlier_mask is None or not _plausible_transform(matrix, reference.shape, page.shape, cv2, np):
        return None
    inliers = int(inlier_mask.sum())
    if inliers < 10:
        return None
    inlier_ratio = inliers / len(good)
    coverage = inliers / len(reference_keypoints)
    if inlier_ratio < 0.45 or coverage < 0.08:
        return None
    return inliers + 8 * inlier_ratio + 8 * coverage


def match_pdf_logo(path, page_indexes, profiles, svg_dir) -> SupplierMatch | None:
    """Return a unique visual supplier match, no match, or an ambiguity marker."""
    try:
        import cv2
        import numpy as np
    except (ImportError, ModuleNotFoundError):
        logger.warning('Visual supplier logo matching unavailable because OpenCV is missing: file=%s',path)
        return None

    indexes = list(page_indexes) if page_indexes is not None else [0]
    page_index = indexes[0] if indexes else 0
    page = _page_image(path, page_index)
    if page is None:
        logger.warning('Visual supplier logo matching could not read the PDF page: file=%s page=%d',path,page_index+1)
        return None
    page_gray = cv2.cvtColor(page, cv2.COLOR_RGB2GRAY)
    try:
        sift = cv2.SIFT_create(nfeatures=1800, contrastThreshold=0.02)
        page_keypoints, page_descriptors = sift.detectAndCompute(page_gray, None)
    except (AttributeError, cv2.error) as exc:
        logger.warning('Visual supplier logo feature extraction failed: file=%s page=%d error=%s',path,page_index+1,exc)
        return None
    if page_descriptors is None:
        logger.warning('Visual supplier logo matching found no usable PDF features: file=%s page=%d',path,page_index+1)
        return None

    candidates = {}
    quality_by_logo = {}
    for profile in profiles:
        vendor = str(profile.get("vendor") or "").strip()
        logo_file = str(profile.get("logo_file") or "")
        if not vendor or not logo_file:
            continue
        logo_path = _safe_logo_path(svg_dir, logo_file)
        if logo_path is None:
            logger.warning('Supplier logo reference is missing or outside the SVG folder: vendor=%s logo=%s',vendor,logo_file)
            continue
        cache_key = str(logo_path)
        if cache_key not in quality_by_logo:
            reference = _reference_image(logo_path)
            if reference is None:
                logger.warning('Supplier logo reference could not be rendered: vendor=%s logo=%s',vendor,logo_file)
            try:
                quality = _feature_quality(reference, page, sift, page_keypoints, page_descriptors, cv2, np) if reference is not None else None
            except cv2.error as exc:
                logger.warning('Supplier logo comparison failed: vendor=%s logo=%s error=%s',vendor,logo_file,exc)
                quality = None
            quality_by_logo[cache_key] = quality
        quality = quality_by_logo[cache_key]
        if quality is None:
            continue
        key = vendor.casefold()
        candidate = _VisualCandidate(vendor, quality)
        if key not in candidates or quality > candidates[key].quality:
            candidates[key] = candidate

    if not candidates:
        logger.warning('Visual supplier logo matching found no candidate above the acceptance threshold: file=%s page=%d',path,page_index+1)
        return None
    ranked = sorted(candidates.values(), key=lambda candidate: candidate.quality, reverse=True)
    best = ranked[0]
    if len(ranked) > 1:
        second = ranked[1]
        if second.quality >= best.quality - 4 and second.quality >= best.quality * 0.85:
            logger.warning('Visual supplier logo match is ambiguous: file=%s page=%d first=%s second=%s',path,page_index+1,best.vendor,second.vendor)
            return SupplierMatch("", "ambiguous_visual_logo", 0)
    logger.info('Visual supplier logo accepted: file=%s page=%d vendor=%s quality=%.2f',path,page_index+1,best.vendor,best.quality)
    return SupplierMatch(best.vendor, "visual_logo", int(round(best.quality * 10)))
