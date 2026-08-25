# OdooGit — development tasks.
#
# Every target runs against the docker compose stack in this directory.
# `make help` lists them.

DB       ?= odoo
# Every addon in this repository. Adding a module means adding it here and
# nothing else: install, upgrade, test and lint all read this list.
MODULES  ?= odoogit
MODULE   ?= $(firstword $(MODULES))
COMPOSE  := docker compose
ODOO     := $(COMPOSE) exec -T odoo odoo
DBFLAGS  := --db_host=postgres --db_user=odoo --db_password=odoo --workers=0
RUFF     := uvx ruff

.DEFAULT_GOAL := help
.PHONY: help build up down clean logs shell psql install upgrade test test-one \
        qa lint fmt xml check release-check versions

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

test: ## Run the full test suite
	$(ODOO) -d $(DB) --test-enable --test-tags /$(MODULE) \
	  --stop-after-init --http-port=8070 $(DBFLAGS)

test-one: ## Run one class or method: make test-one T=TestJsonApi
	$(ODOO) -d $(DB) --test-enable --test-tags /$(MODULE):$(T) \
	  --stop-after-init --http-port=8070 $(DBFLAGS)

qa: ## Browser QA flows (needs the stack up and exactly one database)
	python3 qa/run.py

check: xml lint upgrade test ## What CI runs — do this before pushing

release-check: xml lint ## Full pre-tag gate: clean install, upgrade, tests, QA
	$(COMPOSE) exec -T postgres psql -U odoo -d postgres \
	  -c "DROP DATABASE IF EXISTS release_check;" >/dev/null
	$(ODOO) -d release_check -i $(MODULE) --stop-after-init $(DBFLAGS)
	$(COMPOSE) exec -T postgres psql -U odoo -d postgres \
	  -c "DROP DATABASE IF EXISTS release_check;" >/dev/null
	@$(MAKE) --no-print-directory upgrade test
	@echo "--- browser QA (a second database would break it; dropped above) ---"
	@$(MAKE) --no-print-directory qa

versions: ## Show what is actually running
	@echo "odoo:       $$($(COMPOSE) exec -T odoo odoo --version 2>/dev/null)"
	@echo "postgres:   $$($(COMPOSE) exec -T postgres postgres --version 2>/dev/null)"
	@echo "git:        $$($(COMPOSE) exec -T odoo git --version 2>/dev/null)"
	@echo "GitPython:  $$($(COMPOSE) exec -T odoo python3 -c 'import git;print(git.__version__)' 2>/dev/null)"
	@echo "module:     $$(python3 -c "import ast;s=open('odoogit/__manifest__.py').read();print(ast.literal_eval(s[s.index('{'):])['version'])")"
