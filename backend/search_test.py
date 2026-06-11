import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio, json
from app.services.rag_service import rag_service

async def test():
    await rag_service.initialize()
    queries = [
        "MO流程L2PO是谁",
        "MO流程的L2 PO是谁",
        "L2PO",
        "曹曦",
    ]
    out = []
    for q in queries:
        results = await rag_service.search_raw(q, top_k=8)
        o = {"query": q, "results": []}
        for i, r in enumerate(results):
            o["results"].append({
                "rank": i,
                "score": r['score'],
                "source": r['metadata'].get('source', '?'),
                "content_preview": r['content'][:200].replace('​', ''),
            })
        out.append(o)

    with open(r'd:\数字分身\search_results.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("Results written to search_results.json")

asyncio.run(test())
