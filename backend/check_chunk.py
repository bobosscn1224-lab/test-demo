"""Debug why Chunk 0 isn't in top search results."""
import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio, json
from app.services.rag_service import rag_service

async def main():
    await rag_service.initialize()
    # Search with top_k=30 to check if chunk 0 appears
    query = "MO流程L2PO是谁"
    # Use internal hybrid search with high candidate count
    docs, metas, dists, scores = rag_service._hybrid_search_sync(query, 30)

    results = []
    for i, (doc, meta, dist, score) in enumerate(zip(docs, metas, dists, scores)):
        src = meta.get('source', '?')
        ci = meta.get('chunk_index', '?')
        has_answer = 'L2 PO' in doc or '曹曦' in doc
        marker = ' *** HAS_ANSWER ***' if has_answer else ''
        results.append({
            "rank": i, "source": src, "chunk_index": ci,
            "hybrid_score": round(score, 4), "sem_score": round(1-dist, 4),
            "has_answer": has_answer,
            "preview": doc[:200].replace('​', '')
        })

    with open(r'd:\数字分身\deep_search.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    for r in results:
        if r['has_answer']:
            print(f"#{r['rank']}: {r['source']} chunk={r['chunk_index']} sem={r['sem_score']:.4f} hybrid={r['hybrid_score']:.4f} ***")

asyncio.run(main())
