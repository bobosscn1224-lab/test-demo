"""Identify and remove backup directory docs from knowledge base."""
import httpx, asyncio, hashlib, os, json

BASE = "http://localhost:8001"
SKIP_DIRS = ["Backup0928", "BACKUP1225", "backup", "BACKUP"]

async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        # Get stats before
        r = await c.get(f"{BASE}/api/knowledge/stats")
        before = r.json()
        print(f"Before cleanup: {before['total_chunks']} chunks, {before['unique_docs']} docs")

        # Get all docs from the search (rough approach)
        r = await c.get(f"{BASE}/api/knowledge/corrections")

        # Walk the watch dir and find files in backup dirs
        watch_dir = r"D:\数字分身\本地知识库"
        backup_files = []
        keep_files = []

        for root, dirs, files in os.walk(watch_dir):
            # Check if this path is under a backup directory
            parts = root.replace(watch_dir, "").split(os.sep)
            is_backup = any(skip in parts for skip in SKIP_DIRS)
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.txt', '.md', '.csv'}:
                    continue
                fpath = os.path.join(root, f)
                if is_backup:
                    backup_files.append(fpath)
                else:
                    keep_files.append(fpath)

        print(f"\nBackup dir files: {len(backup_files)}")
        print(f"Keep files: {len(keep_files)}")

        # Show backup file names
        print("\nBackup files to remove:")
        for f in backup_files:
            print(f"  {os.path.basename(f)}")

        # Delete each backup file's doc from the index
        deleted_chunks = 0
        deleted_docs = 0
        for fpath in backup_files:
            doc_id = hashlib.md5(fpath.encode()).hexdigest()[:12]
            try:
                r = await c.delete(f"{BASE}/api/knowledge/{doc_id}")
                if r.status_code == 200:
                    data = r.json()
                    deleted_chunks += data.get("deleted_chunks", 0)
                    deleted_docs += 1
            except Exception:
                pass

        print(f"\nDeleted: {deleted_docs} docs, {deleted_chunks} chunks")

        # Get stats after
        r = await c.get(f"{BASE}/api/knowledge/stats")
        after = r.json()
        print(f"After cleanup: {after['total_chunks']} chunks, {after['unique_docs']} docs")

        # Show remaining file types
        print(f"\nRemaining files in index: {keep_files}")

asyncio.run(main())
