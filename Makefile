PYTHON ?= .venv/bin/python

.PHONY: run debug profile build clean

run:
	$(PYTHON) main.py

debug:
	$(PYTHON) main.py --debug

profile:
	$(PYTHON) main.py --profile

build:
	$(PYTHON) build.py

clean:
	rm -rf build dist
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
