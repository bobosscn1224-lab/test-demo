"""Final end-to-end test: strict prompt + correction + chat."""
import httpx, json, asyncio

BASE = "http://localhost:8001"

async def stream_chat(msg, sid=None):
    body = {"message": msg, "session_id": sid, "persona_slug": "default"}
    full = ""
    new_sid = sid
    async with httpx.AsyncClient(timeout=60) as c:
        async with c.stream("POST", f"{BASE}/api/chat/stream", json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:])
                        if ev["type"] == "token":
                            full += ev["data"]
                        elif ev["type"] == "done":
                            if ev.get("data", {}).get("session_id"):
                                new_sid = ev["data"]["session_id"]
                    except Exception:
                        pass
    return full.strip(), new_sid

async def main():
    # Test 1: Ask with knowledge
    print("=== Test 1: Knowledge-based question with correction ===")
    reply, sid = await stream_chat("MO流程的L2PO是谁？")
    print(f"Reply: {reply[:500]}")
    print(f"Contains 曹曦: {'曹曦' in reply}")
    print(f"Contains source doc: {'M11' in reply or '验证商机' in reply}")

    # Test 2: Ask something NOT in knowledge base
    print("\n=== Test 2: Question NOT in knowledge base ===")
    reply2, _ = await stream_chat("今天天气怎么样？", sid)
    print(f"Reply: {reply2[:200]}")
    has_no_info = "知识库" in reply2 or "资料" in reply2 or "无法" in reply2
    print(f"Refers to knowledge limitation: {has_no_info}")

    # Clean up correction
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/api/knowledge/corrections")
        for corr in r.json()["corrections"]:
            await c.delete(f"{BASE}/api/knowledge/corrections/{corr['id']}")
            print(f"\nCleaned up: {corr['id']}")

asyncio.run(main())
