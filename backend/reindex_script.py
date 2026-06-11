"""Delete old ChromaDB index and re-scan all files with Markdown cleaning."""
import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio
import os
from app.services.rag_service import rag_service
from app.services.file_scanner import file_scanner

async def main():
    await rag_service.initialize()
    if not rag_service.is_ready:
        print("RAG not ready")
        return

    # Delete all existing data
    print(f"Old collection count: {rag_service._collection.count()}")
    try:
        rag_service._client.delete_collection("knowledge_base")
        rag_service._collection = rag_service._client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )
        print("Collection deleted and recreated")
    except Exception as e:
        print(f"Delete error: {e}")

    # Re-scan
    file_scanner.watch_dirs = [os.path.abspath(r'D:\数字分身\本地知识库')]
    file_scanner._known_files.clear()
    result = await file_scanner.full_scan()
    print(f"Scan result: {result}")
    stats = await rag_service.get_stats()
    print(f"New stats: {stats}")

asyncio.run(main())
