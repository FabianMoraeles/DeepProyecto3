from dataclasses import dataclass, replace
import os


@dataclass(frozen=True)
class Config:
    provider: str = 'anthropic'
    model: str = 'claude-haiku-5-5'
    retrieval: str = 'lexical'
    top_k: int = 4
    examples: int = 3
    repair: bool = True
    structured: bool = True
    clarify: bool = True
    full_schema: bool = False
    timeout: float = 45
    max_tokens: int = 1500

    @classmethod
    def from_env(cls):
        try:
            from dotenv import load_dotenv
            from datoclaro.io import ROOT
            load_dotenv(ROOT / '.env')
        except ImportError:
            pass  # Las herramientas de datos siguen funcionando sin dependencias UI.
        provider = os.getenv('DATOCLARO_PROVIDER', 'anthropic')
        return cls(provider=provider,
                   model=os.getenv('DATOCLARO_MODEL', 'qwen2.5-coder:7b-instruct' if provider == 'ollama' else 'claude-haiku-5-5'),
                   retrieval=os.getenv('DATOCLARO_RETRIEVAL', 'lexical'))


def experiment(name):
    base = replace(Config.from_env(), provider='anthropic', model='claude-haiku-5-5')
    configs = {
        'I1': dict(full_schema=True, structured=False, examples=0, repair=False, clarify=False),
        'I2': dict(full_schema=True, examples=0, repair=False, clarify=False),
        'I3': dict(examples=0, repair=False, clarify=False),
        'I4': dict(repair=False, clarify=False),
        'I5': dict(clarify=False), 'I6': {},
        'I7': dict(provider='anthropic', model='claude-sonnet-5-5'),
        'I8': dict(provider='ollama', model='qwen2.5-coder:7b-instruct'),
    }
    if name not in configs:
        raise ValueError('Experimento desconocido')
    return replace(base, **configs[name])
