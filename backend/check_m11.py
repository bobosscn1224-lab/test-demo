"""Check if M11.1 is properly indexed."""
import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio, os
from app.services.rag_service import rag_service, _make_doc_id

async def main():
    await rag_service.initialize()

    paths = [
        r'D:\数字分身\本地知识库\M11.1 验证商机流程说明文件-V1.0.pdf',
        r'D:\数字分身\本地知识库\MO流程\M11.1 验证商机流程说明文件-V1.0.pdf',
    ]
    for p in paths:
        if os.path.exists(p):
            doc_id = _make_doc_id(p)
            all_data = rag_service._collection.get(include=["metadatas"])
            found = sum(1 for m in all_data.get("metadatas", []) if m and m.get("doc_id") == doc_id)
            print(f"Path: {os.path.basename(p)} exists, doc_id={doc_id}, chunks={found}")

    print("\nTop search results for 'MO流程的L2PO是谁':")
    results = await rag_service.search_raw("MO流程的L2PO是谁", top_k=5)
    for i, r in enumerate(results):
        src = r["metadata"].get("source", "?")
        ci = r["metadata"].get("chunk_index", "?")
        print(f"  [{i}] {src} chunk={ci} score={r['score']:.4f}")
        if "曹曦" in r["content"]:
            print(f"       *** CONTAINS ANSWER ***")

asyncio.run(main())
