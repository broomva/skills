"""End-to-end tests for the `bookkeeping render` CLI command."""
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bookkeeping.py"


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


class TestRenderCLI:
    def test_render_single_file(self, tmp_path):
        src = tmp_path / "note.md"
        src.write_text("---\ntitle: Test\n---\n# Body\n")
        result = run(["render", str(src)], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        out = src.with_suffix(".html")
        assert out.exists()
        text = out.read_text()
        assert "<title>Test</title>" in text
        assert "<h1>Body</h1>" in text

    def test_render_directory_glob(self, tmp_path):
        (tmp_path / "a-synthesis.md").write_text("---\ntitle: A\n---\n# A")
        (tmp_path / "b-synthesis.md").write_text("---\ntitle: B\n---\n# B")
        (tmp_path / "c-raw.md").write_text("---\ntitle: C\n---\n# C")  # not synthesis
        result = run(["render", str(tmp_path)], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "a-synthesis.html").exists()
        assert (tmp_path / "b-synthesis.html").exists()
        assert not (tmp_path / "c-raw.html").exists()  # only -synthesis glob

    def test_render_link_html_flag(self, tmp_path):
        src = tmp_path / "note.md"
        src.write_text("See [[concept/foo]].")
        result = run(["render", str(src), "--link-html"], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        text = src.with_suffix(".html").read_text()
        assert 'href="../concept/foo.html"' in text

    def test_render_nonexistent_path_errors(self, tmp_path):
        ghost = tmp_path / "ghost.md"
        result = run(["render", str(ghost)], cwd=tmp_path)
        assert result.returncode != 0
        # Should be either "not found" message or general error
        assert result.returncode in (1, 2)

    def test_render_no_args_errors(self, tmp_path):
        result = run(["render"], cwd=tmp_path)
        # Either argparse rejects (exit 2) or our usage check fires (exit 2)
        assert result.returncode != 0
