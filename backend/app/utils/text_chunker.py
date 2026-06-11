"""Semantic text chunker — splits by document structure, not fixed byte count."""

import re

# Default target range (characters, roughly 1 char ≈ 1-2 Chinese tokens).
# The public chunk_text() API can override these with chunk_size/overlap.
TARGET_MIN = 400
TARGET_MAX = 900

# ── Section boundary patterns ──────────────────────────────

# Line-level heading patterns — compiled without MULTILINE, applied per-line
_LINE_HEADING_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r'^(第[一二三四五六七八九十\d]+[章节篇]\s*[^\n]*)'), 1),
    (re.compile(r'^([一二三四五六七八九十]{1,2}、[^\n]+)'), 2),
    (re.compile(r'^(（[一二三四五六七八九十]+）[^\n]*)'), 3),
    (re.compile(r'^(\d+(?:\.\d+)+[\s、.][^\n]+)'), 4),
    (re.compile(r'^(\d+[\.、]\s*[^\n]{5,})'), 5),
    (re.compile(r'^([A-Z一-鿿][A-Za-z一-鿿\s]{2,30})$'), 6),
]


def _detect_section_boundaries(text: str) -> list[tuple[int, str, int]]:
    """Return [(position, heading_text, level), ...] for each detected heading.

    Processes text line-by-line to avoid catastrophic regex backtracking on
    long documents without natural line breaks (e.g. Excel exports).
    """
    boundaries = []
    pos = 0
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped:
            pos += len(line) + 1  # +1 for the \n we split on
            continue

        for pattern, level in _LINE_HEADING_PATTERNS:
            m = pattern.match(stripped)
            if m:
                heading = m.group(1).strip()
                boundaries.append((pos, heading, level))
                break  # first matching pattern wins for this line

        pos += len(line) + 1

    # Deduplicate: if two boundaries are very close, keep the higher-level (lower level number) one
    filtered = []
    for b in boundaries:
        if filtered and abs(b[0] - filtered[-1][0]) < 20:
            if b[2] < filtered[-1][2]:
                filtered[-1] = b
        else:
            filtered.append(b)

    return filtered


def _split_by_sections(text: str) -> list[tuple[str, str]]:
    """Split text into (section_heading, section_content) pairs."""
    boundaries = _detect_section_boundaries(text)

    if not boundaries:
        return [("", text)]

    sections = []
    # Text before first heading
    if boundaries[0][0] > 0:
        preamble = text[:boundaries[0][0]].strip()
        if preamble:
            sections.append(("", preamble))

    for i, (pos, heading, level) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        content = text[pos:end].strip()
        sections.append((heading, content))

    return sections


def _chunk_section(title: str, content: str, chunk_size: int, overlap: int) -> list[str]:
    """Chunk a single document section into appropriately sized pieces."""
    target_max = max(120, chunk_size)
    target_min = max(80, min(TARGET_MIN, int(target_max * 0.65)))

    # If content fits in one chunk, return as-is (prepend title for context)
    if len(content) <= target_max:
        return [content]

    # Split by paragraphs first
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks = []
    current = ""
    for para in paragraphs:
        combined = current + ("\n" + para if current else para)
        if len(combined) <= target_max:
            current = combined
        else:
            # If current is only a heading and the next paragraph is large,
            # split the combined text instead of creating an oversized chunk.
            if current and len(current) < target_min // 2:
                if len(para) > target_max:
                    subs = _split_long_para(combined, chunk_size, overlap)
                    chunks.extend(subs)
                    current = ""
                else:
                    current = combined  # merge up, preferring context over size limit
                continue

            # Current chunk is large enough — save it
            if current:
                chunks.append(current)

            # Start new chunk
            if len(para) > target_max:
                subs = _split_long_para(para, chunk_size, overlap)
                chunks.extend(subs)
                current = ""
            else:
                current = para

    # Don't forget the last chunk
    if current:
        if chunks and len(current) < target_min // 2:
            chunks[-1] = chunks[-1] + "\n" + current
        else:
            chunks.append(current)

    # Apply overlap between consecutive chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            if len(prev) > overlap:
                tail = prev[-overlap:]
                overlapped.append(tail + "\n" + chunks[i])
            else:
                overlapped.append(chunks[i])
        return overlapped

    return chunks


def _split_long_para(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split a very long paragraph at sentence boundaries."""
    target_max = max(120, chunk_size)

    # Split on Chinese/English sentence endings
    sentences = re.split(r'(?<=[。！？.!?])\s*', text)
    if len(sentences) <= 1:
        # No sentence boundaries found, hard split
        result = []
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                result.append(chunk.strip())
        return result

    chunks = []
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        combined = current + (" " + sent if current else sent)
        if len(combined) <= target_max:
            current = combined
        else:
            if current:
                chunks.append(current)
            if len(sent) > target_max:
                # Hard split
                for i in range(0, len(sent), chunk_size - overlap):
                    chunk = sent[i:i + chunk_size].strip()
                    if chunk:
                        chunks.append(chunk)
                current = ""
            else:
                current = sent

    if current:
        chunks.append(current)

    return chunks


# ── Dirty content filter ───────────────────────────────────
# All filtering is done line-by-line to avoid catastrophic regex backtracking
# on long documents (e.g. Excel exports with mixed ASCII/Chinese lines).

# Binary predicate: True = line is garbage and should be removed
def _is_dirty_line(line: str) -> bool:
    """Return True if *line* is low-quality and should be removed."""
    stripped = line.strip()
    if not stripped:
        return False  # keep blank lines as paragraph separators

    # Standalone digits (page numbers, line numbers from exports)
    if re.fullmatch(r'\d{1,4}', stripped):
        return True

    # Repetitive special characters
    if re.fullmatch(r'[_-]{3,}', stripped):
        return True

    # Lines where >70% of characters are ASCII non-alphanumeric
    # (indicates formatting cruft from PDF/text extraction, not real content)
    if len(stripped) >= 10:
        non_alpha = sum(1 for c in stripped if c.isascii() and not c.isalnum() and not c.isspace())
        alpha = sum(1 for c in stripped if c.isalpha() or ('一' <= c <= '鿿'))
        if non_alpha > alpha and non_alpha / len(stripped) > 0.6:
            return True

    return False


def _filter_chunk(chunk: str) -> str:
    """Return empty string if chunk is garbage; otherwise return cleaned chunk."""
    if not chunk or not chunk.strip():
        return ""

    # Remove dirty lines
    lines = chunk.split("\n")
    kept = [l for l in lines if not _is_dirty_line(l)]

    # Check for single-char dominated garbage (from bad PDF extraction)
    if len(kept) >= 4:
        single_char_lines = sum(1 for l in kept if len(l.strip()) <= 1 and l.strip())
        if single_char_lines > len(kept) * 0.5:
            # Try to salvage by merging single chars
            merged_lines = []
            buf = ""
            for l in kept:
                stripped = l.strip()
                if len(stripped) == 1:
                    buf += stripped
                else:
                    if buf:
                        merged_lines.append(buf)
                        buf = ""
                    if stripped:
                        merged_lines.append(stripped)
            if buf:
                merged_lines.append(buf)
            kept = merged_lines

    cleaned = "\n".join(kept).strip()
    if len(cleaned) < 20:
        return ""

    return cleaned


# ── Public API ─────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into semantic chunks based on document structure.

    Returns chunks near chunk_size, preferring section boundaries and
    paragraph breaks over arbitrary cut points.
    """
    if not text or len(text.strip()) < 20:
        return []

    # Step 1: Filter dirty content from the whole text first
    text = _filter_chunk(text)
    if not text:
        return []

    # Step 2: Split by detected section headings
    sections = _split_by_sections(text)

    # Step 3: Chunk each section
    all_chunks = []
    for _title, content in sections:
        section_chunks = _chunk_section(_title, content, chunk_size, overlap)
        all_chunks.extend(section_chunks)

    # Step 4: Merge orphan small chunks and filter
    result = []
    target_min = max(80, min(TARGET_MIN, int(max(120, chunk_size) * 0.65)))
    target_max = max(120, chunk_size)
    for c in all_chunks:
        cleaned = _filter_chunk(c)
        if not cleaned:
            continue
        # Merge with previous if this chunk is too small on its own
        if result and len(cleaned) < target_min // 2:
            merged = result[-1] + "\n" + cleaned
            if len(merged) <= target_max + overlap:
                result[-1] = merged
                continue
        result.append(cleaned)

    return result


# Legacy alias for backward compatibility
chunk_text_semantic = chunk_text
