PYTHON ?= python3

.PHONY: check install install-codex install-opencode

check:
	$(PYTHON) -m json.tool codex/hooks.json >/dev/null
	$(PYTHON) -m json.tool codex/config.example.json >/dev/null
	$(PYTHON) -m unittest discover -s tests -v

install: install-codex install-opencode

install-codex:
	install -d -m 700 "$(HOME)/.agents/logbook-hooks"
	@test ! -e "$(HOME)/.agents/logbook-hooks/codex_logbook.py" || cmp -s codex/codex_logbook.py "$(HOME)/.agents/logbook-hooks/codex_logbook.py" || { echo "refusing to overwrite $(HOME)/.agents/logbook-hooks/codex_logbook.py" >&2; exit 1; }
	install -m 700 codex/codex_logbook.py "$(HOME)/.agents/logbook-hooks/codex_logbook.py"
	test -e "$(HOME)/.agents/logbook-hooks/config.json" || install -m 600 codex/config.example.json "$(HOME)/.agents/logbook-hooks/config.json"
	install -d -m 700 "$(HOME)/.codex"
	@test ! -e "$(HOME)/.codex/hooks.json" || cmp -s codex/hooks.json "$(HOME)/.codex/hooks.json" || { echo "refusing to overwrite $(HOME)/.codex/hooks.json; merge it manually" >&2; exit 1; }
	install -m 600 codex/hooks.json "$(HOME)/.codex/hooks.json"

install-opencode:
	install -d -m 700 "$(HOME)/.config/opencode/plugins"
	@test ! -e "$(HOME)/.config/opencode/plugins/logbook.ts" || cmp -s opencode/logbook.ts "$(HOME)/.config/opencode/plugins/logbook.ts" || { echo "refusing to overwrite $(HOME)/.config/opencode/plugins/logbook.ts" >&2; exit 1; }
	install -m 600 opencode/logbook.ts "$(HOME)/.config/opencode/plugins/logbook.ts"
