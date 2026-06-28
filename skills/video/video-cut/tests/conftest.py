import sys
from pathlib import Path

# make scripts/ importable as top-level modules (edl, pack_transcripts)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
