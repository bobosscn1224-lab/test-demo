import json
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user_profile import UserProfile
from app.services.llm_service import llm_service


class UserProfileService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create(self) -> UserProfile:
        result = await self.db.execute(select(UserProfile).where(UserProfile.id == "default"))
        profile = result.scalar_one_or_none()
        if not profile:
            profile = UserProfile(id="default")
            self.db.add(profile)
            await self.db.commit()
            await self.db.refresh(profile)
        return profile

    async def add_fact(self, fact: str, category: str, source: str = "chat", importance: int = 3):
        profile = await self.get_or_create()
        facts = list(profile.learned_facts or [])

        # Fuzzy dedup: check if a similar fact exists (simple overlap)
        existing_idx = None
        fact_words = set(fact.lower().split())
        for i, f in enumerate(facts):
            existing_words = set(f.get("fact", "").lower().split())
            if fact_words and existing_words:
                overlap = len(fact_words & existing_words) / min(len(fact_words), len(existing_words))
                if overlap > 0.6:  # 60% word overlap = same fact
                    existing_idx = i
                    break

        if existing_idx is not None:
            # Update existing: bump count, take max importance
            existing = facts[existing_idx]
            existing["count"] = existing.get("count", 1) + 1
            existing["importance"] = max(existing.get("importance", 3), importance)
            existing["updated_at"] = datetime.utcnow().isoformat()
        else:
            facts.append({
                "fact": fact,
                "category": category,
                "source": source,
                "importance": importance,
                "count": 1,
                "learned_at": datetime.utcnow().isoformat(),
            })

        # Evict: keep top 100 by importance * count
        if len(facts) > 100:
            facts.sort(key=lambda f: f.get("importance", 3) * f.get("count", 1), reverse=True)
            facts = facts[:100]

        profile.learned_facts = facts
        await self.db.commit()

    async def update_basic_info(self, info: dict):
        profile = await self.get_or_create()
        current = dict(profile.basic_info or {})
        current.update(info)
        profile.basic_info = current
        await self.db.commit()

    async def update_expertise(self, items: list[str]):
        profile = await self.get_or_create()
        current = list(profile.expertise or [])
        for item in items:
            if item not in current:
                current.append(item)
        profile.expertise = current
        await self.db.commit()

    async def update_projects(self, projects: list[dict]):
        profile = await self.get_or_create()
        current = list(profile.projects or [])
        for proj in projects:
            existing = next((p for p in current if p.get("name") == proj.get("name")), None)
            if existing:
                existing.update(proj)
            else:
                current.append(proj)
        profile.projects = current
        await self.db.commit()

    async def get_profile_summary(self) -> str:
        profile = await self.get_or_create()
        parts = []

        basic = profile.basic_info or {}
        if basic:
            parts.append("## 用户基本信息")
            for k, v in basic.items():
                parts.append(f"- {k}: {v}")

        expertise = profile.expertise or []
        if expertise:
            parts.append("\n## 专业领域")
            for e in expertise:
                parts.append(f"- {e}")

        projects = profile.projects or []
        if projects:
            parts.append("\n## 当前项目")
            for p in projects:
                parts.append(f"- {p.get('name', '')}: {p.get('description', '')} [{p.get('status', '')}]")

        facts = profile.learned_facts or []
        if facts:
            parts.append("\n## 从对话中了解到的信息")
            # Show top 20 by importance * count (most relevant + frequently mentioned)
            scored = sorted(
                facts,
                key=lambda f: f.get("importance", 3) * f.get("count", 1),
                reverse=True,
            )
            for f in scored[:20]:
                imp = f.get("importance", 3)
                cnt = f.get("count", 1)
                stars = "⭐" * min(imp, 5)
                repeat = f" (提及{cnt}次)" if cnt > 1 else ""
                parts.append(f"- {stars} [{f.get('category', '')}] {f.get('fact', '')}{repeat}")

        return "\n".join(parts) if parts else ""


async def extract_user_info_from_message(user_message: str, assistant_reply: str, db: AsyncSession):
    """Use LLM to extract user profile info from conversation, skip if nothing useful."""
    svc = UserProfileService(db)

    extraction_prompt = f"""分析以下对话，提取关于"用户"的新信息。只提取明确陈述的事实，不要推断。
如果没有值得记录的新信息，返回空的JSON数组。

对每个事实，标注重要性(1-5)：
  5=核心身份/长期偏好  4=项目关键信息  3=一般偏好/技能  2=临时提及  1=琐碎信息

用户消息: {user_message[:500]}
助手回复: {assistant_reply[:200]}

返回严格JSON格式，不要带markdown代码块标记:
[{{"fact": "事实描述", "category": "basic_info|expertise|project|preference|other", "importance": 3}}]"""

    try:
        response = await llm_service.chat(
            system_prompt="你是一个信息提取助手。只提取对话中明确陈述的用户信息，标注重要性。返回严格JSON格式。",
            messages=[{"role": "user", "content": extraction_prompt}],
            max_tokens=500,
            temperature=0.1,
        )
        text = response.content[0].text if response.content else "[]"
        # Strip markdown code fences
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        if not text:
            return

        facts = json.loads(text)
        for item in facts:
            if isinstance(item, dict) and item.get("fact"):
                await svc.add_fact(
                    fact=item["fact"],
                    category=item.get("category", "other"),
                    source="chat_analysis",
                    importance=int(item.get("importance", 3)),
                )
                # Also update structured fields
                cat = item.get("category", "")
                fact_text = item["fact"]
                if cat == "basic_info":
                    await svc.update_basic_info({"note": fact_text})
                elif cat == "expertise":
                    await svc.update_expertise([fact_text])
                elif cat == "project":
                    await svc.update_projects([{"name": fact_text, "status": "进行中"}])
    except Exception:
        pass  # Extraction failure should not break chat
