# -*- coding: utf-8 -*-
"""Quick test: SiliconFlow embedding API + RAG service initialization."""
import sys
sys.path.insert(0, r"D:\数字分身\backend")

import asyncio

async def main():
    # Test 1: Direct API call
    print("=== Test 1: Direct SiliconFlow API call ===")
    from app.services.rag_service import SiliconFlowEmbedding
    from app.config import settings

    emb = SiliconFlowEmbedding(
        api_key=settings.siliconflow_api_key,
        base_url=settings.siliconflow_embedding_base_url,
        model=settings.embedding_model,
    )
    result = emb.encode(["你好世界", "MO流程是什么"])
    print(f"  Embeddings returned: {len(result)}")
    print(f"  Dims: {len(result[0])}")
    print(f"  First 5 values: {result[0][:5]}")
    print(f"  OK!")

    # Test 2: RAG service init
    print("\n=== Test 2: RAG service initialization ===")
    from app.services.rag_service import rag_service

    await rag_service.initialize()
    stats = await rag_service.get_stats()
    print(f"  Stats: {stats}")
    print(f"  Ready: {rag_service.is_ready}")

    # Test 3: Quick search (may return empty if no data indexed)
    if rag_service.is_ready:
        print("\n=== Test 3: Search ===")
        result = await rag_service.search("MO流程")
        print(f"  Search result length: {len(result)} chars")
        if result:
            print(f"  Preview: {result[:200]}...")
        else:
            print("  (No results — knowledge base may be empty after model switch)")

    print("\nAll tests passed!")

asyncio.run(main())
