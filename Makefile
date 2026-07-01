DOCS_RUN = uv run --python 3.12 --with-requirements docs/requirements.txt

.PHONY: help docs-serve docs-build docs-check docs-clean

help:
	@echo "Documentation targets:"
	@echo "  make docs-serve  - live preview with auto-reload at http://127.0.0.1:8000/"
	@echo "  make docs-build  - build the static site into ./site/"
	@echo "  make docs-check  - build with --strict to fail on broken docs or links"
	@echo "  make docs-clean  - remove the built site"

docs-serve:
	$(DOCS_RUN) mkdocs serve

docs-build:
	$(DOCS_RUN) mkdocs build

docs-check:
	$(DOCS_RUN) mkdocs build --strict

docs-clean:
	rm -rf site
