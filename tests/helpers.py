import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

MOCK_DATA = REPO_ROOT / "mock_data"
CONFIG = REPO_ROOT / "config"

from governance.agents.orchestrator import Orchestrator  # noqa: E402
from governance.catalog import Catalog  # noqa: E402


def full_run(as_of=None):
    """One fully-wired pass over the real mock data, held in memory."""
    catalog = Catalog()
    orchestrator = Orchestrator(catalog, config_dir=CONFIG)
    scorecard = orchestrator.run_all(MOCK_DATA, as_of=as_of)
    return orchestrator, catalog, scorecard
