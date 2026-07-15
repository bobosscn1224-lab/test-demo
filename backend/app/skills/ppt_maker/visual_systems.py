"""PPT Maker — visual system descriptions for image generation prompts.

Each system defines the complete visual spec: background, fonts, colors, charts,
icons, cards, margins, whitespace, footer, and page density for a given style.
"""


def style_text_for_choice(choice: str) -> str:
    """One-line style description for each visual direction."""
    styles = {
        "A": "premium strategy consulting report, bright background, precise grid, restrained accent colors",
        "B": "advanced technology keynote, deep clean background, luminous data accents, high-end AI atmosphere",
        "C": "refined editorial business deck, sophisticated image use, generous whitespace, elegant information blocks",
        "REF": "user-provided collage master — faithfully replicate the exact visual style, layout, color palette, and text hierarchy shown in the uploaded reference collage",
    }
    return styles.get(choice, styles["A"])


def build_visual_system(choice: str) -> str:
    """Build a detailed visual system specification for the given choice."""
    systems = {
        "REF": _REF_SYSTEM,
        "A": _SYSTEM_A,
        "B": _SYSTEM_B,
        "C": _SYSTEM_C,
    }
    return systems.get(choice, _SYSTEM_A)


_REF_SYSTEM = """The user has uploaded a collage as the definitive visual master. Replicate every aspect of the collage's visual system exactly as it appears:
Background: exactly match the collage's background style, color, and any textures or gradients present.
Font system: exactly match the collage's font hierarchy, sizes, weights, and colors for titles, subtitles, body text, and data callouts.
Color palette: exactly match the collage's color scheme — primary, secondary, accent colors, and their usage across elements.
Charts: exactly match the collage's chart style — type, color, line weight, grid presence, data label position, and legend placement.
Icons: exactly match the collage's icon style — geometric vs. organic, line weight, filled vs. outlined, color treatment.
Cards/modules: exactly match the collage's card border style, fill opacity, corner radius, internal padding, and shadow if present.
Margins: exactly match the collage's page margins and content area boundaries.
Whitespace: exactly match the collage's spacing rhythm between elements and sections.
Footer: exactly match the collage's footer treatment — separator line, page number position/style, any section labels.
Page density: exactly match the collage's information density — number of content blocks per page, visual weight distribution.
CRITICAL: Do NOT apply any preset style. The uploaded collage IS the only style reference."""

_SYSTEM_A = """Background: clean white to very light warm gray (#F8F7F4 to #FFFFFF). No gradients on standard pages.
Font system: modern sans-serif (similar to Inter/Source Han Sans). Title 28-32px bold, dark charcoal (#1A1A1A). Section headings 14-16px medium, muted gray (#4A4A4A). Body text 10-12px regular (#333333). Key numbers in 36-48px display weight with indigo accent (#3B5998).
Color palette: primary indigo/blue (#3B5998), secondary warm gray (#9E9E9E), accent coral (#E8734A) used sparingly for emphasis.
Charts: flat design, thin gray gridlines (0.5px #E0E0E0), consistent 10px axis labels, data labels placed directly on chart elements. Bar charts with rounded tops (2px radius). Line charts with 2px stroke weight.
Icons: simple geometric line icons, 1.5-2px consistent stroke, grayscale (#666666) or matching indigo accent.
Cards/modules: 1px #E8E8E8 borders, optional 2-3% gray fill (#F5F5F5), 6px border radius, 16px internal padding.
Margins: 60px left/right, 50px top, 70px bottom (for page number zone).
Whitespace: 20-28px gap between modules, clear visual grouping by proximity.
Footer: thin 1px #E0E0E0 separator line at bottom, page number right-aligned 9px #999999, optional section label left-aligned.
Page density: medium — 1 clear focal point per page, 3-5 content blocks maximum."""

_SYSTEM_B = """Background: deep dark base (#0D1117 to #161B22), subtle grid or dot pattern overlay at 3-5% opacity.
Font system: geometric sans-serif (similar to SF Pro Display/DIN). Title 30-38px bold, white (#FFFFFF) or electric blue (#58A6FF). Section labels 12-14px uppercase letter-spacing 2px, cyan accent (#39D2C0). Body 10-11px light gray (#C9D1D9). Key metrics in 40-56px bold display, gradient from cyan to electric blue.
Color palette: deep background (#0D1117), primary electric blue (#58A6FF), accent cyan (#39D2C0), data highlight amber (#F0883E), subtle purple for secondary data (#BC8CFF).
Charts: dark surface with luminous data elements. Bar charts with subtle inner glow. Line charts with 2px stroke + subtle outer glow (matching data color). Grid lines at 8% white opacity. Data labels in white 10px.
Icons: thin luminous line icons (1.5px stroke), cyan or electric blue (#58A6FF), subtle glow effect.
Cards/modules: semi-transparent panels (8-15% white overlay) on dark background, 1px border at 15-20% white, 10px border radius, 20px padding.
Margins: 55px left/right, 45px top, 65px bottom.
Whitespace: 24-32px between modules, dramatic negative space on dark background.
Footer: minimal footer, thin gradient separator line (cyan to transparent), page number in cyan 9px, subtle glow.
Page density: medium-high — data-rich but clean, strong visual hierarchy, 4-6 blocks per page."""

_SYSTEM_C = """Background: warm off-white or very light cream (#FAF9F6), occasional subtle paper texture at 2% opacity for depth.
Font system: refined serif for titles (similar to Source Han Serif/Noto Serif CJK), modern sans-serif for body. Title 24-28px regular weight, deep brown (#2C2416). Section labels 11-13px with 3px letter-spacing, warm taupe (#8B7D6B). Body 10-12px with 1.6x line height, warm charcoal (#3D3226). Numbers in 32-40px light weight.
Color palette: warm neutral base (#FAF9F6), deep brown/charcoal (#2C2416), warm taupe (#8B7D6B), accent muted burgundy (#8B3A3A) or deep olive (#4A6741), occasional gold accent (#C4A747) for highlights.
Charts: refined minimal style, very thin lines (0.5-1px), muted color differentiation (2-3 analogous warm tones), integrated serif typography in labels, minimal to no grid lines.
Icons: delicate thin line icons (1-1.5px stroke), warm taupe (#8B7D6B) or matching the neutral palette.
Cards/modules: very subtle — thin rules (0.5px #D9D3C9), occasional 2-3% warm gray fill, 12-16px border radius, 20-24px padding.
Margins: generous 72-80px left/right, 60px top, 80px bottom.
Whitespace: abundance — the defining characteristic. 32-48px between sections. Each element has breathing room.
Footer: nearly invisible, page number in very light warm gray (#C4BDB2) 8px, minimal or no separator line.
Page density: low to medium — one clear statement per page, maximum 3 content blocks, surrounded by generous space."""


def detect_page_layout(content: str) -> str:
    """Detect likely page layout type from content structure for better imagegen prompts."""
    content_lower = content.lower()
    if any(kw in content_lower for kw in ["封面", "title", "标题页", "cover"]):
        return "COVER slide: centered title with subtitle, minimal content, large title text, company/date line at bottom."
    if any(kw in content_lower for kw in ["目录", "agenda", "目录页", "contents"]):
        return "AGENDA/TOC slide: numbered list of sections, possibly with brief descriptions. Clean list format."
    if any(kw in content_lower for kw in ["图表", "chart", "graph", "数据", "趋势", "对比", "占比", "%"]):
        return "DATA/CHART slide: chart or graph as dominant visual element, with supporting title and 2-3 key insight callouts."
    if any(kw in content_lower for kw in ["对比", "比较", "vs", "方案", "优劣"]):
        return "COMPARISON slide: two-column or multi-column layout comparing options/scenarios."
    if any(kw in content_lower for kw in ["流程", "步骤", "阶段", "process", "step", "timeline", "时间线"]):
        return "PROCESS/TIMELINE slide: horizontal or vertical flow showing sequential steps or phases."
    if any(kw in content_lower for kw in ["总结", "下一步", "感谢", "谢谢", "thank", "summary", "conclusion"]):
        return "SUMMARY/CLOSING slide: key takeaways or call to action. Clean and impactful."
    if any(kw in content_lower for kw in ["概述", "背景", "目标", "现状"]):
        return "OVERVIEW slide: title + 2-4 text blocks or cards introducing a topic."
    return "CONTENT slide: standard business slide with title, 2-4 key points, possible supporting visual."
