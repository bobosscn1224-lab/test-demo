"""Diagnose common issues: chat, skill, session, CORS"""
import httpx, json, sys, asyncio
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://127.0.0.1:8001"

async def test(name, coro):
    try:
        await coro
        print(f"  [OK] {name}")
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        # 1. CORS headers
        r = await c.options(f"{BASE}/api/chat/stream")
        print(f"CORS: allow-origin={r.headers.get('access-control-allow-origin','MISSING')}")
        print()

        # 2. Normal chat
        print("--- Normal chat ---")
        r = await c.post(f"{BASE}/api/chat/stream", json={"message": "你好", "session_id": None})
        text = r.text
        has_error = "error" in text.lower() and "type" in text
        print(f"  Status: {r.status_code}, has_error: {has_error}")
        for line in text.split("\n")[:3]:
            if line.startswith("data: "):
                d = json.loads(line[6:])
                print(f"  Type: {d.get('type')}, msg_len: {len(str(d.get('data','')))}")

        # 3. Skill trigger
        print("\n--- Skill trigger ---")
        r = await c.post(f"{BASE}/api/chat/stream", json={"message": "写周报", "session_id": None})
        for line in r.text.split("\n"):
            if line.startswith("data: "):
                d = json.loads(line[6:])
                print(f"  Type: {d.get('type')}, Skill: {d.get('skill')}, Mode: {d.get('data',{}).get('mode')}")

        # 4. Session list
        print("\n--- Sessions ---")
        r = await c.get(f"{BASE}/api/sessions")
        data = r.json()
        print(f"  Count: {len(data)}")

        # 5. Knowledge stats
        print("\n--- Knowledge ---")
        r = await c.get(f"{BASE}/api/knowledge/stats")
        d = r.json()
        print(f"  Status: {d.get('status')}, Docs: {d.get('unique_docs')}, Chunks: {d.get('total_chunks')}")

asyncio.run(main())
