"""SVG Slide Generator — creates editable vector slides from PPT outlines.

Generates professional 16:9 SVG slides with fully editable text elements.
Each slide is a standalone SVG file with clean, semantic structure.

Also supports Draw.io (MX) format for diagram-style output.
"""
from __future__ import annotations

import logging
import os
import uuid

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

SVG_PROMPT = """You are a professional presentation designer. Create a SINGLE 16:9 SVG slide.

## Slide Content
Title: {title}
Content: {content}
Page {page_num} of {total_pages}

## SVG Requirements
1. ViewBox: "0 0 1920 1080" (16:9 ratio, use these exact dimensions)
2. Include a root <svg> element with xmlns="http://www.w3.org/2000/svg"
3. Use <rect> for backgrounds and layout sections
4. Use <text> elements for ALL text content — every word must be editable
5. Use <line>, <circle>, <rect>, <path> for simple graphics
6. Clean modern design: subtle gradients, professional color palette
7. Font family: "PingFang SC, Microsoft YaHei, sans-serif"
8. NO external images, NO base64 data URIs
9. All text must be REAL <text> elements with proper x, y, font-size, fill attributes
10. Well-organized with <!-- comments --> for each section

## Design Style
{style}

## Color Palette
{colors}

Output ONLY the SVG code. No explanations, no markdown code blocks."""




class SVGSlideService:
    """Generates editable vector slides from outlines."""

    async def generate_svg_slides(
        self,
        outline: str,
        slides: list[dict],
        style: str = "professional",
    ) -> list[dict]:
        """Generate SVG files for each slide in the outline."""
        results = []
        total = len(slides)
        colors = self._color_palette(style)

        for slide in slides:
            idx = slide.get("index", len(results) + 1)
            title = slide.get("title", f"Slide {idx}")
            content = slide.get("content", "")[:3000]

            prompt = SVG_PROMPT.format(
                title=title,
                content=content,
                page_num=idx,
                total_pages=total,
                style=self._style_text(style),
                colors=colors,
            )

            try:
                resp = await llm_service.chat(
                    interaction_name="svg_generation",
                    system_prompt="You are an SVG expert. Output ONLY valid SVG code. No markdown, no explanations.",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                    temperature=0.3,
                    thinking={"type": "disabled"},
                )
                svg_code = self._extract(resp)
                # Clean: remove markdown code fences if present
                if svg_code.startswith("```"):
                    svg_code = svg_code.split("\n", 1)[1] if "\n" in svg_code else svg_code[3:]
                if svg_code.endswith("```"):
                    svg_code = svg_code[:-3]
                svg_code = svg_code.strip()

                if svg_code.startswith("<svg"):
                    out_dir = os.path.abspath(os.path.join("data", "outputs"))
                    os.makedirs(out_dir, exist_ok=True)
                    fname = f"slide_{idx:02d}_{uuid.uuid4().hex[:6]}.svg"
                    fpath = os.path.join(out_dir, fname)
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(svg_code)
                    results.append({
                        "index": idx,
                        "title": title,
                        "filename": fname,
                        "path": fpath,
                        "url": f"http://127.0.0.1:8001/api/skills/download/{fname}",
                    })
                else:
                    logger.warning("SVG gen for slide %d returned non-SVG content", idx)
            except Exception as exc:
                logger.warning("SVG gen failed for slide %d: %s", idx, exc)

        return results

    async def generate_drawio(
        self, outline: str, slides: list[dict], session_id: str = ""
    ) -> dict | None:
        """Generate a multi-page Draw.io file — builds XML directly, no LLM."""
        out_dir = os.path.abspath(os.path.join("data", "outputs"))
        os.makedirs(out_dir, exist_ok=True)

        pages_xml = []
        for page_idx, slide in enumerate(slides):
            title = slide.get("title", f"Slide {page_idx+1}")
            content = slide.get("content", "")[:3000]

            # Build cells manually — reliable, no duplicate IDs
            cells = []
            cell_id = 2
            # Title box
            cells.append(
                f'<mxCell id="{cell_id}" value="{self._escape_xml(title[:80])}" '
                f'style="rounded=1;whiteSpace=wrap;html=1;fillColor=#1a365d;fontColor=#ffffff;fontSize=22;fontStyle=1;align=center;" '
                f'vertex="1" parent="1"><mxGeometry x="40" y="40" width="1100" height="60" as="geometry"/></mxCell>'
            )
            cell_id += 1

            # Content lines → individual text boxes
            lines = content.split("\n")
            y_pos = 130
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    # Section header
                    cells.append(
                        f'<mxCell id="{cell_id}" value="{self._escape_xml(line.lstrip("#").strip()[:120])}" '
                        f'style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ebf8ff;fontColor=#2b6cb0;fontSize=16;fontStyle=1;" '
                        f'vertex="1" parent="1"><mxGeometry x="40" y="{y_pos}" width="1100" height="40" as="geometry"/></mxCell>'
                    )
                    y_pos += 52
                elif line.startswith("-") or line.startswith("*"):
                    # Bullet point
                    cells.append(
                        f'<mxCell id="{cell_id}" value="{self._escape_xml(line.lstrip("-*").strip()[:200])}" '
                        f'style="rounded=0;whiteSpace=wrap;html=1;fillColor=#f7fafc;fontColor=#2d3748;fontSize=13;align=left;" '
                        f'vertex="1" parent="1"><mxGeometry x="70" y="{y_pos}" width="1050" height="36" as="geometry"/></mxCell>'
                    )
                    y_pos += 42
                else:
                    # Regular text
                    cells.append(
                        f'<mxCell id="{cell_id}" value="{self._escape_xml(line[:200])}" '
                        f'style="rounded=0;whiteSpace=wrap;html=1;fillColor=none;fontColor=#4a5568;fontSize=13;align=left;" '
                        f'vertex="1" parent="1"><mxGeometry x="40" y="{y_pos}" width="1100" height="36" as="geometry"/></mxCell>'
                    )
                    y_pos += 42
                cell_id += 1
                if y_pos > 1000:
                    break  # Max page height

            pages_xml.append(
                f'<diagram id="page-{page_idx}" name="{self._escape_xml(title[:50])}">'
                f'<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                + "\n".join(cells) +
                "</root></mxGraphModel></diagram>"
            )

        drawio_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<mxfile host="DigitalTwin" modified="2024-01-01T00:00:00.000Z" agent="PPT Maker" version="21.0.0">\n'
            + "\n".join(pages_xml) +
            "\n</mxfile>"
        )

        fname = f"ppt_drawio_{session_id[:8] if session_id else 'output'}.drawio"
        fpath = os.path.join(out_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(drawio_xml)

        return {
            "filename": fname,
            "path": fpath,
            "url": f"http://127.0.0.1:8001/api/skills/download/{fname}",
            "pages": len(slides),
        }

    @staticmethod
    def _escape_xml(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def _color_palette(self, style: str) -> str:
        palettes = {
            "professional": "Primary: #1a365d, Accent: #3182ce, Background: #f7fafc, Text: #2d3748, Light: #edf2f7",
            "modern": "Primary: #0f172a, Accent: #6366f1, Background: #ffffff, Text: #334155, Light: #f1f5f9",
            "warm": "Primary: #744210, Accent: #dd6b20, Background: #fffff0, Text: #2d3748, Light: #fefcbf",
            "dark": "Primary: #e2e8f0, Accent: #63b3ed, Background: #1a202c, Text: #e2e8f0, Light: #2d3748",
        }
        return palettes.get(style, palettes["professional"])

    def _style_text(self, style: str) -> str:
        styles = {
            "professional": "Clean corporate consulting style. Subtle gradients, precise spacing, professional typography hierarchy.",
            "modern": "Minimal modern design. Bold typography, generous whitespace, strong contrast, accent color highlights.",
            "warm": "Warm, approachable style. Soft colors, rounded corners, friendly typography.",
            "dark": "Dark mode presentation. Deep backgrounds, luminous accents, high contrast text.",
        }
        return styles.get(style, styles["professional"])

    @staticmethod
    def _extract(response) -> str:
        text = ""
        if response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
        return text.strip()


svg_slide_service = SVGSlideService()
