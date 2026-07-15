"""Features module — self-contained business logic modules.

Each feature:
  - Has a dedicated API router in backend/app/api/
  - Reuses shared services from backend/app/services/
  - May import from backend/app/skills/ for backwards compatibility
  - Does NOT depend on the skill conversation system

Current status:
  - weekly_report:  API in api/reports.py, reuses skills/weekly_report modules
  - image_gen:      API in api/images.py, reuses services/image_gen_service.py
  - pptx_convert:   API in api/pptx.py, reuses services/batch_pptx_service.py

Future: logic currently in skills/ can be moved here as the migration progresses.
"""
