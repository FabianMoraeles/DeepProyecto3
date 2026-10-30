"""Adaptadores acotados: sin fallback silencioso ni registro de secretos."""
import json
import os
from urllib.request import Request, urlopen
from urllib.parse import urlparse


class ProviderError(RuntimeError):
    pass


def complete(system, prompt, config):
    if config.provider == 'anthropic':
        if not os.getenv('ANTHROPIC_API_KEY'):
            raise ProviderError('Configura ANTHROPIC_API_KEY en el servidor o selecciona Ollama.')
        from anthropic import Anthropic
        try:
            client = Anthropic(timeout=config.timeout, max_retries=0)
            count = client.messages.count_tokens(model=config.model, system=system, messages=[{'role':'user','content':prompt}])
            if count.input_tokens > 8000:
                raise ProviderError('El contexto excede 8,000 tokens; reduce tablas o ejemplos.')
            response = client.messages.create(model=config.model, max_tokens=config.max_tokens,
                temperature=0, system=system, messages=[{'role': 'user', 'content': prompt}])
            text = ''.join(b.text for b in response.content if b.type == 'text')
            if response.stop_reason == 'max_tokens':
                raise ProviderError('La respuesta del modelo excedió el límite de salida; acota la pregunta.')
            tin, tout = response.usage.input_tokens, response.usage.output_tokens
            # Tarifas configuradas por el operador, nunca inferidas de nombres de modelo.
            prices = json.loads(os.getenv('DATOCLARO_PRICES_JSON', '{}')).get(config.model)
            cost = (tin*prices['input'] + tout*prices['output'])/1e6 if prices else None
            return {'text': text, 'tokens_in': tin, 'tokens_out': tout, 'cost_usd': cost, 'model': response.model}
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f'No se pudo completar la llamada a Claude ({type(exc).__name__}). Verifica credenciales, saldo y modelo.') from exc
    if config.provider == 'ollama':
        host = os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434').rstrip('/')
        url = urlparse(host)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username:
            raise ProviderError('OLLAMA_HOST inválido')
        payload = {'model': config.model, 'stream': False, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}],
                   'options': {'temperature': 0, 'num_predict': config.max_tokens, 'num_ctx': 8192}}
        if config.structured:
            payload['format'] = 'json'
        if len((system+prompt).encode('utf-8')) > 6500:
            raise ProviderError('El contexto local excede el límite conservador; reduce tablas o ejemplos.')
        try:
            req = Request(host+'/api/chat', json.dumps(payload).encode(), {'Content-Type': 'application/json'})
            with urlopen(req, timeout=config.timeout) as response:
                obj = json.loads(response.read(2_000_000))
            if not obj.get('done') or obj.get('done_reason') == 'length':
                raise ValueError('Respuesta incompleta')
            return {'text': obj['message']['content'], 'tokens_in': obj.get('prompt_eval_count'),
                    'tokens_out': obj.get('eval_count'), 'cost_usd': None, 'model': obj.get('model', config.model)}
        except Exception as exc:
            raise ProviderError('Ollama no respondió. Inicia el servicio y descarga el modelo configurado.') from exc
    raise ProviderError('Proveedor desconocido')
