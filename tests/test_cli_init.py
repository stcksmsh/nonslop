"""Checks `nonslop init --from`. Run: python3 tests/test_cli_init.py [path/to/bin/nonslop]"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "bin" / "nonslop"


def init(repo: Path, source: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BIN), "init", "--from", str(source)],
                          cwd=repo, capture_output=True, text=True, check=False)


def main() -> None:
    scratch_root = ROOT / ".claude" / "tmp"
    scratch_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=scratch_root, prefix="test-init-"))
    try:
        repo = work / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        first, second, bad = work / "a.toml", work / "b.toml", work / "bad.toml"
        first.write_text('[commands]\ntest = "a"\n', encoding="utf-8")
        second.write_text('[commands]\ntest = "b"\n', encoding="utf-8")
        bad.write_text("x = = 1\n", encoding="utf-8")

        assert init(repo, bad).returncode != 0, "invalid TOML must exit non-zero"
        assert not (repo / ".nonslop.toml").exists(), "invalid TOML must not create the config"

        result = init(repo, first)
        assert result.returncode == 0, result.stderr
        assert (repo / ".nonslop.toml").read_text(encoding="utf-8") == first.read_text(encoding="utf-8")

        assert init(repo, second).returncode == 0
        assert (repo / ".nonslop.toml").read_text(encoding="utf-8") == first.read_text(encoding="utf-8"), \
            "an existing .nonslop.toml must be kept"
    finally:
        shutil.rmtree(work, ignore_errors=True)


main()
