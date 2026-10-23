PYTHON ?= python3
NODE ?= node
OPENCODE_CONFIG_DIR ?= $(if $(XDG_CONFIG_HOME),$(XDG_CONFIG_HOME),$(HOME)/.config)/opencode
OPENCODE2_PLUGIN_DIR ?= $(OPENCODE_CONFIG_DIR)/plugins/logbook-v2

.PHONY: check check-codex check-opencode2 install install-codex install-opencode install-opencode1 install-opencode2

check: check-codex check-opencode2

check-codex:
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

check-opencode2:
	$(NODE) --test opencode2/tests/*.test.mjs

# Preserve the original install-opencode target as the V1 installer.
install-opencode1: install-opencode

install-opencode2:
	@test ! -e "$(OPENCODE_CONFIG_DIR)/plugins/logbook.ts" || { echo "disable the V1 logbook.ts before installing the V2 plugin" >&2; exit 1; }
	@for file in index.ts core.mjs package.json; do \
		test ! -e "$(OPENCODE2_PLUGIN_DIR)/$$file" || cmp -s "opencode2/$$file" "$(OPENCODE2_PLUGIN_DIR)/$$file" || { echo "refusing to overwrite $(OPENCODE2_PLUGIN_DIR)/$$file" >&2; exit 1; }; \
	done
	install -d -m 700 "$(OPENCODE2_PLUGIN_DIR)"
	install -m 600 opencode2/index.ts opencode2/core.mjs opencode2/package.json "$(OPENCODE2_PLUGIN_DIR)/"
