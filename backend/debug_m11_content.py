"""Debug: check actual M11.1 content in ChromaDB + test PDF extraction."""
import httpx, asyncio, os, hashlib, json

BASE = "http://localhost:8001"

async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        # Get all chunks for M11.1
        doc_id = hashlib.md5(r'D:\数字分身\本地知识库\M11.1 验证商机流程说明文件-V1.0.pdf'.encode()).hexdigest()[:12]
        print(f"doc_id: {doc_id}")

        # Check search for this doc
        r = await c.get(f"{BASE}/api/knowledge/search", params={"q": "流程L2 PO 曹曦 M11.1 验证商机", "top_k": 10})
        data = r.json()
        for i, res in enumerate(data["results"]):
            src = res["metadata"].get("source", "?")
            ci = res["metadata"].get("chunk_index", "?")
            score = res["score"]
            has = "曹曦" in res["content"]
            m = "***" if has else ""
            print(f"[{i}] {src} chunk={ci} score={score:.4f} {m}")

        # Try to read the uploaded file's content
        upload_path = r'd:\数字分身\backend\data\uploads\knowledge\M11.1 验证商机流程说明文件-V1.0.pdf'
        if os.path.exists(upload_path):
            print(f"\nUpload path exists: {upload_path}")
            print(f"Size: {os.path.getsize(upload_path)}")
        else:
            print(f"\nUpload path does NOT exist: {upload_path}")

asyncio.run(main())
