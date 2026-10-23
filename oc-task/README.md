# oc-task

A standard-library Python client for submitting tasks to an OpenCode 2 HTTP service. It does not launch the OpenCode CLI. Python 3 and a running, compatible OpenCode 2 service are required.

Put the executable `oc-task` on `PATH` or invoke its installed path. No particular installation directory is required.

```sh
export OPENCODE_SERVER_PASSWORD='your-service-password'
oc-task --server http://127.0.0.1:4096 -m provider/model 'Summarize this project'
printf '%s\n' 'Summarize the supplied activity' | oc-task --agent logbook --cleanup --format json --stdin
oc-task -b -m provider/model 'Run this task on the server'
```

The second example requires a default model in the environment or configuration. There is no built-in default model. `--agent` selects an agent already configured on the service; it does not create or configure an agent. Configure restricted summarization agents on the server and verify their tool permissions there.

## Execution modes

Foreground execution waits for a final server outcome, streams text in the default output mode, and returns a nonzero exit code on failure. `--timeout SECONDS` limits execution; zero, the default, means no overall limit. On timeout, interruption, or an unattended permission/form request, the client attempts to cancel the server task. Cancellation and optional cleanup can take additional time beyond the execution timeout.

`--cleanup` deletes the newly created session after foreground execution, including failed or timed-out execution. Cleanup failure returns nonzero and preserves any final reply in the JSON result. It never deletes pre-existing sessions.

`-b` / `--background` submits the prompt and immediately exits after the server acknowledges it. The service continues execution without a waiting client or `systemd-run`. Exit zero means submission succeeded, not that the task ultimately succeeded. No final reply is collected and no session is deleted. `--timeout` and `--cleanup` cannot be combined with background mode. If acknowledgement is lost, inspect the reported session before retrying to avoid duplicate work.

The default working directory is the caller's current directory. `--dir` selects another existing directory accessible to the server. A local deployment can customize this default through configuration.

## Configuration and authentication

Configuration is read from `OC_TASK_CONFIG`, otherwise `$XDG_CONFIG_HOME/oc-task/config.json` (default `~/.config/oc-task/config.json`). For example:

```json
{
  "model": "provider/model",
  "server": "http://127.0.0.1:4096",
  "web_url": "http://127.0.0.1:4096/",
  "directory": "/path/to/workspace",
  "env_file": "/path/to/trusted-service.env"
}
```

All fields are optional, but a model and service password must be supplied somewhere. Models use `provider/model` or `provider/model#variant` syntax.

| Setting | CLI | Environment | Configuration |
| --- | --- | --- | --- |
| Model | `-m`, `--model` | `OC_TASK_MODEL`, then `MODEL` | `model` |
| API endpoint | `--server` | `OC_TASK_SERVER` | `server` |
| Displayed Web URL | `--web-url` | `OC_TASK_WEB_URL` | `web_url` |
| Working directory | `--dir` | `OC_TASK_DIR` | `directory` |
| Credential file | `--env-file` | `OC_TASK_ENV_FILE` | `env_file` |

CLI settings override environment settings, which override configuration. The API endpoint defaults to `http://127.0.0.1:4096`; the Web URL defaults to that endpoint with a trailing slash. `--name` changes the generated task-title prefix. Use `--help` for all options.

Authentication uses HTTP Basic authentication. `OPENCODE_SERVER_PASSWORD` takes precedence over credential files; `OPENCODE_SERVER_USERNAME` defaults to `opencode`. Otherwise the client loads the selected environment file, falling back to `$XDG_CONFIG_HOME/opencode/web.env.gpg`, then `web.env`. These are trusted Bash files and are sourced as code: use only files you control. Credential-file loading requires Bash; `.gpg` files additionally require GnuPG and unattended decryption. Passwords are not passed as command-line arguments. Use HTTPS when accessing a service across an untrusted network.

## Programmatic output

`--stdin` reads the entire prompt from standard input, keeping potentially large or private prompts out of command arguments. Do not combine it with a positional prompt.

`--format json` suppresses progress text and emits one JSON object on stdout after execution or submission. Diagnostics go to stderr. Argument/configuration parsing errors may exit before producing JSON, so callers must check both the exit code and JSON validity.

```json
{
  "session_id": "session-id",
  "title": "task-title",
  "status": "succeeded",
  "model": "provider/model",
  "text": "Final assistant reply",
  "error": null,
  "cleanup": {"requested": true, "deleted": true, "error": null}
}
```

`model` records the selected model reference when available (resolved from the final assistant message on completion). `session_id` and `title` can be null when initialization fails. `status` is `succeeded`, `failed`, `interrupted`, `submitted`, or `error`; `text` is a string and error fields are null or diagnostic strings. A cleanup failure can change status to `error` while retaining `text`. A successful submission has status `submitted` and no final text. Foreground exit zero means successful execution and, when requested, successful cleanup. Timeout exits with 124; interrupted server outcomes exit with 130; other failures return nonzero.

## Tests

The tests launch a local fake HTTP server and execute the actual client in subprocesses. They do not call a model or use production credentials. Temporary test data is created under `/tmp/opencode/`.

```sh
mkdir -p /tmp/opencode
python3 -m unittest discover -s tests -v
```
