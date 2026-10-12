#!/usr/bin/env bash
.PHONY: help install dev test lint listen serve gallery docker docker-run tunnel clean

help:
	@echo "make install    - install package (editable)"
	@echo "make dev        - install with dev+audio extras"
	@echo "make test       - run tests"
	@echo "make lint       - ruff check"
	@echo "make listen     - record 8s and make a postcard"
	@echo "make serve      - run the local web app (http://127.0.0.1:8000)"
	@echo "make gallery    - build the static HTML gallery"
	@echo "make docker     - build the gallery image"
	@echo "make docker-run - run the gallery image locally"
	@echo "make tunnel     - expose the local gallery on a public URL (no account)"
	@echo "make clean      - remove build/test caches"

install:
	pip install -e .

dev:
	pip install -e ".[audio,dev]"

test:
	python -m pytest -q

lint:
	ruff check src tests

listen:
	wanderear listen --seconds 8

serve:
	python web/server.py

gallery:
	wanderear gallery

docker:
	docker build -f Dockerfile -t wanderear .

docker-run: docker
	docker run --rm -p 8000:8000 -e HOST=0.0.0.0 wanderear

tunnel:
	scripts/tunnel.sh

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
