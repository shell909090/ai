import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import signal
import time
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlsplit, parse_qs

SCRIPT = Path(__file__).resolve().parents[1] / 'oc-task'


class TaskTest(unittest.TestCase):
    def setUp(self):
        Path('/tmp/opencode').mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir='/tmp/opencode', prefix='oc-task-test-')
        self.root = Path(self.temp.name)
        self.requests = []
        self.outcome = 'succeeded'
        self.delete_status = 204
        self.interrupt_delay = 0
        self.expected_auth = 'Basic ' + base64.b64encode(b'test-user:test-password').decode()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                owner.requests.append((self.command, self.path, json.loads(body) if body else None,
                                       self.headers.get('Authorization') == owner.expected_auth))
                route = urlsplit(self.path)
                if route.path.endswith("/interrupt"):
                    time.sleep(owner.interrupt_delay)
                data = None
                status = 200
                if self.command == 'DELETE':
                    status = owner.delete_status
                elif self.command == 'POST' and route.path == '/api/session':
                    data = {'id': 'test-session'}
                elif route.path.endswith('/message'):
                    kind = parse_qs(route.query).get('type', [''])[0]
                    data = ([{'id': 'reply', 'content': [{'type': 'text', 'text': 'summary text'}]}]
                            if kind == 'assistant' else [{'error': {'type': 'ModelError', 'message': 'model failed'}}])
                elif route.path.endswith('/permission') or route.path.endswith('/form'):
                    data = []
                elif self.command == 'GET':
                    data = {'outcome': owner.outcome}
                payload = json.dumps({'data': data}).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                if status != 204:
                    self.wfile.write(payload)

            do_GET = do_POST = do_DELETE = handle_request

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('OC_TASK_', 'OPENCODE_SERVER_')) and k != 'MODEL'}
        self.env.update(OC_TASK_CONFIG=str(self.root / 'missing-config.json'),
                        OPENCODE_SERVER_USERNAME='test-user', OPENCODE_SERVER_PASSWORD='test-password')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def run_task(self, *arguments, prompt='private prompt'):
        return subprocess.run([sys.executable, str(SCRIPT), '--server', self.url,
                               '--format', 'json', '-m', 'provider/model#fast',
                               *arguments, '--stdin'], input=prompt, text=True,
                              capture_output=True, env=self.env, cwd=self.root, timeout=10)

    def test_success_agent_stdin_and_cleanup(self):
        completed = self.run_task('--agent', 'logbook', '--cleanup')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['text'], 'summary text')
        self.assertEqual(result['cleanup'], {'requested': True, 'deleted': True, 'error': None})
        create = self.requests[0][2]
        self.assertEqual(create['agent'], 'logbook')
        self.assertEqual(create['model'], {'providerID': 'provider', 'id': 'model', 'variant': 'fast'})
        self.assertEqual(create['location']['directory'], str(self.root))
        self.assertEqual(self.requests[1][2], {'text': 'private prompt'})
        self.assertTrue(all(request[3] for request in self.requests), 'authentication mismatch')
        self.assertEqual(self.requests[-1][0], 'DELETE')

    def test_model_failure_is_nonzero_json(self):
        self.outcome = 'failed'
        completed = self.run_task('--cleanup')
        self.assertNotEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('model failed', result['error'])
        self.assertTrue(result['cleanup']['deleted'])

    def test_cleanup_failure_preserves_text(self):
        self.delete_status = 500
        completed = self.run_task('--cleanup')
        self.assertNotEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertEqual(result['text'], 'summary text')
        self.assertFalse(result['cleanup']['deleted'])
        self.assertTrue(result['cleanup']['error'])

    def test_timeout_cancels_before_cleanup(self):
        self.outcome = None
        completed = self.run_task('--timeout', '0.15', '--cleanup')
        self.assertEqual(completed.returncode, 124)
        result = json.loads(completed.stdout)
        self.assertIn('timed out', result['error'])
        self.assertTrue(result['cleanup']['deleted'])
        self.assertEqual(self.requests[-2][:2], ('POST', '/api/session/test-session/interrupt?resume=false'))
        self.assertEqual(self.requests[-1][:2], ('DELETE', '/api/session/test-session'))

    def test_repeated_stop_signal_finishes_cancellation_and_cleanup(self):
        self.outcome = None
        self.interrupt_delay = 0.2
        command = [sys.executable, str(SCRIPT), '--server', self.url, '--format', 'json',
                   '-m', 'provider/model', '--cleanup', '--stdin']
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, env=self.env, cwd=self.root) as process:
            process.stdin.write('private prompt')
            process.stdin.close()
            process.stdin = None
            deadline = time.monotonic() + 5
            while not any('/prompt' in r[1] for r in self.requests):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            process.send_signal(signal.SIGTERM)
            while not any('/interrupt' in r[1] for r in self.requests):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 143, stderr)
        result = json.loads(stdout)
        self.assertEqual(result['status'], 'interrupted')
        self.assertTrue(result['cleanup']['deleted'])

    def test_background_only_submits(self):
        self.outcome = None
        completed = self.run_task('-b')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result['status'], 'submitted')
        self.assertEqual([request[0] for request in self.requests], ['POST', 'POST'])
        self.assertFalse(result['cleanup']['requested'])

    def test_background_cleanup_rejected_before_network(self):
        completed = self.run_task('-b', '--cleanup')
        self.assertEqual(completed.returncode, 2)
        self.assertIn('foreground', completed.stderr)
        self.assertFalse(self.requests)

    def test_config_and_environment_model_precedence(self):
        config = self.root / 'config.json'
        config.write_text(json.dumps({'model': 'config/model', 'server': self.url}))
        self.env['OC_TASK_CONFIG'] = str(config)
        for env_model, expected in [(None, 'config'), ('environment/model', 'environment')]:
            if env_model:
                self.env['OC_TASK_MODEL'] = env_model
            completed = subprocess.run([sys.executable, str(SCRIPT), '-b', '--format', 'json', 'prompt'],
                                       capture_output=True, text=True, env=self.env, cwd=self.root, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(self.requests[-2][2]['model']['providerID'], expected)

    def test_missing_model_rejected(self):
        completed = subprocess.run([sys.executable, str(SCRIPT), '--stdin'], input='prompt',
                                   capture_output=True, text=True, env=self.env, cwd=self.root, timeout=10)
        self.assertEqual(completed.returncode, 2)
        self.assertIn('model', completed.stderr)
        self.assertFalse(self.requests)


if __name__ == '__main__':
    unittest.main()
