"""Re-index M11.1 PDF only to test improved extraction."""
import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio, os, json
from app.services.rag_service import rag_service, _make_doc_id

async def main():
    await rag_service.initialize()

    paths = [
        r'D:\数字分身\本地知识库\M11.1 验证商机流程说明文件-V1.0.pdf',
        r'D:\数字分身\本地知识库\MO流程\M11.1 验证商机流程说明文件-V1.0.pdf',
    ]
    for pdf_path in paths:
        if os.path.exists(pdf_path):
            doc_id = _make_doc_id(pdf_path)
            await rag_service.delete_doc(doc_id)
            ids = await rag_service.index_file(pdf_path)
            print(f"Re-indexed: {os.path.basename(pdf_path)} -> {len(ids)} chunks")

    results = await rag_service.search_raw("MO流程L2PO是谁", top_k=10)
    out = []
    for i, r in enumerate(results):
        src = r['metadata'].get('source', '?')
        ci = r['metadata'].get('chunk_index', '?')
        content = r['content'].replace('​', '')
        has_l2po = '流程L2 PO' in content
        out.append({
            "rank": i, "score": r['score'], "source": src, "chunk_index": ci,
            "has_L2PO_answer": has_l2po,
            "preview": content[:300]
        })

    with open(r'd:\数字分身\reindex_result.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    for o in out:
        marker = " <<< ANSWER" if o['has_L2PO_answer'] else ""
        print(f"#{o['rank']} score={o['score']:.4f} {o['source']} chunk={o['chunk_index']}{marker}")

asyncio.run(main())
