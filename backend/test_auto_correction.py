"""Test auto-correction — all streaming."""
import httpx, json, asyncio

BASE = "http://localhost:8001"

async def stream_chat(message, session_id=None):
    body = {"message": message, "session_id": session_id, "persona_slug": "default"}
    full = ""
    sid = session_id
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", f"{BASE}/api/chat/stream", json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event["type"] == "token":
                            full += event["data"]
                        elif event["type"] == "done":
                            if event["data"] and "session_id" in event["data"]:
                                sid = event["data"]["session_id"]
                    except Exception:
                        pass
    return full.strip(), sid

async def main():
    # 1. First message — ask a question
    print("=== Step 1: Ask question ===")
    reply, sid = await stream_chat("MO流程的L2PO是谁？")
    print(f"Session: {sid}")
    print(f"Reply: {reply[:200]}")
    print(f"Contains 曹曦: {'曹曦' in reply}")

    # 2. Correction — this should trigger auto-detection
    print("\n=== Step 2: Send correction ===")
    reply2, sid2 = await stream_chat("不对，MO流程的L2PO是曹曦", session_id=sid)
    print(f"Session: {sid2} (same: {sid2 == sid})")
    print(f"Reply: {reply2[:300]}")
    is_correction_ack = any(kw in reply2 for kw in ["校正", "记录", "记住"])
    print(f"Is correction ack: {is_correction_ack}")

    # 3. Check DB
    print("\n=== Step 3: Check stored corrections ===")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/api/knowledge/corrections")
        data = r.json()
        print(f"Count: {data['count']}")
        for corr in data["corrections"]:
            print(f"  Q: {corr['question']}")
            print(f"  A: {corr['correct_answer']}")

    # 4. Search for the answer
    print("\n=== Step 4: Search ===")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/api/knowledge/search", params={"q": "MO流程的L2PO是谁", "top_k": 3})
        data = r.json()
        for res in data["results"]:
            print(f"  src={res['metadata'].get('source','?')} score={res['score']}")

    # Cleanup
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/api/knowledge/corrections")
        for corr in r.json()["corrections"]:
            await c.delete(f"{BASE}/api/knowledge/corrections/{corr['id']}")

asyncio.run(main())
