"""Multi-turn chat test to verify no hangs after several messages."""
import httpx, json, asyncio

BASE = "http://localhost:8001"

async def stream_chat(msg, sid=None):
    body = {"message": msg, "session_id": sid, "persona_slug": "default"}
    full = ""
    new_sid = sid
    async with httpx.AsyncClient(timeout=90) as c:
        async with c.stream("POST", f"{BASE}/api/chat/stream", json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:])
                        if ev["type"] == "token":
                            full += ev["data"]
                        elif ev["type"] == "done":
                            new_sid = ev.get("data", {}).get("session_id", sid)
                    except Exception:
                        pass
    return full.strip()[:200], new_sid

async def main():
    print("=== Multi-turn chat test ===")
    sid = None
    questions = [
        "什么是MO流程？",
        "MO流程有哪些关键阶段？",
        "L2PO的职责是什么？",
    ]
    for i, q in enumerate(questions):
        print(f"\n[{i+1}] Q: {q}")
        reply, sid = await stream_chat(q, sid)
        print(f"    A: {reply}")
        if not reply:
            print("    ❌ No response!")
        await asyncio.sleep(1)
    print("\n✅ Multi-turn test complete")

asyncio.run(main())
