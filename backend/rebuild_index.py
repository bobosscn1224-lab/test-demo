"""Rebuild index with Chinese embedding model."""
import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio, os, traceback

async def main():
    from app.services.rag_service import rag_service, _make_doc_id
    from app.utils.file_parser import parse_file_sync, SUPPORTED_EXTENSIONS

    await rag_service.initialize()
    if not rag_service.is_ready:
        print("RAG not ready"); return

    # Nuke old collection
    try:
        rag_service._client.delete_collection("knowledge_base")
    except Exception:
        pass
    rag_service._collection = rag_service._client.get_or_create_collection(
        name="knowledge_base", metadata={"hnsw:space": "cosine"},
    )
    print("Collection reset", flush=True)

    watch_dir = r'D:\数字分身\本地知识库'
    total = 0
    skip_dirs = {'Backup0928', 'BACKUP1225'}  # Skip backup duplicates

    for root, dirs, files in os.walk(watch_dir):
        # Filter out backup directories
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            fpath = os.path.join(root, fname)
            try:
                text = parse_file_sync(fpath)
                if not text:
                    print(f"  SKIP: {fname}", flush=True)
                    continue
                meta = {"source": fname, "file_path": fpath, "doc_id": _make_doc_id(fpath)}
                ids = await rag_service.index_text(text, meta)
                if ids:
                    total += 1
                    print(f"  OK [{len(ids)}ch] {fname}", flush=True)
                else:
                    print(f"  FAIL: {fname}", flush=True)
            except Exception as e:
                print(f"  ERR: {fname} - {e}", flush=True)
                traceback.print_exc()

    stats = await rag_service.get_stats()
    print(f"\nDone. {total} files indexed. Stats: {stats}", flush=True)

asyncio.run(main())
