# Placeholder; grows each phase.
VM=fabricx-lab
# How to reach Docker/Containerlab. Mac: through the OrbStack VM. CI runner: make RUN=sudo ...
RUN ?= orb -m $(VM) sudo
hello-up:
	$(RUN) containerlab deploy -t $(CURDIR)/labs/hello/hello.clab.yml
hello-down:
	$(RUN) containerlab destroy -t $(CURDIR)/labs/hello/hello.clab.yml --cleanup

# ---- fabric ----
gen:
	.venv/bin/fabricx generate
fabric-up: gen
	$(RUN) containerlab deploy -t $(CURDIR)/generated/fabricx.clab.yml
fabric-down:
	$(RUN) containerlab destroy -t $(CURDIR)/generated/fabricx.clab.yml --cleanup
unit:
	.venv/bin/pytest tests/unit -q
lab-test:
	.venv/bin/pytest tests/lab -q -m lab

# ---- Phase 4: one command ----
up: fabric-up
	@echo "waiting for the fabric to converge..."; sleep 40
down: fabric-down
# `make test` = lint + types + unit + live lab tests (JUnit XML) + validation report + drift check + traceability matrix.
# Non-zero exit on ANY failure.
lint:
	.venv/bin/ruff check .
	.venv/bin/mypy
test: lint
	.venv/bin/pytest tests -q -m "not resilience" --junitxml=artifacts/junit.xml
	.venv/bin/fabricx validate
	.venv/bin/fabricx drift
	.venv/bin/fabricx trace
smoke:
	.venv/bin/pytest tests -q -m smoke

# On demand: inject and restore every fault, then check the fabric is healthy again (about 10 minutes).
resilience:
	.venv/bin/pytest tests -q -m resilience --junitxml=artifacts/junit_resilience.xml
# Blind drill over all faults (about 15 minutes): results in experiments/E9/results/
drill:
	.venv/bin/fabricx drill --seed 1
