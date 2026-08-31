PYTHON ?= python3
JING ?= jing
MVN ?= mvn

.PHONY: candidates check check-inputs editorial-gate package registry test validate-overrides

candidates:
	$(PYTHON) scripts/generate-candidates.py

check-inputs:
	$(PYTHON) scripts/check-inputs.py

validate-overrides:
	$(JING) registry/schema/raskovnik-overrides.rng registry/raskovnik-overrides.xml

test:
	$(PYTHON) -m unittest discover -s tests -v

check: check-inputs validate-overrides test
	$(PYTHON) scripts/generate-candidates.py --check
	$(MVN) -o validate

editorial-gate: check
	$(PYTHON) scripts/check-editorial-gate.py

registry: editorial-gate
	$(PYTHON) scripts/build-registry.py

package: registry
	$(MVN) -o package
