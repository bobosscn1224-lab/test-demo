# -*- coding: utf-8 -*-
"""Standalone re-index — text-only, content-deduped, skips duplicates."""
import sys, os, time, hashlib, traceback
os.chdir(r"D:\数字分身\backend")
sys.path.insert(0, r"D:\数字分身\backend")

import asyncio
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

async def main():
    from app.services.rag_service import RAGService
    from app.utils.file_parser import SUPPORTED_EXTENSIONS, parse_file_sync

    rag = RAGService()
    await rag.initialize()
    print(f"RAG ready: {rag.is_ready}", flush=True)

    kb_dir = r"D:\数字分身\本地知识库"
    EXCLUDED = {"Backup0928", "BACKUP1225", "backup", "BACKUP"}

    # Collect all files first
    all_files = []
    for root, dirs, files in os.walk(kb_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED]
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            if filename.startswith("~$"):
                continue
            all_files.append(os.path.join(root, filename))

    total = len(all_files)
    print(f"Found {total} files in non-excluded dirs", flush=True)

    # Dedup by content hash — skip files with identical content
    seen_hashes = set()
    indexed = 0
    skipped_dup = 0
    errors = 0

    for i, file_path in enumerate(all_files, 1):
        filename = os.path.basename(file_path)
        try:
            # Compute content hash first to detect duplicates
            with open(file_path, "rb") as f:
                content_hash = hashlib.md5(f.read()).hexdigest()

            if content_hash in seen_hashes:
                skipped_dup += 1
                print(f"  [{i}/{total}] DUP: {filename} (same content as another file)", flush=True)
                continue
            seen_hashes.add(content_hash)

            text = parse_file_sync(file_path)
            if not text:
                print(f"  [{i}/{total}] SKIP: {filename} (no text)", flush=True)
                errors += 1
                continue

            doc_id = hashlib.md5(file_path.encode()).hexdigest()[:12]
            meta = {
                "source": filename,
                "file_path": file_path,
                "doc_id": doc_id,
            }
            chunk_ids = await rag.index_text(text, meta)
            if chunk_ids:
                indexed += 1
                print(f"  [{i}/{total}] OK: {filename} ({len(chunk_ids)} chunks)", flush=True)
            else:
                errors += 1
                print(f"  [{i}/{total}] SKIP: {filename} (index returned empty)", flush=True)
        except Exception as e:
            errors += 1
            print(f"  [{i}/{total}] FAIL: {filename}: {e}", flush=True)
            traceback.print_exc()

    stats = await rag.get_stats()
    print(f"\nDone. Files: {total}, Indexed: {indexed}, Skipped(dup): {skipped_dup}, Errors: {errors}", flush=True)
    print(f"Stats: {stats}", flush=True)

    result = await rag.search("什么是MO流程")
    if result:
        print(f"Search OK: {len(result)} chars", flush=True)
        print(result[:500], flush=True)
    else:
        print("Search: no results", flush=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"FATAL: {e}", flush=True)
        traceback.print_exc()
