# -*- coding: utf-8 -*-
"""Re-index the knowledge base with new SiliconFlow embeddings."""
import sys, os
os.chdir(r"D:\数字分身\backend")
sys.path.insert(0, r"D:\数字分身\backend")

import asyncio

async def main():
    from app.services.rag_service import rag_service
    from app.services.file_scanner import file_scanner

    print("Initializing RAG service...")
    await rag_service.initialize()
    print(f"Ready: {rag_service.is_ready}")

    # Scan the knowledge base directory directly
    kb_dir = r"D:\数字分身\本地知识库"
    print(f"\nScanning: {kb_dir}")
    count = await file_scanner.scan_directory(kb_dir)
    print(f"Indexed {count} files")

    stats = await rag_service.get_stats()
    print(f"Stats: {stats}")

    # Quick search test
    result = await rag_service.search("什么是MO流程")
    if result:
        print(f"\nSearch test: {len(result)} chars")
        print(result[:300])
    else:
        print("\nSearch test: no results (knowledge base is empty)")

asyncio.run(main())
