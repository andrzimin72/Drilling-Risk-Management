# =============================================================================
# Drilling Risk Management System — Makefile
# Version: 1.0.0 (Enterprise Edition)
# =============================================================================

.PHONY: help install install-dev test test-coverage lint format clean \
        run-dashboard run-server run-demo docker-build docker-run docker-stop \
        docker-logs setup venv activate

# Variables
PYTHON := python3
PIP := pip3
VENV := .venv
VENV_BIN := $(VENV)/bin
PYTHON_VENV := $(VENV_BIN)/python
PIP_VENV := $(VENV_BIN)/pip
STREAMLIT := $(VENV_BIN)/streamlit
PYTEST := $(VENV_BIN)/pytest
BLACK := $(VENV_BIN)/black
RUFF := $(VENV_BIN)/ruff
DOCKER_IMAGE := oil-gas-swarm
DOCKER_TAG := 2.0.0

# Colors for terminal output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

# =============================================================================
# Help
# =============================================================================

help: ## Show this help message
	@echo "$(BLUE)Oil & Gas Risk Management System — Available commands:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Examples:$(NC)"
	@echo "  make setup              # Initial project setup"
	@echo "  make run-dashboard      # Start Streamlit dashboard"
	@echo "  make test               # Run all tests"
	@echo "  make docker-build       # Build Docker image"

# =============================================================================
# Setup & Installation
# =============================================================================

setup: venv install install-dev ## Complete project setup (venv + dependencies)
	@echo "$(GREEN)✓ Project setup complete!$(NC)"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Copy .env.example to .env and fill in your API keys"
	@echo "  2. Run: make run-dashboard"
	@echo "  3. Open: http://localhost:8501"

venv: ## Create Python virtual environment
	@echo "$(BLUE)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV)
	@echo "$(GREEN)✓ Virtual environment created at $(VENV)$(NC)"

install: venv ## Install production dependencies
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	$(PIP_VENV) install --upgrade pip
	$(PIP_VENV) install -r requirements.txt
	@echo "$(GREEN)✓ Production dependencies installed$(NC)"

install-dev: venv ## Install development dependencies (testing, linting)
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	$(PIP_VENV) install pytest pytest-asyncio pytest-cov black ruff mypy
	@echo "$(GREEN)✓ Development dependencies installed$(NC)"

activate: ## Show command to activate virtual environment
	@echo "$(YELLOW)To activate the virtual environment, run:$(NC)"
	@echo "  source $(VENV)/bin/activate  # Linux/Mac"
	@echo "  $(VENV)\\Scripts\\activate     # Windows"

# =============================================================================
# Testing
# =============================================================================

test: ## Run all tests
	@echo "$(BLUE)Running tests...$(NC)"
	$(PYTEST) tests/ -v

test-coverage: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	$(PYTEST) tests/ --cov=skills --cov=swarms --cov-report=term-missing --cov-report=html
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/$(NC)"
	@echo "  Open: htmlcov/index.html"

test-risk: ## Run risk management tests only
	@echo "$(BLUE)Running risk management tests...$(NC)"
	$(PYTEST) tests/test_risk_*.py -v

test-parsers: ## Run parser tests only
	@echo "$(BLUE)Running parser tests...$(NC)"
	$(PYTEST) tests/test_*_parser.py -v

test-swarm: ## Run swarm integration tests
	@echo "$(BLUE)Running swarm tests...$(NC)"
	$(PYTEST) tests/test_swarm.py tests/test_e2e_swarm.py -v

# =============================================================================
# Code Quality
# =============================================================================

lint: ## Run linters (ruff)
	@echo "$(BLUE)Running linters...$(NC)"
	$(RUFF) check skills/ swarms/ tests/
	@echo "$(GREEN)✓ Linting complete$(NC)"

format: ## Format code with black
	@echo "$(BLUE)Formatting code...$(NC)"
	$(BLACK) skills/ swarms/ tests/ --line-length 100
	@echo "$(GREEN)✓ Code formatted$(NC)"

format-check: ## Check code formatting without making changes
	@echo "$(BLUE)Checking code formatting...$(NC)"
	$(BLACK) skills/ swarms/ tests/ --check --line-length 100

type-check: ## Run type checking with mypy
	@echo "$(BLUE)Running type checks...$(NC)"
	$(VENV_BIN)/mypy skills/ swarms/ --ignore-missing-imports
	@echo "$(GREEN)✓ Type checking complete$(NC)"

# =============================================================================
# Running the Application
# =============================================================================

run-dashboard: ## Start Streamlit dashboard
	@echo "$(BLUE)Starting Streamlit dashboard...$(NC)"
	@echo "$(GREEN)Dashboard will be available at: http://localhost:8501$(NC)"
	$(STREAMLIT) run dashboard.py --server.port=8501 --server.address=0.0.0.0

run-server: ## Start MCP server
	@echo "$(BLUE)Starting MCP server...$(NC)"
	$(PYTHON_VENV) -m swarms.server

run-demo: ## Run demo script (all demos)
	@echo "$(BLUE)Running demo...$(NC)"
	$(PYTHON_VENV) -m swarms.demo

run-demo-risk: ## Run risk management demo
	@echo "$(BLUE)Running risk management demo...$(NC)"
	$(PYTHON_VENV) -m swarms.demo risk

run-demo-russian: ## Run Russian/Metric demo
	@echo "$(BLUE)Running Russian/Metric demo...$(NC)"
	$(PYTHON_VENV) -m swarms.demo russian

run-demo-checkpoint: ## Run checkpoint recovery demo
	@echo "$(BLUE)Running checkpoint recovery demo...$(NC)"
	$(PYTHON_VENV) -m swarms.demo checkpoint

# =============================================================================
# Docker
# =============================================================================

docker-build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .
	@echo "$(GREEN)✓ Docker image built: $(DOCKER_IMAGE):$(DOCKER_TAG)$(NC)"

docker-run: ## Run Docker container (dashboard + MCP server)
	@echo "$(BLUE)Starting Docker container...$(NC)"
	@echo "$(GREEN)Dashboard: http://localhost:8501$(NC)"
	@echo "$(GREEN)MCP Server: http://localhost:8342$(NC)"
	docker run -d \
		--name oil-gas-swarm \
		-p 8501:8501 \
		-p 8342:8342 \
		--env-file .env \
		-v $(PWD)/.cache:/app/.cache \
		-v $(PWD)/data/input:/app/input:ro \
		-v $(PWD)/data/output:/app/output \
		$(DOCKER_IMAGE):$(DOCKER_TAG)
	@echo "$(GREEN)✓ Container started$(NC)"
	@echo "  View logs: make docker-logs"
	@echo "  Stop: make docker-stop"

docker-run-monitoring: ## Run with Jaeger monitoring
	@echo "$(BLUE)Starting with monitoring (Jaeger)...$(NC)"
	docker-compose --profile monitoring up -d
	@echo "$(GREEN)✓ Services started$(NC)"
	@echo "  Dashboard: http://localhost:8501"
	@echo "  Jaeger UI: http://localhost:16686"

docker-stop: ## Stop Docker container
	@echo "$(BLUE)Stopping Docker container...$(NC)"
	docker stop oil-gas-swarm || true
	docker rm oil-gas-swarm || true
	@echo "$(GREEN)✓ Container stopped$(NC)"

docker-logs: ## View Docker container logs
	docker logs -f oil-gas-swarm

docker-compose-up: ## Start all services with docker-compose
	@echo "$(BLUE)Starting services with docker-compose...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓ Services started$(NC)"

docker-compose-down: ## Stop all docker-compose services
	@echo "$(BLUE)Stopping docker-compose services...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ Services stopped$(NC)"

docker-test: ## Run tests inside Docker container
	@echo "$(BLUE)Running tests in Docker...$(NC)"
	docker run --rm $(DOCKER_IMAGE):$(DOCKER_TAG) pytest tests/ -v

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Remove Python cache files
	@echo "$(BLUE)Cleaning Python cache files...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Cache cleaned$(NC)"

clean-test: ## Remove test artifacts
	@echo "$(BLUE)Cleaning test artifacts...$(NC)"
	rm -rf .pytest_cache htmlcov .coverage coverage.xml
	@echo "$(GREEN)✓ Test artifacts cleaned$(NC)"

clean-cache: ## Remove application cache
	@echo "$(BLUE)Cleaning application cache...$(NC)"
	rm -rf .cache/
	@echo "$(GREEN)✓ Cache cleaned$(NC)"

clean-all: clean clean-test clean-cache ## Remove all generated files
	@echo "$(GREEN)✓ All generated files removed$(NC)"

clean-venv: ## Remove virtual environment
	@echo "$(YELLOW)Removing virtual environment...$(NC)"
	rm -rf $(VENV)
	@echo "$(GREEN)✓ Virtual environment removed$(NC)"

# =============================================================================
# Database Operations
# =============================================================================

db-backup: ## Backup SQLite databases
	@echo "$(BLUE)Backing up databases...$(NC)"
	@mkdir -p backups/$$(date +%Y%m%d)
	@for db in .cache/*.db; do \
		if [ -f "$$db" ]; then \
			sqlite3 "$$db" ".backup 'backups/$$(date +%Y%m%d)/$$(basename $$db)'"; \
			echo "  Backed up: $$db"; \
		fi; \
	done
	@echo "$(GREEN)✓ Databases backed up to backups/$$(date +%Y%m%d)/$(NC)"

db-vacuum: ## Vacuum SQLite databases (optimize size)
	@echo "$(BLUE)Vacuuming databases...$(NC)"
	@for db in .cache/*.db; do \
		if [ -f "$$db" ]; then \
			sqlite3 "$$db" "VACUUM;"; \
			echo "  Vacuumed: $$db"; \
		fi; \
	done
	@echo "$(GREEN)✓ Databases optimized$(NC)"

# =============================================================================
# Documentation
# =============================================================================

docs: ## Generate documentation (if sphinx is installed)
	@echo "$(BLUE)Generating documentation...$(NC)"
	@if [ -f "docs/conf.py" ]; then \
		$(VENV_BIN)/sphinx-build -b html docs/ docs/_build/html; \
		echo "$(GREEN)✓ Documentation generated in docs/_build/html/$(NC)"; \
	else \
		echo "$(YELLOW)Sphinx not configured. See docs/ folder for markdown documentation.$(NC)"; \
	fi

# =============================================================================
# Development Utilities
# =============================================================================

check: lint format-check test ## Run all checks (lint, format, test)
	@echo "$(GREEN)✓ All checks passed$(NC)"

pre-commit: lint format test ## Run pre-commit checks
	@echo "$(GREEN)✓ Pre-commit checks passed$(NC)"

deps-tree: ## Show dependency tree
	@echo "$(BLUE)Dependency tree:$(NC)"
	$(PIP_VENV) tree

outdated: ## Check for outdated packages
	@echo "$(BLUE)Checking for outdated packages...$(NC)"
	$(PIP_VENV) list --outdated

update-deps: ## Update all dependencies
	@echo "$(BLUE)Updating dependencies...$(NC)"
	$(PIP_VENV) install --upgrade -r requirements.txt
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

# =============================================================================
# Production
# =============================================================================

production-build: ## Build for production
	@echo "$(BLUE)Building for production...$(NC)"
	make clean
	make test
	make docker-build
	@echo "$(GREEN)✓ Production build complete$(NC)"

production-deploy: ## Deploy to production (requires docker-compose)
	@echo "$(BLUE)Deploying to production...$(NC)"
	make docker-compose-down
	make docker-build
	make docker-compose-up
	@echo "$(GREEN)✓ Production deployment complete$(NC)"

# =============================================================================
# Default target
# =============================================================================

.DEFAULT_GOAL := help