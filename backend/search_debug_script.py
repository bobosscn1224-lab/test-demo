import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio
from app.services.rag_service import rag_service

async def test():
    await rag_service.initialize()
    qe = rag_service._embedding_fn.encode(['MO流程L2PO是谁'], show_progress_bar=False).tolist()
    results = rag_service._collection.query(query_embeddings=qe, n_results=20)
    docs = results['documents'][0]
    metas = results['metadatas'][0]
    dists = results['distances'][0]

    target_found = False
    with open(r'd:\数字分身\search_debug.txt', 'w', encoding='utf-8') as f:
        for i, doc in enumerate(docs):
            source = metas[i].get('source', '?') if i < len(metas) else '?'
            score = 1 - dists[i] if i < len(dists) else 0
            has_l2 = 'L2' in doc or 'L2' in source
            marker = '*** HAS_L2 ***' if has_l2 else ''
            f.write(f'--- #{i} score={score:.4f} src={source} {marker} ---\n')
            f.write(doc[:200] + '\n\n')
            if '流程L2 PO' in doc or ('L2' in doc and 'PO' in doc):
                target_found = True
                f.write('>>> TARGET FOUND!\n')
    print(f'Target found in top 20: {target_found}')

asyncio.run(test())
