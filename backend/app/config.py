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
    agnes_api_key: str = ""
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    agnes_model: str = "agnes-2.0-flash"

    lovart_api_key: str = ""
    lovart_base_url: str = "https://api.catrouter.net/v1"

    image_gen_backend: str = "auto"

    shiyun_api_key: str = ""
    shiyun_base_url: str = "https://api.tokenriver.cn"

    api0029_key: str = ""
    api0029_base_url: str = "https://api.0029.org"

    tutujin_api_key: str = ""
    tutujin_api_key_a: str = ""
    tutujin_api_key_b: str = ""
    tutujin_api_key_c: str = ""
    tutujin_vision_api_key: str = ""
    tutujin_base_url: str = "https://api.tutujin.com"
    apiyi_api_key: str = ""
    apiyi_quality: str = "low"

    icover_api_key: str = ""
    icover_base_url: str = "https://icover.ai"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}


settings = Settings()
