"""Re-index M11.1 via API."""
import httpx, asyncio, os, json

BASE = "http://localhost:8001"
PDF_PATH = r'D:\数字分身\本地知识库\M11.1 验证商机流程说明文件-V1.0.pdf'

if not os.path.exists(PDF_PATH):
    PDF_PATH = r'D:\数字分身\本地知识库\MO流程\M11.1 验证商机流程说明文件-V1.0.pdf'

async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        # Get stats before
        r = await c.get(f"{BASE}/api/knowledge/stats")
        print(f"Before: {r.json()}")

        # Delete existing M11.1
        import hashlib
        doc_id = hashlib.md5(PDF_PATH.encode()).hexdigest()[:12]
        print(f"Deleting doc_id: {doc_id}")
        r = await c.delete(f"{BASE}/api/knowledge/{doc_id}")
        print(f"Delete: {r.json() if r.status_code == 200 else r.text}")

        # Upload + re-index
        with open(PDF_PATH, 'rb') as f:
            r = await c.post(f"{BASE}/api/knowledge/upload", files={"file": f})
            data = r.json()
            print(f"Re-index: {data}")

        # Verify search
        r = await c.get(f"{BASE}/api/knowledge/search", params={"q": "MO流程的L2PO是谁", "top_k": 5})
        data = r.json()
        print(f"\nTop 5 after re-index:")
        for i, res in enumerate(data["results"]):
            src = res["metadata"].get("source", "?")
            ci = res["metadata"].get("chunk_index", "?")
            score = res["score"]
            has_ans = "曹曦" in res["content"] or "流程L2 PO" in res["content"]
            marker = " *** ANSWER ***" if has_ans else ""
            print(f"  [{i}] {src} chunk={ci} score={score:.4f}{marker}")

asyncio.run(main())
