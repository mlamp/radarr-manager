# Makefile for radarr-manager
#
# Versioning Pipeline:
#   1. Single source of truth: pyproject.toml contains the version
#   2. Git tags: v{VERSION} (e.g., v1.12.0)
#   3. Docker images: {VERSION} (e.g., 1.12.0) + latest
#
# Usage:
#   make version          - Show current version
#   make bump-patch       - Bump patch version (1.12.0 -> 1.12.1)
#   make bump-minor       - Bump minor version (1.12.0 -> 1.13.0)
#   make bump-major       - Bump major version (1.12.0 -> 2.0.0)
#   make tag              - Create git tag from current version
#   make docker-build     - Build Docker image
#   make docker-push      - Push Docker image to registry
#   make release          - Full release: tag + build + push

.PHONY: version bump-patch bump-minor bump-major tag docker-build docker-push release \
        lint test clean help check-clean check-version

# Configuration
DOCKER_REPO := mlamp/radarr-manager
PLATFORMS := linux/amd64,linux/arm64

# Extract version from pyproject.toml
VERSION := $(shell python3 -c "import re; print(re.search(r'version = \"([^\"]+)\"', open('pyproject.toml').read()).group(1))")

# Default target
.DEFAULT_GOAL := help

help:
	@echo "radarr-manager build and release tools"
	@echo ""
	@echo "Version Management:"
	@echo "  make version       - Show current version ($(VERSION))"
	@echo "  make bump-patch    - Bump patch version (x.y.Z)"
	@echo "  make bump-minor    - Bump minor version (x.Y.0)"
	@echo "  make bump-major    - Bump major version (X.0.0)"
	@echo ""
	@echo "Release:"
	@echo "  make tag           - Create git tag v$(VERSION)"
	@echo "  make docker-build  - Build Docker image $(DOCKER_REPO):$(VERSION)"
	@echo "  make docker-push   - Push Docker image to registry"
	@echo "  make release       - Full release pipeline"
	@echo ""
	@echo "Development:"
	@echo "  make lint          - Run linters (ruff, black)"
	@echo "  make test          - Run tests"
	@echo "  make clean         - Clean build artifacts"

version:
	@echo "Current version: $(VERSION)"
	@echo "Git tag: v$(VERSION)"
	@echo "Docker image: $(DOCKER_REPO):$(VERSION)"

# Bump version helpers
bump-patch:
	@python3 -c "\
import re; \
f = open('pyproject.toml', 'r'); content = f.read(); f.close(); \
version = re.search(r'version = \"([^\"]+)\"', content).group(1); \
parts = version.split('.'); \
parts[2] = str(int(parts[2]) + 1); \
new_version = '.'.join(parts); \
content = re.sub(r'version = \"[^\"]+\"', f'version = \"{new_version}\"', content); \
f = open('pyproject.toml', 'w'); f.write(content); f.close(); \
print(f'Bumped version: {version} -> {new_version}')"
	@echo "Don't forget to: git add pyproject.toml && git commit -m 'chore: bump version to $$(make -s version-only)'"

bump-minor:
	@python3 -c "\
import re; \
f = open('pyproject.toml', 'r'); content = f.read(); f.close(); \
version = re.search(r'version = \"([^\"]+)\"', content).group(1); \
parts = version.split('.'); \
parts[1] = str(int(parts[1]) + 1); \
parts[2] = '0'; \
new_version = '.'.join(parts); \
content = re.sub(r'version = \"[^\"]+\"', f'version = \"{new_version}\"', content); \
f = open('pyproject.toml', 'w'); f.write(content); f.close(); \
print(f'Bumped version: {version} -> {new_version}')"
	@echo "Don't forget to: git add pyproject.toml && git commit -m 'chore: bump version to $$(make -s version-only)'"

bump-major:
	@python3 -c "\
import re; \
f = open('pyproject.toml', 'r'); content = f.read(); f.close(); \
version = re.search(r'version = \"([^\"]+)\"', content).group(1); \
parts = version.split('.'); \
parts[0] = str(int(parts[0]) + 1); \
parts[1] = '0'; \
parts[2] = '0'; \
new_version = '.'.join(parts); \
content = re.sub(r'version = \"[^\"]+\"', f'version = \"{new_version}\"', content); \
f = open('pyproject.toml', 'w'); f.write(content); f.close(); \
print(f'Bumped version: {version} -> {new_version}')"
	@echo "Don't forget to: git add pyproject.toml && git commit -m 'chore: bump version to $$(make -s version-only)'"

version-only:
	@echo "$(VERSION)"

# Check working directory is clean
check-clean:
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "Error: Working directory is not clean. Commit or stash changes first."; \
		git status --short; \
		exit 1; \
	fi

# Check if tag already exists
check-version:
	@if git rev-parse "v$(VERSION)" >/dev/null 2>&1; then \
		echo "Error: Tag v$(VERSION) already exists."; \
		echo "Use 'make bump-patch' or 'make bump-minor' to increment version first."; \
		exit 1; \
	fi

# Create git tag
tag: check-clean check-version
	@echo "Creating git tag v$(VERSION)..."
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	@echo "Tag v$(VERSION) created. Push with: git push origin v$(VERSION)"

# Docker build (multi-arch)
docker-build:
	@echo "Building Docker image $(DOCKER_REPO):$(VERSION)..."
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(DOCKER_REPO):$(VERSION) \
		-t $(DOCKER_REPO):latest \
		--load \
		.
	@echo "Built $(DOCKER_REPO):$(VERSION)"

# Docker build and push (multi-arch)
docker-push:
	@echo "Building and pushing Docker image $(DOCKER_REPO):$(VERSION)..."
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(DOCKER_REPO):$(VERSION) \
		-t $(DOCKER_REPO):latest \
		--push \
		.
	@echo "Pushed $(DOCKER_REPO):$(VERSION) and $(DOCKER_REPO):latest"

# Full release pipeline
release: check-clean check-version
	@echo "=========================================="
	@echo "Releasing v$(VERSION)"
	@echo "=========================================="
	@echo ""
	@echo "Step 1/3: Creating git tag..."
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	@echo ""
	@echo "Step 2/3: Building and pushing Docker image..."
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(DOCKER_REPO):$(VERSION) \
		-t $(DOCKER_REPO):latest \
		--push \
		.
	@echo ""
	@echo "Step 3/3: Pushing git tag..."
	git push origin "v$(VERSION)"
	@echo ""
	@echo "=========================================="
	@echo "Release v$(VERSION) complete!"
	@echo "=========================================="
	@echo "  Git tag: v$(VERSION)"
	@echo "  Docker:  $(DOCKER_REPO):$(VERSION)"
	@echo "  Docker:  $(DOCKER_REPO):latest"
	@echo "=========================================="

# Development helpers
lint:
	ruff check .
	black --check src tests

lint-fix:
	ruff check --fix .
	black src tests

test:
	pytest

test-cov:
	pytest --cov=src/radarr_manager --cov-report=term-missing

clean:
	rm -rf build/ dist/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
