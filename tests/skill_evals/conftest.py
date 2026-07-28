"""Put ``scripts/`` on sys.path so ``skill_evals`` resolves to the harness package.

Deliberately no ``__init__.py`` in this directory: it would register a *second*
package literally named ``skill_evals`` (the test dir) that shadows the one under
test, and pytest would import the tests instead of the harness.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
