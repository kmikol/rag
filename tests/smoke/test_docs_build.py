import subprocess


def test_docs_build_strict() -> None:
    result = subprocess.run(
        ["mkdocs", "build", "-f", "docs/mkdocs.yml", "--strict"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
