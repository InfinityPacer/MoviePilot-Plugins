from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
SELECTOR = REPO_ROOT / ".github/scripts/select_plugin_release_dir.sh"
WORKFLOW = REPO_ROOT / ".github/workflows/release.yml"


def _select(tmp_path: Path, package_file: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SELECTOR), package_file, "example"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_directory_selects_each_generation_source(tmp_path: Path) -> None:
    (tmp_path / "plugins/example").mkdir(parents=True)
    (tmp_path / "plugins.v2/example").mkdir(parents=True)
    (tmp_path / "plugins.v3/example").mkdir(parents=True)

    assert _select(tmp_path, "package.json").stdout.strip() == "plugins/example"
    assert _select(tmp_path, "package.v2.json").stdout.strip() == "plugins.v2/example"
    assert _select(tmp_path, "package.v3.json").stdout.strip() == "plugins.v3/example"


def test_v3_release_directory_does_not_fall_back_to_v2_source(tmp_path: Path) -> None:
    (tmp_path / "plugins.v2/example").mkdir(parents=True)

    result = _select(tmp_path, "package.v3.json")

    assert result.returncode != 0
    assert result.stdout == ""


def test_v2_release_directory_does_not_fall_back_to_v1_source(tmp_path: Path) -> None:
    (tmp_path / "plugins/example").mkdir(parents=True)

    result = _select(tmp_path, "package.v2.json")

    assert result.returncode != 0
    assert result.stdout == ""


def test_release_directory_rejects_unknown_package_file(tmp_path: Path) -> None:
    result = _select(tmp_path, "package.beta.json")

    assert result.returncode == 2
    assert "Unsupported package file" in result.stderr


def test_release_workflow_uses_generation_aware_directory_selector() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'select_plugin_release_dir.sh "$pkg_file" "$plugin_id_lc"' in workflow
    assert 'process_package "package.json"' in workflow
    assert 'process_package "package.v2.json"' in workflow
    assert 'process_package "package.v3.json"' in workflow
    assert ".value.v3 == true or .value.v2 == true" in workflow
    assert ".value.release == true and .value.v3 != false" in workflow
    assert "Missing plugin directory" in workflow
    assert 'git rev-parse -q --verify "refs/tags/$tag"' in workflow
    assert 'prev_tag="$tag"' in workflow
    assert 'if [ -d "$dir2" ]; then plugin_dir="$dir2"; fi' not in workflow


def test_release_workflow_builds_frontend_before_packaging() -> None:
    """带前端工程的插件必须在打包前构建并校验联邦入口。"""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "uses: actions/setup-node@v7" in workflow
    assert "build_frontend \"$plugin_dir\"" in workflow
    assert "yarn --frozen-lockfile && yarn build" in workflow
    assert '[ ! -s "$frontend_dir/dist/assets/remoteEntry.js" ]' in workflow
    assert 'git check-ignore -q "$frontend_dir/dist/assets/remoteEntry.js"' not in workflow
    assert 'git status --porcelain --untracked-files=all -- "$frontend_dir/dist"' not in workflow
    assert '-x "*/node_modules/*"' in workflow


def test_frontend_federation_entries_are_generated_and_ignored() -> None:
    """V2/V3 联邦入口由构建生成，不应作为 Git 源文件提交。"""
    invalid = []
    for plugin_generation in ("plugins.v2", "plugins.v3"):
        for package_path in sorted(
            REPO_ROOT.glob(f"{plugin_generation}/*/frontend/package.json")
        ):
            remote_entry = package_path.parent / "dist/assets/remoteEntry.js"
            relative_entry = remote_entry.relative_to(REPO_ROOT)
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", str(relative_entry)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            ignored = subprocess.run(
                ["git", "check-ignore", "--no-index", "-q", str(relative_entry)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if tracked.returncode == 0 or ignored.returncode != 0:
                invalid.append(str(relative_entry))

    assert invalid == []
