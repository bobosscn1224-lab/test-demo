from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    anthropic_base_url: str = "https://api.deepseek.com/anthropic"
    claude_model: str = "deepseek-v4-pro"
    claude_max_tokens: int = 16384
    claude_temperature: float = 0.7

    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    siliconflow_api_key: str = ""
    siliconflow_embedding_base_url: str = "https://api.siliconflow.cn/v1/embeddings"

    default_voice_id: str = "zh-CN-YunxiNeural"
    whisper_model_size: str = "small"

    database_url: str = "sqlite+aiosqlite:///./data/digital_twin.db"

    chroma_persist_dir: str = "./data/chroma_db"

    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: list[str] = ["http://localhost:5173"]

    watch_dirs: str = "[]"

    active_persona: str = "default"
    personas_dir: str = "./personas"

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_oauth_redirect_uri: str = ""

    ruizhi_imagegen_exe: str = ""
    ruizhi_home: str = ""
    codex_home: str = ""
    ruizhi_api_key: str = ""
    openai_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}


settings = Settings()
