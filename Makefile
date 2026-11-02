ifeq ($(OS),Windows_NT)
PYTHON ?= .venv/Scripts/python.exe
else
PYTHON ?= .venv/bin/python
endif

.PHONY: test fetch-data check-data check-references eda eval
test:
	"$(PYTHON)" tasks.py test
fetch-data:
	"$(PYTHON)" tasks.py fetch-data
check-data:
	"$(PYTHON)" tasks.py check-data
check-references:
	"$(PYTHON)" tasks.py check-references
eda:
	"$(PYTHON)" tasks.py eda
eval:
	"$(PYTHON)" tasks.py eval --baseline --split dev
