# -*- coding: utf-8 -*-
"""Quick re-index of knowledge base — runs in foreground."""
import sys, os
os.chdir(r"D:\数字分身\backend")
sys.path.insert(0, r"D:\数字分身\backend")

import asyncio

async def main():
    from app.services.rag_service import rag_service
    from app.services.file_scanner import file_scanner

    await rag_service.initialize()
    print(f"RAG ready: {rag_service.is_ready}")

    kb_dir = r"D:\数字分身\本地知识库"
    print(f"Scanning: {kb_dir}")
    count = await file_scanner.scan_directory(kb_dir)
    print(f"Indexed {count} files")

    stats = await rag_service.get_stats()
    print(f"Stats: {stats}")

    # Search test
    result = await rag_service.search("MO流程是什么")
    if result:
        print(f"Search OK: {len(result)} chars")
        print(result[:300])
    else:
        print("No search results")

asyncio.run(main())
