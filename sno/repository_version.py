import itertools

import click
import json

from .core import walk_tree

REPO_VERSION_BLOB_PATH = ".sno.repository.version"
REPO_VERSION_CONFIG_PATH = "sno.repository.version"

REPO_VERSIONS = (0, 1, 2)
DEFAULT_REPO_VERSION = 2

# Only versions 1 and 2 (or "auto") are currently supported by any commands.
# If you have version 0, use sno upgrade 00-02
REPO_VERSIONS_CHOICE = click.Choice(["1", "2"])
REPO_VERSIONS_DEFAULT_CHOICE = str(DEFAULT_REPO_VERSION)


def encode_repo_version(version):
    return REPO_VERSION_BLOB_PATH, f"{version}\n".encode("utf8")


def extra_blobs_for_version(version):
    """Returns the extra blobs that should be written to a repository for the given version."""
    version = int(version)
    if version <= 1:
        # Version 1 never had a repo-wide version blob. We'll leave it that way, no need to change it.
        return []

    # Versions 2 and up have their version number stored in REPO_VERSION_BLOB_PATH
    return [encode_repo_version(version)]


def get_repo_version(
    repo, tree=None, allow_legacy_versions=False, default=DEFAULT_REPO_VERSION
):
    """
    Returns the repo version from the blob at <repo-root>/REPO_VERSION_BLOB_PATH -
    (note that this is not user-visible in the file-system since we keep it hidden via sparse / bare checkouts).
    """
    if tree is None:
        tree = repo.head_tree
        if tree is None:  # Empty repo / empty branch.
            return _get_repo_version_from_config(repo, default)

    if REPO_VERSION_BLOB_PATH in tree:
        return json.loads((tree / REPO_VERSION_BLOB_PATH).data)

    # Versions less than 2 don't have ".sno.repository.version" files, so must be 0 or 1.
    # We don't support v0 except when performing a `sno upgrade`.
    return _distinguish_v0_v1(tree) if allow_legacy_versions else 1


def _get_repo_version_from_config(repo, default=DEFAULT_REPO_VERSION):
    repo_cfg = repo.config
    if REPO_VERSION_CONFIG_PATH in repo_cfg:
        return repo_cfg.get_int(REPO_VERSION_CONFIG_PATH)
    return default


def _distinguish_v0_v1(tree):
    WALK_LIMIT = 100
    for top_tree, top_path, subtree_names, blob_names in itertools.islice(
        walk_tree(tree), 0, WALK_LIMIT
    ):
        dir_name = top_tree.name
        if dir_name == "meta" or dir_name == "features":
            # "meta" exists in v1 too, but only inside ".sno-table" - so report the one we get to first.
            return 0
        elif dir_name == ".sno-table":
            return 1
    # Maybe this isn't even a sno repo?
    return 1
