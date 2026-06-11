"""Debug: directly check ChromaDB for M11.1 chunk 0"""
import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio, json
from app.services.rag_service import rag_service, _make_doc_id

async def main():
    await rag_service.initialize()

    query = "MO流程L2PO是谁"
    qe = rag_service._embedding_fn.encode([query], show_progress_bar=False).tolist()

    # Get all M11.1 chunks
    doc_id = _make_doc_id(r'D:\数字分身\本地知识库\M11.1 验证商机流程说明文件-V1.0.pdf')
    print(f"Looking for doc_id: {doc_id}")

    # Direct ChromaDB query for all chunks
    all_data = rag_service._collection.get(include=["documents", "metadatas"])
    found = []
    for cid, doc, meta in zip(all_data.get('ids', []), all_data.get('documents', []), all_data.get('metadatas', [])):
        if meta and meta.get('doc_id') == doc_id:
            found.append((cid, doc, meta))

    print(f"Found {len(found)} chunks for this doc in DB")

    # Check each chunk's distance
    for cid, doc, meta in found:
        ci = meta.get('chunk_index', '?')
        emb = rag_service._embedding_fn.encode([doc], show_progress_bar=False).tolist()
        from sklearn.metrics.pairwise import cosine_similarity
        sim = cosine_similarity(qe, emb)[0][0]
        has = '流程L2 PO' in doc
        marker = " *** HAS ANSWER ***" if has else ""
        print(f"  {cid} chunk={ci} sem={sim:.4f} len={len(doc)}{marker}")

    # Now check top 50 semantic results to see where M11.1 chunks rank
    results = rag_service._collection.query(query_embeddings=qe, n_results=100)
    if results and results.get('ids'):
        for i, (rid, rmeta) in enumerate(zip(results['ids'][0], results.get('metadatas', [[]])[0])):
            src = rmeta.get('source', '?') if rmeta else '?'
            ci = rmeta.get('chunk_index', '?') if rmeta else '?'
            if 'M11.1' in src and 'V1.0.pdf' in src:
                dist = results['distances'][0][i] if results.get('distances') else 0
                doc_text = results['documents'][0][i][:100]
                print(f"  SEM rank {i}: {src} chunk={ci} dist={dist:.4f} sem={1-dist:.4f}")

asyncio.run(main())
