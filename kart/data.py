import sys

import click

from .cli_util import KartGroup, StringFromFile, add_help_subcommand
from .commit import commit_json_to_text, commit_obj_to_json, get_commit_message
from .diff_structs import DatasetDiff, Delta, DeltaDiff, RepoDiff
from .exceptions import NO_TABLE, NotFound
from .output_util import dump_json_output
from .repo import KartRepoState
from .completion_shared import ref_completer

# Changing these items would generally break the repo;
# we disallow that.


@add_help_subcommand
@click.group(cls=KartGroup)
@click.pass_context
def data(ctx, **kwargs):
    """Information about the datasets in a repository."""


@data.command(name="ls")
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
)
@click.argument("refish", required=False, default="HEAD", shell_complete=ref_completer)
@click.pass_context
def data_ls(ctx, output_format, refish):
    """List all of the datasets in the Kart repository"""
    repo = ctx.obj.get_repo(allowed_states=KartRepoState.ALL_STATES)
    ds_paths = list(repo.datasets(refish).paths())

    if output_format == "text":
        if ds_paths:
            for ds_path in ds_paths:
                click.echo(ds_path)
        else:
            repo_desc = (
                "Empty repository."
                if repo.head_is_unborn
                else "The commit at HEAD has no datasets."
            )
            click.echo(f'{repo_desc}\n  (use "kart import" to add some data)')

    elif output_format == "json":
        dump_json_output({"kart.data.ls/v1": ds_paths}, sys.stdout)


@data.command(name="rm")
@click.option(
    "--message",
    "-m",
    multiple=True,
    help=(
        "Use the given message as the commit message. If multiple `-m` options are given, their values are "
        "concatenated as separate paragraphs."
    ),
    type=StringFromFile(encoding="utf-8"),
)
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
)
@click.argument("datasets", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def data_rm(ctx, message, output_format, datasets):
    """Delete one or more datasets in the Kart repository, and commit the result"""

    if not datasets:
        raise click.UsageError("Specify a dataset to delete: eg `kart data rm DATASET`")

    repo = ctx.obj.get_repo()
    existing_ds_paths = set(repo.datasets().paths())

    for ds_path in datasets:
        if ds_path not in existing_ds_paths:
            raise NotFound(
                f"Cannot delete dataset at path '{ds_path}' since it does not exist",
                exit_code=NO_TABLE,
            )

    repo.working_copy.check_not_dirty()

    repo_diff = RepoDiff()
    for ds_path in datasets:
        dataset = repo.datasets()[ds_path]
        ds_diff = DatasetDiff()
        ds_diff["meta"] = DeltaDiff.diff_dicts(dataset.meta_items(), {})
        ds_diff["feature"] = dataset.all_features_diff(delta_type=Delta.delete)
        repo_diff[ds_path] = ds_diff

    do_json = output_format == "json"
    if message:
        commit_msg = "\n\n".join([m.strip() for m in message]).strip()
    else:
        commit_msg = get_commit_message(repo, repo_diff, quiet=do_json)

    if not commit_msg:
        raise click.UsageError("Aborting commit due to empty commit message.")

    new_commit = repo.structure().commit_diff(repo_diff, commit_msg)
    repo.working_copy.reset_to_head()

    jdict = commit_obj_to_json(new_commit, repo, repo_diff)
    if do_json:
        dump_json_output(jdict, sys.stdout)
    else:
        click.echo(commit_json_to_text(jdict))

    repo.gc("--auto")


@data.command(name="version")
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
)
@click.pass_context
def data_version(ctx, output_format):
    """Show the repository structure version"""
    repo = ctx.obj.get_repo(
        allowed_states=KartRepoState.ALL_STATES, allow_unsupported_versions=True
    )
    version = repo.table_dataset_version
    if output_format == "text":
        click.echo(f"This Kart repo uses Datasets v{version}")
        if version >= 1:
            click.echo(
                f"(See https://github.com/koordinates/kart/blob/master/docs/DATASETS_v{version}.md)"
            )
    elif output_format == "json":
        from .repo import KartConfigKeys

        branding = (
            "kart"
            if KartConfigKeys.KART_REPOSTRUCTURE_VERSION in repo.config
            else "sno"
        )
        dump_json_output(
            {"repostructure.version": version, "localconfig.branding": branding},
            sys.stdout,
        )
