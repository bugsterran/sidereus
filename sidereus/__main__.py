"""`python3 -m sidereus start|stop|status` — thin entry that delegates to sidereus_cli.py (repo root)."""
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)
import sidereus_cli  # noqa: E402

sys.exit(sidereus_cli.main())   # asset lookup (clone vs sidereus/_bundle) lives in sidereus_cli
