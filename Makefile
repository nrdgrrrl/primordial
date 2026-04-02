PYTHON ?= .venv/bin/python

.PHONY: run debug profile test build clean

run:
	$(PYTHON) main.py

debug:
	$(PYTHON) main.py --debug

profile:
	$(PYTHON) main.py --profile

test:
	$(PYTHON) -m pytest -q

build:
	$(PYTHON) build.py

clean:
	rm -rf build dist
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
