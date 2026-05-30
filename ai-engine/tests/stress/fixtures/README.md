# Synthetic PDF Fixtures

This directory contains scripts to generate deterministic synthetic PDF attachments for stress testing.

## Files

- **`build_pdfs.py`** - Script that generates the four synthetic PDFs

## Generated Artifacts (not committed)

The script generates these files (automatically by `.gitignore`):

- `attach_5kb.pdf` - 5 KB deterministic test attachment
- `attach_20kb.pdf` - 20 KB deterministic test attachment
- `attach_50kb.pdf` - 50 KB deterministic test attachment
- `attach_100kb.pdf` - 100 KB deterministic test attachment

## Usage

### Regenerate fixtures

```bash
python build_pdfs.py
```

### Verify determinism

```bash
# Run twice and verify checksums match
md5sum *.pdf
python build_pdfs.py
md5sum *.pdf
```

## Design Rationale

- **Deterministic**: Same input → same bytes (verified by MD5)
- **Exact sizes**: Precise byte counts for reproducible testing
- **Simple**: Text-based content (Lorem Ipsum) with padding
- **Fast**: Quick generation without external services
- **Not versioned**: PDFs are regenerated on each test run

These fixtures simulate real attachment handling in the stress test scenarios (ProjectGrowth, ProjectPivot, ProjectContradiction) to measure latency and cost impact of different file sizes.
