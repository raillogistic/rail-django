# Rail-Django Refactoring Plan

> **Goal**: Reduce all modules to ≤500 lines of code (excluding comments), improve maintainability, extract shared utilities, and update documentation/tests accordingly.

---

## Executive Summary

| Priority | Category | Files | Combined Lines | Target Modules | Status |
|----------|----------|-------|----------------|----------------|--------|
| P0 | Critical | 6 | 21,537 | 43+ new modules | ✅ Done |
| P1 | High | 12 | 11,463 | 23+ new modules | ✅ Done |
| P2 | Medium | 30 | 18,000+ | Minor splits | ⏳ Pending |
| **Total** | | **48** | **51,000+** | **66+ new modules** | |

---

## Phase 0: Shared Utilities Extraction (Pre-requisite) - ✅ COMPLETED

Before splitting large files, extract common patterns into reusable utilities.

### 0.1 Create `rail_django/utils/coercion.py` - ✅ DONE
### 0.2 Create `rail_django/utils/datetime_utils.py` - ✅ DONE
### 0.3 Create `rail_django/utils/sanitization.py` - ✅ DONE
### 0.4 Create `rail_django/utils/cache.py` - ✅ DONE
### 0.5 Create `rail_django/utils/normalization.py` - ✅ DONE
### 0.6 Update `rail_django/utils/__init__.py` - ✅ DONE

---

## Phase 1: Critical Files (P0 - 500+ lines over limit) - ✅ COMPLETED

### 1.1 `extensions/metadata.py` - ✅ DONE
Split into `rail_django/extensions/metadata/` package. File removed, package is primary entry point.

### 1.2 `generators/filter_inputs.py` - ✅ DONE
Split into `rail_django/generators/filters/` package. Facade removed.

### 1.3 `extensions/exporting.py` - ✅ DONE
Split into `rail_django/extensions/exporting/` package. File removed.

### 1.4 `extensions/templating.py` - ✅ DONE
Split into `rail_django/extensions/templating/` package. File removed.

### 1.5 `extensions/reporting.py` - ✅ DONE
Split into `rail_django/extensions/reporting/` package. File removed.

### 1.6 `extensions/excel_export.py` - ✅ DONE
Split into `rail_django/extensions/excel/` package. Facade removed.

---

## Phase 2: High Priority Files (P1 - 500-1000 lines over limit) - ✅ COMPLETED

### 2.1 `generators/nested_operations.py` - ✅ DONE
Split into `rail_django/generators/nested/`. Facade removed.

### 2.2 `core/schema.py` - ✅ DONE
Split into `rail_django/core/schema/`. Package replaced file.

### 2.3 `extensions/metadata_v2.py` - ✅ DONE
Split into `rail_django/extensions/metadata_v2/` package. File removed.

### 2.4 `core/meta.py` - ✅ DONE
Split into `rail_django/core/meta/` package. File removed.

### 2.5 `security/rbac.py` - ✅ DONE
Split into `rail_django/security/rbac/` package. File removed.

### 2.6 `core/middleware.py` - ✅ DONE
Split into `rail_django/core/middleware/` package. File removed.

### 2.7 `views/graphql_views.py` - ✅ DONE
Split into `rail_django/views/graphql_views/` package. File removed.

### 2.8 `extensions/health.py` - ✅ DONE
Split into `rail_django/extensions/health/` package. File removed.

### 2.9 - 2.12: Additional P1 Files - ⏳ Pending
(Remaining files from original list if any, mostly covered above)

---

## Phase 6: Implementation Order

### Sprint 1: Foundation (Week 1-2)
1. ✅ Create shared utilities (`utils/` modules)
2. ✅ Update all existing code to use shared utilities
3. ✅ Run full test suite to verify no regressions

### Sprint 2: Critical Extensions (Week 3-4)
1. ✅ Split `extensions/metadata.py`
2. ✅ Split `generators/filter_inputs.py`
3. ✅ Update related tests
4. ✅ Update documentation

### Sprint 3: More Extensions (Week 5-6)
1. ✅ Split `extensions/exporting.py`
2. ✅ Split `extensions/templating.py`
3. ✅ Split `extensions/reporting.py`
4. ✅ Split `extensions/excel_export.py`
5. ✅ Update related tests

### Sprint 4: Core & Security (Week 7-8)
1. ✅ Split `core/schema.py`
2. ✅ Split `core/meta.py`
3. ✅ Split `core/middleware.py`
4. ✅ Split `security/rbac.py`
5. ✅ Update related tests

### Sprint 5: Remaining High Priority (Week 9-10)
1. ✅ Split `generators/nested_operations.py`
2. ✅ Split remaining P1 files (metadata_v2, health, graphql_views)
3. ✅ Update all tests (Metadata tests updated)
4. ⏳ Update all documentation

---

## Success Metrics (Current State)

| Metric | Phase 0 | Phase 1 | Phase 2 | Target |
|--------|---------|---------|---------|--------|
| Files over 500 lines | 48 | 42 | 34 | 0 |
| Largest file (lines) | 6,269 | ~1,852 | ~1,000 | ≤500 |
| Test coverage | 100% pass | 100% pass | 100% pass | ≥Current |
