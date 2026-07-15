"""VBA PPTX Reconstruction Service.

Strategy: Generate VBA code that PowerPoint executes natively to create
every element as a proper Office Shape. This avoids ALL python-pptx OOXML issues.

Pipeline:
  1. CV/OCR analysis -> text regions, shapes, colors, positions
  2. LLM generates element manifest (structured JSON)
  3. VBA code generator transforms manifest -> .bas file
  4. User imports .bas into PowerPoint, runs macro -> perfect editable PPTX
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

SLIDE_W = 960   # VBA coordinates (points * 1.333 for standard PPT)
SLIDE_H = 540


async def analyze_and_generate_vba(
    image_path: str,
    session_id: str = "",
    output_dir: str | None = None,
) -> dict | None:
    """Full pipeline: analyze image -> generate VBA code -> save .bas file.

    Returns dict with vba_code, bas_path, element_count, manifest.
    """
    out_dir = Path(output_dir) if output_dir else Path("data/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = session_id[:8] if session_id else uuid.uuid4().hex[:8]

    # Step 1: CV/OCR analysis
    analysis = _run_analysis(image_path)
    if not analysis or not analysis.get("text_regions"):
        logger.warning("No elements detected in image")
        return None

    # Step 2: Generate element manifest via LLM
    manifest = await _generate_manifest(image_path, analysis)
    if not manifest:
        logger.warning("LLM manifest generation failed, using CV-only manifest")
        manifest = _build_cv_manifest(analysis)

    # Step 3: Generate VBA code
    vba_code = generate_vba_code(manifest)

    # Step 4: Save
    bas_name = f"ppt_reconstruct_{sid}.bas"
    bas_path = out_dir / bas_name
    bas_path.write_text(vba_code, encoding="utf-8")

    element_count = len(manifest.get("elements", []))
    logger.info("VBA generated: %d elements -> %s", element_count, bas_name)

    return {
        "vba_code": vba_code,
        "bas_path": str(bas_path),
        "bas_name": bas_name,
        "url": f"http://127.0.0.1:8001/api/skills/download/{bas_name}",
        "element_count": element_count,
        "manifest": manifest,
    }


# ── Step 1: CV/OCR Analysis ─────────────────────────────────────────────

def _run_analysis(image_path: str) -> dict | None:
    """Run CV/OCR on the image to extract text regions, shapes, colors."""
    import cv2
    import numpy as np
    from PIL import Image
    import pytesseract

    tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    img = Image.open(image_path)
    iw, ih = img.size
    buf = np.fromfile(image_path, dtype=np.uint8)
    cv_img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if cv_img is None:
        cv_img = np.array(img.convert("RGB"))[:, :, ::-1]

    # OCR text regions
    from app.services.image_to_pptx import _ocr_text_regions, _detect_lines_and_rects
    sx = SLIDE_W / iw
    sy = SLIDE_H / ih
    text_regions = _ocr_text_regions(img, iw, ih)
    shapes = _detect_lines_and_rects(cv_img, iw, ih, sx, sy)

    # Background color
    h, w = cv_img.shape[:2]
    corners = [cv_img[0:8, 0:8], cv_img[0:8, -8:], cv_img[-8:, 0:8], cv_img[-8:, -8:]]
    bg_avg = np.mean([np.mean(s.reshape(-1, 3), axis=0) for s in corners if s.size > 0], axis=0).astype(int)
    bg_hex = f"{int(bg_avg[2]):02x}{int(bg_avg[1]):02x}{int(bg_avg[0]):02x}"

    return {
        "width": iw, "height": ih,
        "text_regions": text_regions,
        "shapes": [
            {"type": s["type"], "subtype": s.get("subtype", ""),
             "x": s.get("x", s.get("x1", 0)), "y": s.get("y", s.get("y1", 0)),
             "w": s.get("w", s.get("x2", 0) - s.get("x1", 0)),
             "h": s.get("h", s.get("y2", 0) - s.get("y1", 0)),
             "x1": s.get("x1"), "y1": s.get("y1"),
             "x2": s.get("x2"), "y2": s.get("y2"),
             "fill": s.get("fill"), "stroke": s.get("stroke")}
            for s in shapes[:20]
        ],
        "bg_color": bg_hex,
    }


# ── Step 2: LLM Element Manifest ────────────────────────────────────────

MANIFEST_SYSTEM_PROMPT = """You are a precise PowerPoint layout analyst. Output ONLY valid JSON.

Analyze the provided OCR text and CV shape data to create an element manifest for VBA-based PowerPoint reconstruction.

Output format:
{
  "slide": {"width": 960, "height": 540, "bg_color": "#XXXXXX"},
  "elements": [
    {
      "id": "elem_1", "type": "rect|text|line|rounded_rect",
      "x": 100, "y": 50, "w": 300, "h": 80,
      "fill": "#XXXXXX", "stroke": "#XXXXXX", "stroke_width": 1.0,
      "text": "content", "font_size": 18, "font_bold": true,
      "font_color": "#XXXXXX", "align": "left|center|right",
      "z": 1
    }
  ]
}

RULES:
- Use VBA coordinates: x=left, y=top in points, slide is 960x540
- Scale image pixels to points proportionally (image_width/960 ratio)
- For text: use CORRECTED version of OCR text, fix garbled characters
- For lines: use x1,y1,x2,y2 instead of x,y,w,h
- font_size is in points (VBA standard)
- z-order: background=0, images=10, shapes=20, text=30
- Each element MUST have an id
- Output ONLY the JSON"""


async def _generate_manifest(image_path: str, analysis: dict) -> dict | None:
    """Use LLM to generate element manifest from CV/OCR data."""
    from app.services.llm_service import llm_service

    iw, ih = analysis["width"], analysis["height"]
    scale_x = SLIDE_W / iw
    scale_y = SLIDE_H / ih

    # Format text regions for LLM
    text_lines = []
    for i, tr in enumerate(analysis.get("text_regions", [])[:15]):
        vba_x = int(tr["x"] * scale_x)
        vba_y = int(tr["y"] * scale_y)
        vba_w = int(tr["w"] * scale_x)
        vba_h = int(tr["h"] * scale_y)
        fs = int(tr.get("font_size_est", 14))
        role = "title" if tr.get("is_title") else ("footer" if tr.get("is_footer") else "body")
        txt_snippet = tr["text"][:80].replace('"', "'")
        text_lines.append(
            f'{i+1}. [{role}] text="{txt_snippet}" '
            f'pos=({vba_x},{vba_y}) size={vba_w}x{vba_h} font_size~{fs}pt'
        )
    text_data = "\n".join(text_lines) if text_lines else "(no text detected)"

    # Format shapes
    shape_lines = []
    for s in analysis.get("shapes", [])[:15]:
        stype = s.get("type", "?")
        if stype == "line":
            sx1 = int(s.get("x1", 0) * scale_x)
            sy1 = int(s.get("y1", 0) * scale_y)
            sx2 = int(s.get("x2", 0) * scale_x)
            sy2 = int(s.get("y2", 0) * scale_y)
            shape_lines.append(f'  - {stype}({s.get("subtype","")}): ({sx1},{sy1})->({sx2},{sy2})')
        else:
            sx = int(s.get("x", 0) * scale_x)
            sy = int(s.get("y", 0) * scale_y)
            sw = int(s.get("w", 0) * scale_x)
            sh = int(s.get("h", 0) * scale_y)
            shape_lines.append(f'  - {stype}: ({sx},{sy}) {sw}x{sh}')
    shape_data = "\n".join(shape_lines[:20]) if shape_lines else "(no shapes)"

    prompt = f"""Create an element manifest for VBA PowerPoint reconstruction.

## Image: {iw}x{ih} pixels -> VBA slide: {SLIDE_W}x{SLIDE_H} points
## Background color: #{analysis.get('bg_color', 'FFFFFF')}

## Detected Text Regions (positions already converted to VBA points):
{text_data}

## Detected Shapes (positions in VBA points):
{shape_data}

## Instructions:
1. Fix garbled OCR text - use the character patterns to guess the CORRECT Chinese/English text
2. For AI-generated images where text is pseudo-characters, use descriptive placeholders like [Title], [Body]
3. Create a rect element for each card/panel/background area
4. Create a line element for each divider/separator
5. Each text region becomes a text element
6. Assign proper font_size, bold, alignment, and z-order
7. Output ONLY the JSON manifest"""

    try:
        resp = await llm_service.chat(
            system_prompt=MANIFEST_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096, temperature=0.2, timeout=30,
        )
        text = ""
        if resp.content:
            for block in resp.content:
                if hasattr(block, "text"): text += block.text
        text = text.strip()
        # Extract JSON
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        logger.warning("LLM manifest failed: %s", e)

    return None


def _build_cv_manifest(analysis: dict) -> dict:
    """Fallback: build manifest directly from CV/OCR data (no LLM)."""
    iw, ih = analysis["width"], analysis["height"]
    scale_x = SLIDE_W / iw
    scale_y = SLIDE_H / ih

    elements = []

    # Background
    elements.append({
        "id": "bg", "type": "rect", "x": 0, "y": 0, "w": SLIDE_W, "h": SLIDE_H,
        "fill": f"#{analysis.get('bg_color', 'FFFFFF')}", "stroke": "none",
        "stroke_width": 0, "z": 0,
    })

    # Shapes
    for i, s in enumerate(analysis.get("shapes", [])[:15]):
        if s["type"] == "line":
            elements.append({
                "id": f"line_{i}", "type": "line", "z": 10,
                "x1": int(s.get("x1", 0) * scale_x), "y1": int(s.get("y1", 0) * scale_y),
                "x2": int(s.get("x2", 0) * scale_x), "y2": int(s.get("y2", 0) * scale_y),
                "stroke": "#999999", "stroke_width": 1.0,
            })
        else:
            elements.append({
                "id": f"rect_{i}", "type": "rect", "z": 10,
                "x": int(s.get("x", 0) * scale_x), "y": int(s.get("y", 0) * scale_y),
                "w": int(s.get("w", 0) * scale_x), "h": int(s.get("h", 0) * scale_y),
                "fill": _rgb_to_hex(s.get("fill")),
                "stroke": _rgb_to_hex(s.get("stroke")), "stroke_width": 0.5,
            })

    # Text regions
    for i, tr in enumerate(analysis.get("text_regions", [])):
        vba_x = int(tr["x"] * scale_x)
        vba_y = int(tr["y"] * scale_y)
        vba_w = int(tr["w"] * scale_x)
        vba_h = int(tr["h"] * scale_y)
        fs = int(tr.get("font_size_est", 14))
        is_title = tr.get("is_title", False)

        placeholder = "[Title]" if is_title else "[Click to edit]"
        if tr.get("is_footer"): placeholder = "[Footer]"
        elif fs > 20: placeholder = "[Subtitle]"

        elements.append({
            "id": f"text_{i}", "type": "text", "z": 20,
            "x": vba_x, "y": vba_y, "w": vba_w, "h": vba_h,
            "text": placeholder, "font_size": max(10, fs),
            "font_bold": is_title or fs > 22,
            "font_color": "#333333", "align": "left",
        })

    return {
        "slide": {"width": SLIDE_W, "height": SLIDE_H,
                  "bg_color": f"#{analysis.get('bg_color', 'FFFFFF')}"},
        "elements": elements,
    }


def _rgb_to_hex(rgb) -> str:
    if not rgb or not isinstance(rgb, (tuple, list)) or len(rgb) < 3:
        return "#FFFFFF"
    return f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"


# ── Step 3: VBA Code Generator ──────────────────────────────────────────

def generate_vba_code(manifest: dict) -> str:
    """Generate VBA code from element manifest.

    The VBA creates every element as a native PowerPoint shape.
    User imports this .bas into PowerPoint and runs the macro.
    """
    slide = manifest.get("slide", {})
    bg_color = slide.get("bg_color", "#FFFFFF").lstrip("#")
    if len(bg_color) == 3:
        bg_color = "".join(c * 2 for c in bg_color)
    r, g, b = int(bg_color[0:2], 16), int(bg_color[2:4], 16), int(bg_color[4:6], 16)

    elements = manifest.get("elements", [])
    elements.sort(key=lambda e: e.get("z", 0))

    lines = []
    lines.append("' PowerPoint Slide Reconstruction Macro")
    lines.append("' Generated by Digital Twin - VBA PPTX Service")
    lines.append("' Usage: Open PowerPoint -> Alt+F11 -> Import this file -> Run ReconstructSlide")
    lines.append("")
    lines.append("Option Explicit")
    lines.append("")
    lines.append("Public Sub ReconstructSlide()")
    lines.append("    Dim sld As Slide")
    lines.append("    Dim shp As Shape")
    lines.append("    Dim tf As TextFrame")
    lines.append("")
    lines.append("    ' Get or create slide")
    lines.append("    On Error Resume Next")
    lines.append("    Set sld = ActivePresentation.Slides(1)")
    lines.append("    On Error GoTo 0")
    lines.append("    If sld Is Nothing Then")
    lines.append("        Set sld = ActivePresentation.Slides.Add(1, ppLayoutBlank)")
    lines.append("    End If")
    lines.append("")
    lines.append("    ' Delete existing shapes")
    lines.append("    Dim i As Long")
    lines.append("    For i = sld.Shapes.Count To 1 Step -1")
    lines.append("        sld.Shapes(i).Delete")
    lines.append("    Next i")
    lines.append("")
    lines.append(f"    ' Slide dimensions: {SLIDE_W}x{SLIDE_H} points")
    lines.append(f"    sld.FollowMasterBackground = msoFalse")
    lines.append(f"    sld.Background.Fill.ForeColor.RGB = RGB({r}, {g}, {b})")
    lines.append("")

    for i, el in enumerate(elements):
        el_type = el.get("type", "rect")
        el_id = el.get("id", f"elem_{i}")

        try:
            if el_type == "rect" or el_type == "rounded_rect":
                code = _vba_add_rect(el, el_id)
            elif el_type == "line":
                code = _vba_add_line(el, el_id)
            elif el_type == "text":
                code = _vba_add_text(el, el_id)
            else:
                continue
            lines.append(code)
            lines.append("")
        except Exception as e:
            lines.append(f"    ' ERROR on {el_id}: {e}")
            lines.append("")

    lines.append("    ' Done - all elements created as editable shapes")
    lines.append(f"    MsgBox \"Reconstruction complete! {len(elements)} elements created.\", vbInformation")
    lines.append("End Sub")

    return "\n".join(lines)


def _vba_add_rect(el: dict, el_id: str) -> str:
    """Generate VBA for a rectangle shape."""
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w, h = int(el.get("w", 100)), int(el.get("h", 50))
    shape_type = "msoShapeRoundedRectangle" if el.get("type") == "rounded_rect" else "msoShapeRectangle"

    fill = el.get("fill", "#FFFFFF").lstrip("#")
    stroke = el.get("stroke", "none")
    sw = el.get("stroke_width", 0.5)

    code = [
        f"    ' {el_id}: Rectangle",
        f"    Set shp = sld.Shapes.AddShape({shape_type}, {x}, {y}, {w}, {h})",
        f"    shp.Name = \"{el_id}\"",
    ]
    if fill and fill != "none":
        fc = _hex_to_rgb(fill)
        code.append(f"    shp.Fill.ForeColor.RGB = RGB({fc[0]}, {fc[1]}, {fc[2]})")
    else:
        code.append("    shp.Fill.Visible = msoFalse")
    if stroke and stroke != "none":
        sc = _hex_to_rgb(stroke)
        code.append(f"    shp.Line.ForeColor.RGB = RGB({sc[0]}, {sc[1]}, {sc[2]})")
        code.append(f"    shp.Line.Weight = {sw}")
    else:
        code.append("    shp.Line.Visible = msoFalse")
    return "\n".join(code)


def _vba_add_line(el: dict, el_id: str) -> str:
    """Generate VBA for a line/connector."""
    x1, y1 = int(el.get("x1", 0)), int(el.get("y1", 0))
    x2, y2 = int(el.get("x2", 100)), int(el.get("y2", 0))
    stroke = el.get("stroke", "#999999").lstrip("#")
    sw = el.get("stroke_width", 1.0)

    code = [
        f"    ' {el_id}: Line",
        f"    Set shp = sld.Shapes.AddConnector(msoConnectorStraight, {x1}, {y1}, {x2}, {y2})",
        f"    shp.Name = \"{el_id}\"",
    ]
    sc = _hex_to_rgb(stroke)
    code.append(f"    shp.Line.ForeColor.RGB = RGB({sc[0]}, {sc[1]}, {sc[2]})")
    code.append(f"    shp.Line.Weight = {sw}")
    return "\n".join(code)


def _vba_add_text(el: dict, el_id: str) -> str:
    """Generate VBA for a text box."""
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w, h = int(el.get("w", 200)), int(el.get("h", 40))
    text = str(el.get("text", "[Edit]")).replace('"', '""')

    fs = int(el.get("font_size", 14))
    bold = el.get("font_bold", False)
    fc = _hex_to_rgb(el.get("font_color", "#333333").lstrip("#"))
    align_map = {"left": 1, "center": 2, "right": 3}
    align = align_map.get(el.get("align", "left"), 1)

    code = [
        f"    ' {el_id}: Text Box",
        f"    Set shp = sld.Shapes.AddTextbox(msoTextOrientationHorizontal, {x}, {y}, {w}, {h})",
        f"    shp.Name = \"{el_id}\"",
        f"    shp.Fill.Visible = msoFalse",
        f"    shp.Line.Visible = msoFalse",
        f"    Set tf = shp.TextFrame",
        f"    tf.WordWrap = msoTrue",
        f"    tf.AutoSize = ppAutoSizeNone",
        f"    tf.TextRange.Text = \"{text}\"",
        f"    tf.TextRange.Font.Size = {fs}",
        f"    tf.TextRange.Font.Color.RGB = RGB({fc[0]}, {fc[1]}, {fc[2]})",
        f"    tf.TextRange.Font.Bold = mso{'True' if bold else 'False'}",
        f"    tf.TextRange.ParagraphFormat.Alignment = {align}",
    ]
    return "\n".join(code)


def _hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex to (r, g, b) tuple."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
