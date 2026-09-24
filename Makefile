PYTHON ?= python3
MVN ?= mvn

.PHONY: check test package prepare-release
check:
	$(PYTHON) scripts/registry.py check
	$(PYTHON) -m unittest discover -s tests -v
	$(MVN) -o validate

test:
	$(PYTHON) -m unittest discover -s tests -v

package: check
	$(MVN) -o package

prepare-release:
	$(PYTHON) scripts/prepare_release.py
	$(MAKE) package
