---
name: QC2 PostgreSQL test encoding
description: Required encoding for local QC2 database acceptance runs.
---

Use a UTF8-encoded isolated database for the QC2 PostgreSQL acceptance chain. A no-locale PostgreSQL cluster can default to SQL_ASCII, which cannot run the Unicode normalization used by canonical JSON hashing.

**Why:** The canonical hash acceptance fixtures include Unicode and rely on PostgreSQL NFC normalization.

**How to apply:** Initialize local acceptance clusters with UTF8, use a dedicated `qc2_test_*` database, and run the migration chain through its rollback-only test runner.
