from __future__ import annotations

import runpy
from pathlib import Path


def test_preflight_script_exports_main_and_check() -> None:
    ns = runpy.run_path("scripts/preflight_s06.py")
    assert "main" in ns
    assert "Check" in ns
    assert callable(ns["main"])


def test_demo_cleaning_script_exports_main() -> None:
    ns = runpy.run_path("scripts/demo_cleaning_s06.py")
    assert "main" in ns
    assert callable(ns["main"])


def test_demo_pii_script_exports_main() -> None:
    ns = runpy.run_path("scripts/demo_pii_s06.py")
    assert "main" in ns
    assert callable(ns["main"])


def test_s06_scripts_exist() -> None:
    assert Path("scripts/preflight_s06.py").exists()
    assert Path("scripts/demo_cleaning_s06.py").exists()
    assert Path("scripts/demo_pii_s06.py").exists()
