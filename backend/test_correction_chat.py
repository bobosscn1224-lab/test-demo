"""Test auto-correction detection via streaming chat.
1. Start a session, ask a question
2. Get response
3. Send "不对，应该是..." to trigger auto-correction
4. Verify correction stored
5. Ask again — should get corrected answer
"""
import httpx, json, asyncio

BASE = "http://localhost:8001"

async def stream_chat(message, session_id=None):
    """Stream chat and return full response + session_id."""
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
    # 1. Ask a question first (so there's conversation context)
    print("=== Step 1: Ask initial question ===")
    reply, sid = await stream_chat("MO流程中L2PO的角色是什么？")
    print(f"Session: {sid}")
    print(f"Reply: {reply[:200]}...")

    # 2. Check if answer mentions 曹曦 or something else
    print("\n=== Step 2: Send correction ===")
    correction_msg = "不对，MO流程的L2PO是曹曦，L3 PO是汪霏"
    reply2, sid2 = await stream_chat(correction_msg, session_id=sid)
    print(f"Session: {sid2}")
    print(f"Reply: {reply2[:300]}...")

    if "校正" in reply2 or "记录" in reply2 or "记住" in reply2:
        print("OK: Auto-correction detected and acknowledged!")
    else:
        print("NOTE: Correction may not have been auto-detected (response was normal chat)")

    # 3. Check if correction was stored
    print("\n=== Step 3: Verify correction stored ===")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE}/api/knowledge/corrections")
        data = r.json()
        print(f"Corrections in DB: {data['count']}")
        for c in data["corrections"]:
            print(f"  - Q: {c['question'][:60]}")
            print(f"    A: {c['correct_answer'][:60]}")
            print(f"    Source: {c['source']}")

    # 4. Ask the same question again — should now use correction
    print("\n=== Step 4: Ask again (should use correction) ===")
    reply3, sid3 = await stream_chat("MO流程的L2PO是谁？")
    print(f"Reply: {reply3[:300]}...")
    if "曹曦" in reply3:
        print("OK: Corrected answer used!")
    else:
        print("NOTE: Answer didn't mention 曹曦")

    # 5. Clean up — delete test correction
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE}/api/knowledge/corrections")
        for c in r.json()["corrections"]:
            if c["source"] == "chat_auto":
                await client.delete(f"{BASE}/api/knowledge/corrections/{c['id']}")
                print(f"\nCleaned up correction: {c['id']}")

asyncio.run(main())
