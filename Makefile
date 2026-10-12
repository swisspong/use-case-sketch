# Document processing v3: extract -> OCR, step by step.
#
#   make extract              # step 1: save PDF + extraction.json, suggest OCR pages
#   make ocr                  # step 2: OCR the last extracted document
#   make all                  # step 1 then step 2
#
# Override any variable on the command line, e.g.
#   make extract PDF=/path/other.pdf
#   make ocr DOC_ID=b5786b0d1ef84fe0af36c9a727227cb5 PAGES=2,3
#
# Note: `make ocr` sends page images to the preset's remote endpoint (paid call).

# ---- Variables -------------------------------------------------------------
BACKEND  := $(CURDIR)/backend
BIN      := $(BACKEND)/.venv/bin
PYTHON   := $(BIN)/python

PDF      ?= $(CURDIR)/คปภ.pdf
CONFIG   ?= $(BACKEND)/examples/mfec.local.json
DATA_DIR ?= $(BACKEND)/local-documents/v3
PRESET   ?= mfec
PAGES    ?=
DOC_ID   ?=

# Written by `make extract`; used by `make ocr` when DOC_ID is not given.
LAST_DOC_FILE ?= $(DATA_DIR)/.last-document-id

PAGES_ARG = $(if $(PAGES),--pages $(PAGES))

# Resolve DOC_ID at recipe run time (so `make all` picks up the fresh id).
RESOLVE_DOC_ID = id="$(DOC_ID)"; \
	if [ -z "$$id" ] && [ -f "$(LAST_DOC_FILE)" ]; then id=$$(cat "$(LAST_DOC_FILE)"); fi; \
	if [ -z "$$id" ]; then echo "No DOC_ID: run 'make extract' or pass DOC_ID=..." >&2; exit 1; fi

.PHONY: help install extract ocr all show-doc test-v3

help:
	@echo "Targets:"
	@echo "  install   Install backend (editable) into $(BIN)"
	@echo "  extract   Step 1: extract-pdf-text-v3 PDF -> DATA_DIR (saves last document id)"
	@echo "  ocr       Step 2: ocr-document-pages-v3 DOC_ID (default: last extracted)"
	@echo "  all       extract then ocr"
	@echo "  show-doc  List saved pages/OCR attempts of DOC_ID (no text printed)"
	@echo "  test-v3   Run v3 unit + integration tests"
	@echo "Variables: PDF=$(PDF)"
	@echo "           CONFIG=$(CONFIG) PRESET=$(PRESET)"
	@echo "           DATA_DIR=$(DATA_DIR) DOC_ID=$(DOC_ID) PAGES=$(PAGES)"

install:
	uv pip install --python "$(PYTHON)" -e "$(BACKEND)"

extract:
	@mkdir -p "$(dir $(DATA_DIR))"
	@out=$$("$(BIN)/extract-pdf-text-v3" "$(PDF)" --config "$(CONFIG)" --data-dir "$(DATA_DIR)"); \
	status=$$?; echo "$$out"; \
	if [ $$status -eq 0 ]; then \
		echo "$$out" | "$(PYTHON)" -c 'import json,sys; print(json.load(sys.stdin)["document_id"])' > "$(LAST_DOC_FILE)"; \
		echo "document_id saved to $(LAST_DOC_FILE)"; \
	fi; \
	exit $$status

ocr:
	@$(RESOLVE_DOC_ID); \
	echo "OCR document $$id with preset $(PRESET) $(PAGES_ARG)"; \
	"$(BIN)/ocr-document-pages-v3" "$$id" --preset "$(PRESET)" \
		--config "$(CONFIG)" --data-dir "$(DATA_DIR)" $(PAGES_ARG)

all: extract
	@$(MAKE) --no-print-directory ocr

# Summary only: statuses/percentages, never page text.
define SHOW_DOC_PY
import json, os, pathlib
d = pathlib.Path(os.environ["DOC_DIR"])
e = json.loads((d / "extraction.json").read_text())
print("document", d.name, "threshold", e["threshold_percent"])
for p in e["pages"]:
    mark = "ocr_suggested" if p["ocr_suggested"] else "-"
    print(f"  page {p['number']}: {mark} {p['ocr_reason'] or ''} {p['problem_percent']:.2f}%")
ocr = d / "ocr"
for a in sorted(ocr.glob("*.json"), key=os.path.getmtime) if ocr.is_dir() else []:
    pages = json.loads(a.read_text())["pages"]
    print("attempt", a.stem, ", ".join(f"{p['number']}:{p['status']}" for p in pages))
endef
export SHOW_DOC_PY

show-doc:
	@$(RESOLVE_DOC_ID); \
	DOC_DIR="$(DATA_DIR)/$$id" "$(PYTHON)" -c "$$SHOW_DOC_PY"

test-v3:
	cd "$(BACKEND)" && "$(PYTHON)" -m pytest tests/unit/contexts/document_processing/v3 \
		tests/integration/contexts/document_processing/v3 -q
