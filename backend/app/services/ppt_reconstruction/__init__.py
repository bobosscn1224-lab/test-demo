"""PPT Reconstruction — Element-by-element editable PPTX pipeline.

Route: source image -> enhanced CV/OCR analysis -> LLM layout plan
       -> background handler -> element-by-element PPTX (PRIMARY)
       -> visual_locked PPTX (fallback).

New modules:
- analysis_engine: Enhanced CV/OCR detection (PaddleOCR + Tesseract, all shapes, gradient)
- background_handler: Native background layer (solid, gradient, or inpainted image)
- layout_planner: LLM-driven layout plan generation
- pipeline: Orchestrator with fallback chain (element-by-element -> visual_locked -> basic OCR)
"""
