"""Exercise TD callback behavior without requiring a running TD process."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Callbacks(unittest.TestCase):
    def setUp(self):
        self.module = load_source('callbacks', ROOT / 'touchdesigner/webserver_callbacks.py')
        self.module.project = SimpleNamespace(name='generic.toe')
        self.module.ui = SimpleNamespace(undo=Mock())
        self.error_lookup = Mock(return_value=None)
        self.module.me = SimpleNamespace(parent=lambda: SimpleNamespace(op=self.error_lookup))
        self.module.op = Mock(return_value=None)

    def request(self, uri, data=None):
        request = {'uri': uri, 'method': 'POST' if data is not None else 'GET'}
        if data is not None:
            request['data'] = json.dumps(data).encode()
        response = self.module.onHTTPRequest(None, request, {})
        return response['statusCode'], json.loads(response['data'])

    def test_nested_functions_resolve_script_variables_and_imports(self):
        status, result = self.request('/execute', {'script': 'import math\nvalue = 9\ndef nested():\n    return math.sqrt(value)\nprint(nested())'})
        self.assertEqual(status, 200)
        self.assertEqual(result, {'output': '3.0\n', 'errors': []})
        self.error_lookup.assert_called_with('error1')
        self.assertEqual(self.module.ui.undo.endBlock.call_count, 1)
        _, second = self.request('/execute', {'script': "print('value' in globals())"})
        self.assertEqual(second['output'], 'False\n')

    def test_execution_failure_closes_undo_block(self):
        _, result = self.request('/execute', {'script': 'raise ValueError("test failure")'})
        self.assertEqual(result['errors'], ['test failure'])
        self.module.ui.undo.endBlock.assert_called_once()

    def test_query_parsing_does_not_double_decode_paths(self):
        self.module.op.return_value = SimpleNamespace(path='/project1/name%20literal', name='name%20literal', OPType='baseCOMP', family='COMP')
        status, result = self.request('/operator?extra=1&path=%2Fproject1%2Fname%2520literal')
        self.assertEqual(status, 200)
        self.module.op.assert_called_once_with('/project1/name%20literal')
        self.assertEqual(result['family'], 'COMP')
        self.assertEqual(self.request('/operator_invalid')[0], 404)

    def test_chop_requires_explicit_path(self):
        self.assertEqual(self.request('/chop')[0], 400)

    def test_screenshot_defaults_to_temp_directory(self):
        def save(filename):
            Path(filename).write_bytes(b'png-fixture')
        self.module.op.return_value = SimpleNamespace(family='TOP', save=save)
        status, result = self.request('/screenshot?path=%2Fcustom%2Foutput')
        self.assertEqual(status, 200)
        actual = Path(result['saved_to'])
        self.assertEqual(actual.parent, Path(tempfile.gettempdir()) / 'td-mcp/screenshots')
        self.assertEqual(result['path'], '/custom/output')
        actual.unlink()

    def test_empty_analysis_returns_clear_error(self):
        self.module.op.return_value = SimpleNamespace(family='CHOP', numSamples=0, chans=lambda: [])
        status, result = self.request('/image_stats?rows_chop=/a&cols_chop=/b')
        self.assertEqual(status, 400)
        self.assertIn('samples', result['error'])


class Installer(unittest.TestCase):
    def test_refuses_replacement_before_creating_anything(self):
        module = load_source('installer', ROOT / 'touchdesigner/install_bridge.py')
        parent = Mock()
        parent.op.return_value = object()
        with self.assertRaises(ValueError):
            module.install_bridge(parent)
        parent.create.assert_not_called()

    def test_embeds_source_and_leaves_server_inactive(self):
        module = load_source('installer', ROOT / 'touchdesigner/install_bridge.py')
        created = {}
        comp = SimpleNamespace(nodeX=0, nodeY=0)
        def create(op_type, name):
            child = SimpleNamespace(par=SimpleNamespace(), nodeX=0, nodeY=0)
            created[name] = child
            return child
        comp.create = create
        parent = SimpleNamespace(op=lambda name: None, create=lambda *args: comp, children=[comp])
        result = module.install_bridge(parent, port=9981)
        self.assertIs(result, comp)
        self.assertFalse(created['webserver'].par.active)
        self.assertEqual(created['webserver'].par.port, 9981)
        self.assertIs(created['webserver'].par.callbacks, created['webserver_callbacks'])
        self.assertIn('def onHTTPRequest', created['webserver_callbacks'].text)
        self.assertEqual(set(created), {'error1', 'webserver', 'webserver_callbacks', 'README'})


if __name__ == '__main__':
    unittest.main()
