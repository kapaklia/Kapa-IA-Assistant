"""python -B tests/run_safe_tests.py: unittest offline e senza configurazione privata."""
import sys
import unittest
from safe_config import install

install()
suite = unittest.TestLoader().loadTestsFromNames([
    'test_patch', 'test_hotkey_portal', 'test_shortcut_status', 'test_regressions', 'test_gui_safe',
    'test_project_layout', 'test_installer',
])
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
