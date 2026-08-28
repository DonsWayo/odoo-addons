# Git Hosting — development tasks.
#
# Every target runs against the docker compose stack in this directory.
# `make help` lists them.

DB       ?= odoo
# Every addon in this repository. Adding a module means adding it here and
# nothing else: install, upgrade, test and lint all read this list.
MODULES  ?= dw_git
MODULE   ?= $(firstword $(MODULES))
COMPOSE  := docker compose
ODOO     := $(COMPOSE) exec -T odoo odoo
DBFLAGS  := --db_host=postgres --db_user=odoo --db_password=odoo --workers=0
RUFF     := uvx ruff

.DEFAULT_GOAL := help
.PHONY: help build up down clean logs shell psql install upgrade test test-one \
        qa lint fmt xml assets check release-check drop-release-check versions i18n seed browser mail mail-clear

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

## ---------------------------------------------------------------- stack

build: ## Rebuild the odoo image (needed after any code change)
	$(COMPOSE) build odoo

up: ## Start the stack
	$(COMPOSE) up -d
	@until $(COMPOSE) exec -T postgres pg_isready -U odoo >/dev/null 2>&1; do sleep 2; done
	@echo "ready — http://localhost:8069 (admin/admin)"

down: ## Stop the stack, keep the data
	$(COMPOSE) down

clean: ## Stop the stack and delete its volumes
	$(COMPOSE) down -v

logs: ## Tail the odoo log
	$(COMPOSE) logs -f odoo

shell: ## Open an odoo shell (remember: it does not auto-commit)
	$(COMPOSE) exec odoo odoo shell -d $(DB) $(DBFLAGS) --no-http

psql: ## Open psql on the database
	$(COMPOSE) exec postgres psql -U odoo -d $(DB)

## ---------------------------------------------------------------- module

install: ## Install every module into $(DB) (creates it if absent)
	$(ODOO) -d $(DB) -i $(shell echo $(MODULES) | tr ' ' ',') --stop-after-init $(DBFLAGS)

upgrade: build ## Rebuild, then upgrade the module in $(DB)
	$(COMPOSE) up -d --force-recreate odoo
	@until $(COMPOSE) exec -T postgres pg_isready -U odoo >/dev/null 2>&1; do sleep 2; done
	$(ODOO) -d $(DB) -u $(shell echo $(MODULES) | tr ' ' ',') --stop-after-init $(DBFLAGS)

i18n: build ## Regenerate $(MODULE)/i18n/$(MODULE).pot from the running module
	$(COMPOSE) up -d --force-recreate odoo
	@until $(COMPOSE) exec -T postgres pg_isready -U odoo >/dev/null 2>&1; do sleep 2; done
	@# Odoo 19 moved this behind an `i18n export` subcommand, which reads the
	@# database rather than parsing source — it picks up field labels, selection
	@# values and view arch that a static scan of the source cannot see.
	@# It takes libpq env vars, not the --db_* flags the other targets use.
	$(COMPOSE) exec -T -e PGHOST=postgres -e PGUSER=odoo -e PGPASSWORD=odoo odoo \
	  odoo i18n export -d $(DB) -o /tmp/$(MODULE).pot $(MODULE)
	@# The export lands inside the container; copy it back or the target
	@# silently produces nothing a human ever sees.
	$(COMPOSE) cp odoo:/tmp/$(MODULE).pot $(MODULE)/i18n/$(MODULE).pot
	@echo "wrote $(MODULE)/i18n/$(MODULE).pot ($$(grep -c '^msgid ' $(MODULE)/i18n/$(MODULE).pot) entries)"

seed: ## Seed realistic demo data (DW_GIT_RESET=1 rebuilds from scratch)
	@# Every repository it creates is a real bare repo with real commits, and
	@# its pull requests get their diffs through the same path a push uses.
	@# If a diff does not render after this, that is a bug, not a fixture gap.
	$(COMPOSE) cp qa/seed.py odoo:/tmp/qa-seed.py
	$(COMPOSE) exec -T -e DW_GIT_RESET=$(DW_GIT_RESET) odoo bash -c \
	  'odoo shell -d $(DB) $(DBFLAGS) --no-http < /tmp/qa-seed.py' 2>&1 \
	  | grep -E '^SEED|^  ' || true

mail: ## Open the local mailbox that catches every outgoing notification
	@# Odoo queues mail with no SMTP server and nobody ever sees it. mailpit
	@# catches everything so the rendered message can actually be read —
	@# which is the only way the notification bugs here were ever visible.
	@echo "  mailbox: http://localhost:8025"
	@curl -s http://localhost:8025/api/v1/messages 2>/dev/null \
	  | python3 -c "import sys,json; d=json.load(sys.stdin); print('  messages: %d' % d.get('total',0)); [print('    -> %s | %s' % (', '.join(x.get('Address','') for x in m.get('To',[])), m.get('Subject',''))) for m in d.get('messages',[])[:10]]" \
	  2>/dev/null || echo "  (mailpit not running — 'make up' first)"

mail-clear: ## Empty the local mailbox
	@curl -s -X DELETE http://localhost:8025/api/v1/messages >/dev/null && echo "  mailbox emptied"

browser: ## Report whether browser tours can actually run here
	@# Odoo SKIPS tours when Chrome or websocket-client is missing and still
	@# reports "0 failed". Every tour in this module was skipped for the whole
	@# life of the project without anyone noticing. This says so out loud.
	@$(COMPOSE) exec -T odoo python3 -c "import websocket" 2>/dev/null \
	  && echo "  websocket-client: present" \
	  || echo "  websocket-client: MISSING - all tours will be skipped"
	@$(COMPOSE) exec -T odoo sh -c 'command -v google-chrome google-chrome-stable chromium 2>/dev/null | head -1' \
	  | grep -q . \
	  && echo "  chrome:           present - tours will RUN" \
	  || echo "  chrome:           MISSING - tours will be SKIPPED, not passed (expected on arm64; CI runs amd64)"

## ---------------------------------------------------------------- checks

lint: ## Ruff over the addon
	$(RUFF) check --config ruff.toml $(MODULES)

fmt: ## Ruff autofix
	$(RUFF) check --config ruff.toml $(MODULES) --fix

xml: ## Every XML file parses (do this before `make build`)
	@python3 -c "from xml.etree import ElementTree as ET; import glob; \
	  fs=[f for m in '$(MODULES)'.split() for f in glob.glob(m+'/**/*.xml', recursive=True)]; \
	  [ET.parse(f) for f in fs]; \
	  print(f'XML OK ({len(fs)} files)')"

assets: ## Every static asset referenced anywhere actually exists
	@# Checks BOTH the manifest bundles and the paths hardcoded in JS and
	@# fetched with loadJS/loadCSS. A manifest-only check reported "OK" while
	@# the diff viewer's highlight.js was never fetched at all.
	@python3 qa/check_assets.py

test: upgrade ## Run the full test suite
	@# Depends on `upgrade`, not just `build`. Rebuilding the image reloads
	@# Python, but security rules, views and mail templates are DATA: without
	@# -u they keep whatever the database was last loaded with, so the suite
	@# happily tests record rules you edited an hour ago. That cost a real
	@# debugging session — a company-scoping fix looked broken because the
	@# database still held the pre-fix rule.
	$(ODOO) -d $(DB) --test-enable --test-tags /$(MODULE) \
	  --stop-after-init --http-port=8070 $(DBFLAGS)

test-one: upgrade ## Run one class or method: make test-one T=TestJsonApi
	$(ODOO) -d $(DB) --test-enable --test-tags /$(MODULE):$(T) \
	  --stop-after-init --http-port=8070 $(DBFLAGS)

qa: ## Browser QA flows (needs the stack up and exactly one database)
	python3 qa/run.py

check: xml assets lint upgrade test ## What CI runs — do this before pushing

release-check: xml lint ## Full pre-tag gate: clean install, upgrade, tests, QA
	@$(MAKE) --no-print-directory drop-release-check
	$(ODOO) -d release_check -i $(MODULE) --stop-after-init $(DBFLAGS)
	@$(MAKE) --no-print-directory drop-release-check
	@$(MAKE) --no-print-directory upgrade test
	@echo "--- browser QA (a second database would break it; dropped above) ---"
	@$(MAKE) --no-print-directory qa

drop-release-check: ## Drop the throwaway release_check database
	@# Odoo logs "Closed N connections" before postgres has actually released
	@# them, so a bare DROP loses a race against its own teardown and fails
	@# with "database is being accessed by other users" — an entire release
	@# gate falling over on timing. Terminate first, then drop.
	@$(COMPOSE) exec -T postgres psql -U odoo -d postgres -c \
	  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
	   WHERE datname = 'release_check';" >/dev/null 2>&1 || true
	@$(COMPOSE) exec -T postgres psql -U odoo -d postgres \
	  -c "DROP DATABASE IF EXISTS release_check;" >/dev/null

versions: ## Show what is actually running
	@echo "odoo:       $$($(COMPOSE) exec -T odoo odoo --version 2>/dev/null)"
	@echo "postgres:   $$($(COMPOSE) exec -T postgres postgres --version 2>/dev/null)"
	@echo "git:        $$($(COMPOSE) exec -T odoo git --version 2>/dev/null)"
	@echo "GitPython:  $$($(COMPOSE) exec -T odoo python3 -c 'import git;print(git.__version__)' 2>/dev/null)"
	@echo "module:     $$(python3 -c "import ast;s=open('dw_git/__manifest__.py').read();print(ast.literal_eval(s[s.index('{'):])['version'])")"
