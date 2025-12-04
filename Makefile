# Makefile for radarr-manager
#
# Versioning Pipeline:
#   1. Single source of truth: pyproject.toml contains the version
#   2. Git tags: v{VERSION} (e.g., v1.12.0)
#   3. Docker images: {VERSION} (e.g., 1.12.0) + latest
#
# Usage:
#   make version          - Show current version
#   make release-patch    - Bump patch, commit, tag, build, push (1.12.0 -> 1.12.1)
#   make release-minor    - Bump minor, commit, tag, build, push (1.12.0 -> 1.13.0)
#   make release-major    - Bump major, commit, tag, build, push (1.12.0 -> 2.0.0)
#   make release          - Release current version (tag + build + push)
#   make docker-build     - Build Docker image only
#   make docker-push      - Push Docker image to registry

.PHONY: version bump-patch bump-minor bump-major tag docker-build docker-push release \
        release-patch release-minor release-major lint test clean help check-clean check-version

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
	@echo "Release (recommended - does everything):"
	@echo "  make release-patch - Bump patch + commit + tag + build + push (x.y.Z)"
	@echo "  make release-minor - Bump minor + commit + tag + build + push (x.Y.0)"
	@echo "  make release-major - Bump major + commit + tag + build + push (X.0.0)"
	@echo ""
	@echo "Manual Steps (if needed):"
	@echo "  make version       - Show current version ($(VERSION))"
	@echo "  make release       - Release current version (tag + build + push)"
	@echo "  make docker-build  - Build Docker image only"
	@echo "  make docker-push   - Push Docker image to registry"
	@echo ""
	@echo "Development:"
	@echo "  make lint          - Run linters (ruff, black)"
	@echo "  make test          - Run tests"
	@echo "  make clean         - Clean build artifacts"

version:
	@echo "Current version: $(VERSION)"
	@echo "Git tag: v$(VERSION)"
	@echo "Docker image: $(DOCKER_REPO):$(VERSION)"

# Internal: bump version in pyproject.toml (used by release-* targets)
_bump-patch:
	@python3 -c "\
import re; \
f = open('pyproject.toml', 'r'); content = f.read(); f.close(); \
version = re.search(r'version = \"([^\"]+)\"', content).group(1); \
parts = version.split('.'); \
parts[2] = str(int(parts[2]) + 1); \
new_version = '.'.join(parts); \
content = re.sub(r'version = \"[^\"]+\"', f'version = \"{new_version}\"', content, count=1); \
f = open('pyproject.toml', 'w'); f.write(content); f.close(); \
print(f'Bumped version: {version} -> {new_version}')"

_bump-minor:
	@python3 -c "\
import re; \
f = open('pyproject.toml', 'r'); content = f.read(); f.close(); \
version = re.search(r'version = \"([^\"]+)\"', content).group(1); \
parts = version.split('.'); \
parts[1] = str(int(parts[1]) + 1); \
parts[2] = '0'; \
new_version = '.'.join(parts); \
content = re.sub(r'version = \"[^\"]+\"', f'version = \"{new_version}\"', content, count=1); \
f = open('pyproject.toml', 'w'); f.write(content); f.close(); \
print(f'Bumped version: {version} -> {new_version}')"

_bump-major:
	@python3 -c "\
import re; \
f = open('pyproject.toml', 'r'); content = f.read(); f.close(); \
version = re.search(r'version = \"([^\"]+)\"', content).group(1); \
parts = version.split('.'); \
parts[0] = str(int(parts[0]) + 1); \
parts[1] = '0'; \
parts[2] = '0'; \
new_version = '.'.join(parts); \
content = re.sub(r'version = \"[^\"]+\"', f'version = \"{new_version}\"', content, count=1); \
f = open('pyproject.toml', 'w'); f.write(content); f.close(); \
print(f'Bumped version: {version} -> {new_version}')"

# Get new version after bump (re-reads pyproject.toml)
_get-version = $(shell python3 -c "import re; print(re.search(r'version = \"([^\"]+)\"', open('pyproject.toml').read()).group(1))")

# Full release pipelines: bump + commit + tag + build + push
release-patch: check-clean
	@echo "=========================================="
	@echo "Starting PATCH release..."
	@echo "=========================================="
	@$(MAKE) _bump-patch
	$(eval NEW_VERSION := $(_get-version))
	@echo ""
	@echo "Step 1/4: Committing version bump..."
	git add pyproject.toml
	git commit -m "chore: bump version to $(NEW_VERSION)"
	@echo ""
	@echo "Step 2/4: Creating git tag v$(NEW_VERSION)..."
	git tag -a "v$(NEW_VERSION)" -m "Release v$(NEW_VERSION)"
	@echo ""
	@echo "Step 3/4: Building and pushing Docker image..."
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(DOCKER_REPO):$(NEW_VERSION) \
		-t $(DOCKER_REPO):latest \
		--push \
		.
	@echo ""
	@echo "Step 4/4: Pushing git tag..."
	git push origin main "v$(NEW_VERSION)"
	@echo ""
	@echo "=========================================="
	@echo "Release v$(NEW_VERSION) complete!"
	@echo "=========================================="

release-minor: check-clean
	@echo "=========================================="
	@echo "Starting MINOR release..."
	@echo "=========================================="
	@$(MAKE) _bump-minor
	$(eval NEW_VERSION := $(_get-version))
	@echo ""
	@echo "Step 1/4: Committing version bump..."
	git add pyproject.toml
	git commit -m "chore: bump version to $(NEW_VERSION)"
	@echo ""
	@echo "Step 2/4: Creating git tag v$(NEW_VERSION)..."
	git tag -a "v$(NEW_VERSION)" -m "Release v$(NEW_VERSION)"
	@echo ""
	@echo "Step 3/4: Building and pushing Docker image..."
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(DOCKER_REPO):$(NEW_VERSION) \
		-t $(DOCKER_REPO):latest \
		--push \
		.
	@echo ""
	@echo "Step 4/4: Pushing git tag..."
	git push origin main "v$(NEW_VERSION)"
	@echo ""
	@echo "=========================================="
	@echo "Release v$(NEW_VERSION) complete!"
	@echo "=========================================="

release-major: check-clean
	@echo "=========================================="
	@echo "Starting MAJOR release..."
	@echo "=========================================="
	@$(MAKE) _bump-major
	$(eval NEW_VERSION := $(_get-version))
	@echo ""
	@echo "Step 1/4: Committing version bump..."
	git add pyproject.toml
	git commit -m "chore: bump version to $(NEW_VERSION)"
	@echo ""
	@echo "Step 2/4: Creating git tag v$(NEW_VERSION)..."
	git tag -a "v$(NEW_VERSION)" -m "Release v$(NEW_VERSION)"
	@echo ""
	@echo "Step 3/4: Building and pushing Docker image..."
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(DOCKER_REPO):$(NEW_VERSION) \
		-t $(DOCKER_REPO):latest \
		--push \
		.
	@echo ""
	@echo "Step 4/4: Pushing git tag..."
	git push origin main "v$(NEW_VERSION)"
	@echo ""
	@echo "=========================================="
	@echo "Release v$(NEW_VERSION) complete!"
	@echo "=========================================="

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
