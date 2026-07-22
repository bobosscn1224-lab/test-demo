"""Prompt and output gate shared by every paid image backend."""
from __future__ import annotations

import copy
import logging
import math
import statistics
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageFilter, ImageStat

from app.config import settings

logger = logging.getLogger(__name__)
_SPEC_PATH = Path(__file__).parent / "collage_prompt_spec.yaml"
with _SPEC_PATH.open(encoding="utf-8") as f:
    IMAGE_SPECS = (yaml.safe_load(f) or {}).get("image_interactions") or {}


def get_image_spec(interaction_name: str) -> dict:
    named = IMAGE_SPECS.get(interaction_name)
    if not named or interaction_name.startswith("_"):
        raise ValueError(f"Unknown image interaction: {interaction_name}")
    result = copy.deepcopy(IMAGE_SPECS.get("_defaults") or {})
    for key, value in named.items():
        if key == "prompt_requirements":
            result.setdefault(key, [])
            result[key].extend(copy.deepcopy(value or []))
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate_image_specs() -> list[str]:
    errors: list[str] = []
    for name in IMAGE_SPECS:
        if name.startswith("_") or name == "version":
            continue
        try:
            spec = get_image_spec(name)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        if not spec.get("description"):
            errors.append(f"{name}: description missing")
        if not spec.get("vision_review_prompt"):
            errors.append(f"{name}: vision_review_prompt missing")
        if int(spec.get("max_retries", -1)) < 0 or int(spec.get("max_retries", 0)) > 2:
            errors.append(f"{name}: max_retries must be 0..2")
        if name == "ppt_collage":
            geometry = spec.get("grid_geometry") or {}
            normalization = geometry.get("normalization") or {}
            if geometry.get("on_detection_failure") not in {"vision_review", "reject"}:
                errors.append("ppt_collage: invalid grid detection fallback")
            if geometry.get("enforcement") not in {"hard", "hard_when_confident", "diagnostic_only"}:
                errors.append("ppt_collage: invalid grid geometry enforcement")
            if normalization.get("enabled"):
                if normalization.get("fit_mode") != "contain":
                    errors.append("ppt_collage: normalization must use contain mode")
                for key in ("margin_fraction", "gap_fraction"):
                    value = normalization.get(key)
                    if not isinstance(value, (int, float)) or not 0 <= float(value) <= 0.10:
                        errors.append(f"ppt_collage: invalid normalization.{key}")
    return errors


_SPEC_ERRORS = validate_image_specs()
if _SPEC_ERRORS:
    raise RuntimeError("Invalid image generation specs: " + " | ".join(_SPEC_ERRORS))


def validate_image_prompt(prompt: str, interaction_name: str,
                          context: dict[str, Any] | None = None) -> list[str]:
    context = context or {}
    spec = get_image_spec(interaction_name)
    failures: list[str] = []
    length = len((prompt or "").strip())
    if length < int(spec.get("min_prompt_chars", 8)):
        failures.append(f"Prompt 太短：{length}，至少需要 {spec.get('min_prompt_chars')} 字")
    if length > int(spec.get("max_prompt_chars", 8000)):
        failures.append(f"Prompt 太长：{length}，最多允许 {spec.get('max_prompt_chars')} 字")
    if interaction_name == "ppt_collage":
        expected_pages = int(context.get("expected_pages") or 0)
        outline = str(context.get("outline") or "")
        if expected_pages <= 0:
            failures.append("拼图缺少 expected_pages")
        if len(outline.strip()) < 50:
            failures.append("拼图缺少完整大纲内容")
        if expected_pages > 0 and outline:
            from app.services.collage_prompt_spec import validate_prompt
            failures.extend(validate_prompt(prompt, expected_pages, outline))
    return failures


def enrich_image_prompt(prompt: str, interaction_name: str) -> str:
    spec = get_image_spec(interaction_name)
    rules = [str(x).strip() for x in spec.get("prompt_requirements", []) if str(x).strip()]
    rendered = "\n".join(f"{idx}. {rule}" for idx, rule in enumerate(rules, 1))
    return f"━━━ 图像质量门禁要求（不可违反）━━━\n{rendered}\n\n{prompt.rstrip()}"


def _expected_aspect(size: str, context: dict[str, Any]) -> float | None:
    if context.get("expected_canvas_aspect"):
        return float(context["expected_canvas_aspect"])
    try:
        width, height = [int(x) for x in size.lower().split("x", 1)]
        return width / height
    except Exception:
        return None


def _content_components(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """Detect card-like regions against the collage's dominant border color."""
    original_width, original_height = image.size
    probe = image.convert("RGB")
    probe.thumbnail((600, 600))
    width, height = probe.size
    pixels = probe.load()
    border = []
    step_x = max(1, width // 80)
    step_y = max(1, height // 80)
    for x in range(0, width, step_x):
        border.extend((pixels[x, 0], pixels[x, height - 1]))
    for y in range(0, height, step_y):
        border.extend((pixels[0, y], pixels[width - 1, y]))
    background = tuple(int(statistics.median(p[channel] for p in border)) for channel in range(3))

    mask = Image.new("L", (width, height), 0)
    mask_pixels = mask.load()
    for y in range(height):
        for x in range(width):
            color = pixels[x, y]
            distance = sum(abs(color[channel] - background[channel]) for channel in range(3))
            if distance >= 45:
                mask_pixels[x, y] = 255
    mask = mask.filter(ImageFilter.MaxFilter(11)).filter(ImageFilter.MinFilter(11))

    raw = bytearray(mask.tobytes())
    components: list[tuple[int, int, int, int]] = []
    min_area = max(100, int(width * height * 0.008))
    for start in range(width * height):
        if raw[start] == 0:
            continue
        raw[start] = 0
        stack = [start]
        min_x = max_x = start % width
        min_y = max_y = start // width
        area = 0
        while stack:
            index = stack.pop()
            x, y = index % width, index // width
            area += 1
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            if x and raw[index - 1]:
                raw[index - 1] = 0
                stack.append(index - 1)
            if x + 1 < width and raw[index + 1]:
                raw[index + 1] = 0
                stack.append(index + 1)
            if y and raw[index - width]:
                raw[index - width] = 0
                stack.append(index - width)
            if y + 1 < height and raw[index + width]:
                raw[index + width] = 0
                stack.append(index + width)
        box_width = max_x - min_x + 1
        box_height = max_y - min_y + 1
        aspect = box_width / max(box_height, 1)
        if area >= min_area and 1.1 <= aspect <= 2.2:
            components.append((min_x, min_y, max_x + 1, max_y + 1))
    scale_x = original_width / max(width, 1)
    scale_y = original_height / max(height, 1)
    scaled = [
        (
            round(left * scale_x),
            round(top * scale_y),
            round(right * scale_x),
            round(bottom * scale_y),
        )
        for left, top, right, bottom in components
    ]
    return sorted(scaled, key=lambda box: (box[1], box[0]))


def _line_groups(values: list[float], threshold: float) -> list[float]:
    groups: list[list[int]] = []
    current: list[int] = []
    for index, value in enumerate(values):
        if value >= threshold:
            current.append(index)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return [sum(group) / len(group) for group in groups if len(group) >= 1]


def _coverage_runs(values: list[float], threshold: float) -> list[tuple[int, int]]:
    """Return inclusive-exclusive runs above a projection threshold."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value >= threshold and start is None:
            start = index
        elif value < threshold and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(values)))
    return runs


def _extend_row_boxes(
    row_boxes: list[tuple[float, float]],
    *,
    expected_rows: int,
) -> list[tuple[float, float]]:
    if len(row_boxes) >= expected_rows:
        return row_boxes[:expected_rows]
    if len(row_boxes) < 2:
        return []
    top_steps = [row_boxes[i][0] - row_boxes[i - 1][0] for i in range(1, len(row_boxes))]
    row_step = float(statistics.median(top_steps))
    row_height = float(statistics.median(end - start for start, end in row_boxes))
    while len(row_boxes) < expected_rows:
        next_top = row_boxes[-1][0] + row_step
        row_boxes.append((next_top, next_top + row_height))
    return row_boxes


def _projected_grid_boxes(
    image: Image.Image,
    *,
    expected_pages: int,
    columns: int,
) -> list[tuple[int, int, int, int]]:
    """Detect long card borders using row/column foreground projections.

    This fallback handles real collages whose white card backgrounds blend into
    the white canvas, a case where connected components see one large region.
    """
    original_width, original_height = image.size
    probe = image.convert("RGB")
    probe.thumbnail((900, 900))
    width, height = probe.size
    pixels = probe.load()
    border = []
    for x in range(width):
        border.extend((pixels[x, 0], pixels[x, height - 1]))
    for y in range(height):
        border.extend((pixels[0, y], pixels[width - 1, y]))
    background = tuple(int(statistics.median(p[channel] for p in border)) for channel in range(3))

    row_counts = [0] * height
    column_counts = [0] * width
    foreground = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            color = pixels[x, y]
            if sum(abs(color[channel] - background[channel]) for channel in range(3)) >= 30:
                row_counts[y] += 1
                column_counts[x] += 1
                foreground[y * width + x] = 1
    row_coverage = [count / max(width, 1) for count in row_counts]
    column_coverage = [count / max(height, 1) for count in column_counts]

    # Complete horizontal card borders span all three columns and cover roughly
    # 70%+ of the canvas width.  Repeated text/chart lines commonly cover
    # 55-65%; accepting those would split one card row into several false rows.
    # Vertical borders need a lower threshold because the incomplete final row
    # legitimately leaves blank cells.
    expected_rows = math.ceil(expected_pages / max(columns, 1))
    horizontal_runs = _coverage_runs(row_coverage, 0.70)
    vertical_runs = _coverage_runs(column_coverage, 0.55)

    # Solid/dark cards appear as broad projection bands, one per column/row.
    if len(vertical_runs) == columns and 2 <= len(horizontal_runs) <= expected_rows:
        column_boxes = [(float(start), float(end)) for start, end in vertical_runs]
        row_boxes = _extend_row_boxes(
            [(float(start), float(end)) for start, end in horizontal_runs],
            expected_rows=expected_rows,
        )
    else:
        # Light cards blending into the canvas appear as thin paired borders.
        horizontal_lines = _line_groups(row_coverage, 0.70)
        vertical_lines = _line_groups(column_coverage, 0.55)
        if len(vertical_lines) < columns * 2 or len(horizontal_lines) < 4:
            return []
        column_boxes = [
            (vertical_lines[index * 2], vertical_lines[index * 2 + 1])
            for index in range(columns)
        ]
        complete_row_count = len(horizontal_lines) // 2
        row_boxes = _extend_row_boxes(
            [
                (horizontal_lines[index * 2], horizontal_lines[index * 2 + 1])
                for index in range(complete_row_count)
            ],
            expected_rows=expected_rows,
        )
    if len(row_boxes) != expected_rows:
        return []

    boxes: list[tuple[int, int, int, int]] = []
    for index in range(expected_pages):
        row, column = divmod(index, columns)
        left, right = column_boxes[column]
        top, bottom = row_boxes[row]
        candidate = (round(left), round(top), round(right), round(bottom))
        sample_left = max(0, min(width, candidate[0]))
        sample_top = max(0, min(height, candidate[1]))
        sample_right = max(0, min(width, candidate[2]))
        sample_bottom = max(0, min(height, candidate[3]))
        area = (sample_right - sample_left) * (sample_bottom - sample_top)
        if area <= 0:
            return []
        active = sum(
            sum(foreground[y * width + sample_left:y * width + sample_right])
            for y in range(sample_top, sample_bottom)
        )
        # Extrapolated last-row cells must contain real visual evidence.  This
        # distinguishes a 10-page 3+3+3+1 grid from a genuinely 9-page image.
        if active / area < 0.005:
            return []
        boxes.append(candidate)
    scale_x = original_width / max(width, 1)
    scale_y = original_height / max(height, 1)
    return [
        (
            round(left * scale_x),
            round(top * scale_y),
            round(right * scale_x),
            round(bottom * scale_y),
        )
        for left, top, right, bottom in boxes
    ]


def _long_separator_grid_boxes(
    image: Image.Image,
    *,
    expected_pages: int,
    columns: int,
) -> list[tuple[int, int, int, int]]:
    """Segment a grid only when near-full-canvas separators are unambiguous.

    Internal text and chart rules are deliberately ignored: a separator must
    create a strong colour transition across at least 75% of the orthogonal
    canvas dimension. Returning no boxes means "uncertain", not "valid".
    """
    original_width, original_height = image.size
    probe = image.convert("RGB")
    probe.thumbnail((900, 900))
    width, height = probe.size
    pixels = probe.load()

    row_scores = []
    for y in range(1, height):
        changed = sum(
            sum(abs(pixels[x, y][c] - pixels[x, y - 1][c]) for c in range(3)) >= 45
            for x in range(width)
        )
        row_scores.append(changed / max(width, 1))
    column_scores = []
    for x in range(1, width):
        changed = sum(
            sum(abs(pixels[x, y][c] - pixels[x - 1, y][c]) for c in range(3)) >= 45
            for y in range(height)
        )
        column_scores.append(changed / max(height, 1))

    def centers(scores: list[float]) -> list[int]:
        runs = _coverage_runs(scores, 0.75)
        return [round((start + end) / 2) + 1 for start, end in runs]

    expected_rows = math.ceil(expected_pages / max(columns, 1))
    vertical = centers(column_scores)
    horizontal = centers(row_scores)
    # Canvas-edge separators are sometimes clipped away. Internal separators
    # must all be present; outer boundaries safely use the canvas edges.
    vertical = [x for x in vertical if width * 0.05 < x < width * 0.95]
    horizontal = [y for y in horizontal if height * 0.05 < y < height * 0.95]
    if len(vertical) != columns - 1 or len(horizontal) != expected_rows - 1:
        return []
    x_bounds = [0, *vertical, width]
    y_bounds = [0, *horizontal, height]
    boxes = []
    for index in range(expected_pages):
        row, column = divmod(index, columns)
        boxes.append((x_bounds[column], y_bounds[row], x_bounds[column + 1], y_bounds[row + 1]))
    scale_x = original_width / max(width, 1)
    scale_y = original_height / max(height, 1)
    return [
        (round(l * scale_x), round(t * scale_y), round(r * scale_x), round(b * scale_y))
        for l, t, r, b in boxes
    ]


def _hough_grid_boxes(
    image: Image.Image,
    *,
    expected_pages: int,
    columns: int,
) -> list[tuple[int, int, int, int]]:
    """Detect repeated low-contrast long borders with OpenCV Hough lines."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    if expected_pages <= 0 or columns <= 0:
        return []
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    edges = cv2.Canny(gray, 20, 80)
    shortest = min(width, height)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=max(50, shortest // 5),
        minLineLength=int(shortest * 0.55),
        maxLineGap=int(shortest * 0.04),
    )
    if lines is None:
        return []
    horizontal: list[tuple[int, int]] = []
    vertical: list[tuple[int, int]] = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        line_width, line_height = abs(x2 - x1), abs(y2 - y1)
        if line_height <= max(3, round(height * 0.01)) and line_width >= width * 0.65:
            horizontal.append((round((y1 + y2) / 2), line_width))
        if line_width <= max(3, round(width * 0.01)) and line_height >= height * 0.65:
            vertical.append((round((x1 + x2) / 2), line_height))

    def clustered_positions(values: list[tuple[int, int]], dimension: int) -> list[int]:
        tolerance = max(4, round(dimension * 0.02))
        groups: list[list[tuple[int, int]]] = []
        for position, length in sorted(values):
            if groups and abs(position - groups[-1][-1][0]) <= tolerance:
                groups[-1].append((position, length))
            else:
                groups.append([(position, length)])
        centers = [
            round(sum(position * length for position, length in group) / sum(length for _, length in group))
            for group in groups
        ]
        return [position for position in centers if dimension * 0.05 < position < dimension * 0.95]

    expected_rows = math.ceil(expected_pages / columns)
    x_internal = clustered_positions(vertical, width)
    y_internal = clustered_positions(horizontal, height)
    if len(x_internal) != columns - 1 or len(y_internal) != expected_rows - 1:
        return []
    x_bounds = [0, *x_internal, width]
    y_bounds = [0, *y_internal, height]
    column_widths = [x_bounds[i + 1] - x_bounds[i] for i in range(columns)]
    row_heights = [y_bounds[i + 1] - y_bounds[i] for i in range(expected_rows)]
    if any(not width * 0.15 <= value <= width * 0.50 for value in column_widths):
        return []
    if any(not height * 0.12 <= value <= height * 0.45 for value in row_heights):
        return []
    return [
        (x_bounds[column], y_bounds[row], x_bounds[column + 1], y_bounds[row + 1])
        for row, column in (divmod(index, columns) for index in range(expected_pages))
    ]


def detect_collage_grid_boxes(
    image: Image.Image,
    *,
    expected_pages: int,
    columns: int,
) -> list[tuple[int, int, int, int]]:
    """Use the reliable detector for the image's visual treatment."""
    separators = _long_separator_grid_boxes(
        image, expected_pages=expected_pages, columns=columns
    )
    if len(separators) == expected_pages:
        return separators
    hough = _hough_grid_boxes(image, expected_pages=expected_pages, columns=columns)
    if len(hough) == expected_pages:
        return hough
    components = _content_components(image)
    if len(components) == expected_pages:
        return components
    return _projected_grid_boxes(
        image,
        expected_pages=expected_pages,
        columns=columns,
    )


def detect_confident_collage_grid_boxes(
    image: Image.Image,
    *,
    expected_pages: int,
    columns: int,
) -> list[tuple[int, int, int, int]]:
    """Return boxes only when full-canvas grid separators prove the layout."""
    separators = _long_separator_grid_boxes(
        image,
        expected_pages=expected_pages,
        columns=columns,
    )
    if len(separators) == expected_pages:
        return separators
    hough = _hough_grid_boxes(image, expected_pages=expected_pages, columns=columns)
    if len(hough) == expected_pages:
        return hough
    components = _content_components(image)
    if len(components) != expected_pages:
        components = _projected_grid_boxes(
            image, expected_pages=expected_pages, columns=columns,
        )
    if len(components) != expected_pages:
        return []
    widths = [box[2] - box[0] for box in components]
    heights = [box[3] - box[1] for box in components]
    median_width = float(statistics.median(widths))
    median_height = float(statistics.median(heights))
    if any(not 1.2 <= width / max(height, 1) <= 2.5 for width, height in zip(widths, heights)):
        return []
    if any(abs(width - median_width) / max(median_width, 1) > 0.25 for width in widths):
        return []
    if any(abs(height - median_height) / max(median_height, 1) > 0.30 for height in heights):
        return []
    expected_rows = math.ceil(expected_pages / max(columns, 1))
    row_groups = [components[row * columns:min((row + 1) * columns, expected_pages)] for row in range(expected_rows)]
    if any(not group for group in row_groups):
        return []
    # A component grid is safe to crop only when repeated row/column anchors
    # prove the boxes are complete cards rather than internal artwork.
    for group in row_groups:
        tops = [box[1] for box in group]
        if max(tops) - min(tops) > image.height * 0.05:
            return []
    for column in range(columns):
        column_boxes = [components[index] for index in range(column, expected_pages, columns)]
        lefts = [box[0] for box in column_boxes]
        if max(lefts) - min(lefts) > image.width * 0.05:
            return []
    row_tops = [statistics.median(box[1] for box in group) for group in row_groups]
    if any(row_tops[index] <= row_tops[index - 1] for index in range(1, len(row_tops))):
        return []
    return components


def validate_collage_grid(
    path: str,
    *,
    expected_pages: int,
    columns: int,
    spec: dict,
) -> list[str]:
    """Verify detected collage cards have equal dimensions and 16:9 aspect."""
    geometry = spec.get("grid_geometry") or {}
    if not geometry.get("enabled", False):
        return []
    with Image.open(path) as image:
        boxes = detect_collage_grid_boxes(
            image,
            expected_pages=expected_pages,
            columns=columns,
        )
    if len(boxes) != expected_pages:
        message = f"拼图网格分割不确定：期望{expected_pages}个缩略图，检测到{len(boxes)}个"
        if geometry.get("on_detection_failure") == "vision_review":
            # Generated collages may use borderless/full-bleed cards that a
            # deterministic connected-component pass cannot segment.  The
            # mandatory vision review below still checks count/order/size.
            logger.warning("%s；交由视觉语义门禁验收", message)
            return []
        return [message]

    widths = [box[2] - box[0] for box in boxes]
    heights = [box[3] - box[1] for box in boxes]
    median_width = float(statistics.median(widths))
    median_height = float(statistics.median(heights))
    size_tolerance = float(geometry.get("size_tolerance", 0.03))
    aspect_tolerance = float(geometry.get("cell_aspect_tolerance", 0.05))
    target_aspect = float(geometry.get("target_cell_aspect", 16 / 9))
    failures: list[str] = []
    for index, (width, height) in enumerate(zip(widths, heights), 1):
        width_delta = abs(width - median_width) / max(median_width, 1)
        height_delta = abs(height - median_height) / max(median_height, 1)
        if width_delta > size_tolerance:
            failures.append(
                f"第{index}个缩略图宽度不一致：{width}px，中位宽度{median_width:.0f}px，偏差{width_delta:.1%}"
            )
        if height_delta > size_tolerance:
            failures.append(
                f"第{index}个缩略图高度不一致：{height}px，中位高度{median_height:.0f}px，偏差{height_delta:.1%}"
            )
        actual_aspect = width / max(height, 1)
        aspect_delta = abs(actual_aspect - target_aspect) / target_aspect
        if aspect_delta > aspect_tolerance:
            failures.append(
                f"第{index}个缩略图不是16:9：实际比例{actual_aspect:.3f}，偏差{aspect_delta:.1%}"
            )
    if geometry.get("enforcement") == "diagnostic_only" and failures:
        logger.warning("拼图几何诊断发现异常，交由视觉语义门禁验收：%s", "；".join(failures))
        return []
    return failures


def validate_image_file(path: str, interaction_name: str, size: str,
                        context: dict[str, Any] | None = None) -> list[str]:
    context = context or {}
    spec = get_image_spec(interaction_name)
    from app.services.collage_prompt_spec import validate_output
    failures: list[str] = list(validate_output(path))
    output = Path(path)
    if not output.exists():
        return ["模型未生成输出文件"]
    file_size = output.stat().st_size
    if file_size < int(spec.get("min_file_bytes", 10000)):
        failures.append(f"输出文件过小：{file_size} bytes")
    try:
        with Image.open(output) as probe:
            probe.verify()
        with Image.open(output) as image:
            image.load()
            width, height = image.size
            if width < int(spec.get("min_width", 512)) or height < int(spec.get("min_height", 512)):
                failures.append(f"图片分辨率不足：{width}x{height}")
            target = _expected_aspect(size, context)
            actual = width / max(height, 1)
            tolerance = float(spec.get("aspect_tolerance", 0.16))
            if target and abs(actual - target) / target > tolerance:
                failures.append(f"宽高比不符合要求：实际 {actual:.3f}，期望 {target:.3f}")
            stat = ImageStat.Stat(image.convert("L").resize((256, 256)))
            stddev = float(stat.stddev[0])
            if not math.isfinite(stddev) or stddev < float(spec.get("min_luminance_stddev", 8.0)):
                failures.append(f"画面接近空白或缺少有效细节：亮度标准差 {stddev:.2f}")
            if interaction_name == "ppt_collage" and context.get("expected_pages"):
                failures.extend(validate_collage_grid(
                    path,
                    expected_pages=int(context["expected_pages"]),
                    columns=int(context.get("columns") or 3),
                    spec=spec,
                ))
    except Exception as exc:
        failures.append(f"图片无法解码：{exc.__class__.__name__}: {exc}")
    return failures


async def validate_image_semantics(path: str, prompt: str, interaction_name: str,
                                   context: dict[str, Any] | None = None) -> tuple[list[str], dict]:
    spec = get_image_spec(interaction_name)
    if not spec.get("vision_review", True):
        return [], {}
    if interaction_name == "ppt_collage":
        from app.services.tutujin_credentials import get_vision_credential
        try:
            get_vision_credential()
        except Exception as exc:
            return [], {"status": "unavailable", "reason": str(exc)}
    elif not settings.agnes_api_key:
        if spec.get("vision_review_required", True):
            return ["缺少 AGNES_API_KEY，无法执行生成后视觉语义门禁"], {}
        return [], {"skipped": "AGNES_API_KEY not configured"}
    try:
        from app.services.vision_model_service import vision_model_service
        review = await vision_model_service.review_generated_image(
            interaction_name=interaction_name,
            prompt=prompt,
            image_path=path,
            context=context,
        )
    except Exception as exc:
        if interaction_name == "ppt_collage":
            return [], {
                "status": "unavailable",
                "reason": f"Tutujin vision review unavailable: {exc.__class__.__name__}",
            }
        return [f"视觉质量审查失败：{exc.__class__.__name__}: {exc}"], {}
    failures = [str(x) for x in review.get("failures", []) if str(x).strip()]
    score = review.get("score", 0)
    passed = review.get("passed") is True and isinstance(score, (int, float)) and score >= 80 and not failures
    if not passed:
        feedback = str(review.get("feedback") or "视觉审查未通过")
        failures.append(f"视觉审查：score={score}，{feedback}")
    return failures, review


def build_image_retry_prompt(original_prompt: str, interaction_name: str,
                             failures: list[str]) -> str:
    spec = get_image_spec(interaction_name)
    feedback = "\n".join(f"- {item}" for item in failures)
    retry = str(spec.get("retry_template", "{failures}")).format(failures=feedback)
    return f"{original_prompt.rstrip()}\n\n{retry}"
