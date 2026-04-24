import yaml
from pathlib import Path
from pydantic import BaseModel

class ExperimentConfig(BaseModel):
    format: str
    documents_dir: str

class EmbeddingsConfig(BaseModel):
    type: str
    model_name: str
    api_base: str = ""
    api_key: str = ""

class LLMConfig(BaseModel):
    provider: str
    model: str
    temperature: float

class RAGConfig(BaseModel):
    experiment: ExperimentConfig
    embeddings: EmbeddingsConfig
    llm: LLMConfig

def load_config(config_path: str = "config.yaml") -> RAGConfig:
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RAGConfig(**data)

# Singleton instance
config = load_config(Path(__file__).parent / "config.yaml")
