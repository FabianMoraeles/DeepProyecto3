import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
from app.config import Config
from app.llm import complete, ProviderError


class ProviderTests(unittest.TestCase):
    def test_missing_credentials(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY':''}):
            with self.assertRaises(ProviderError): complete('system','prompt',Config())

    @unittest.skipUnless(importlib.util.find_spec('anthropic'),'SDK opcional')
    def test_sdk_contract_and_cost(self):
        client=MagicMock()
        client.messages.count_tokens.return_value=SimpleNamespace(input_tokens=30)
        client.messages.create.return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='{"status":"ok","sql":"SELECT 1"}')],
            usage=SimpleNamespace(input_tokens=30,output_tokens=10),model='test-model',stop_reason='end_turn')
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'test-only','DATOCLARO_PRICES_JSON':'{"test-model":{"input":1,"output":2}}'}), patch('anthropic.Anthropic',return_value=client):
            output=complete('system','prompt',Config(model='test-model'))
            self.assertAlmostEqual(output['cost_usd'],0.00005)
            client.messages.count_tokens.return_value=SimpleNamespace(input_tokens=8001)
            with self.assertRaises(ProviderError): complete('system','prompt',Config())
            self.assertEqual(client.messages.create.call_count,1)


if __name__=='__main__': unittest.main()
