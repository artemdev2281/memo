from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    ollama_url: str = "http://127.0.0.1:11434"
    data_dir: str = "./data"
    embed_model: str = "bge-m3"
    name_model: str = "qwen3:1.7b"

    model_config = {"env_prefix": "MEMO_"}


settings = Settings()
