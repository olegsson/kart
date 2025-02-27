import sys

import click

from kart import diff_estimation
from kart.cli_util import OutputFormatType, parse_output_format
from kart.completion_shared import path_completer
from kart.crs_util import CoordinateReferenceString
from kart.output_util import dump_json_output
from kart.parse_args import PreserveDoubleDash, parse_commits_and_filters
from kart.repo import KartRepoState


def feature_count_diff(
    repo,
    output_format,
    commit_spec,
    output_path,
    exit_code,
    json_style,
    accuracy,
):
    if output_format not in ("text", "json"):
        raise click.UsageError("--only-feature-count requires text or json output")

    from .base_diff_writer import BaseDiffWriter

    (
        base_rs,
        target_rs,
        include_wc_diff,
    ) = BaseDiffWriter.parse_diff_commit_spec(repo, commit_spec)

    dataset_change_counts = diff_estimation.estimate_diff_feature_counts(
        repo,
        base_rs.tree,
        target_rs.tree,
        include_wc_diff=include_wc_diff,
        accuracy=accuracy,
    )

    if output_format == "text":
        if dataset_change_counts:
            for dataset_name, count in sorted(dataset_change_counts.items()):
                click.secho(f"{dataset_name}:", bold=True)
                click.echo(f"\t{count} features changed")
        else:
            click.echo("0 features changed")
    elif output_format == "json":
        dump_json_output(dataset_change_counts, output_path, json_style=json_style)
    if dataset_change_counts and exit_code:
        sys.exit(1)


@click.command(cls=PreserveDoubleDash)
@click.pass_context
@click.option(
    "--output-format",
    "-o",
    type=OutputFormatType(
        output_types=[
            "text",
            "json",
            "geojson",
            "quiet",
            "feature-count",
            "html",
            "json-lines",
        ],
        allow_text_formatstring=False,
    ),
    default="text",
    help=(
        "Output format. 'quiet' disables all output and implies --exit-code.\n"
        "'html' attempts to open a browser unless writing to stdout ( --output=- )"
    ),
)
@click.option(
    "--exit-code",
    is_flag=True,
    help="Make the program exit with codes similar to diff(1). That is, it exits with 1 if there were differences and 0 means no differences.",
)
@click.option(
    "--crs",
    type=CoordinateReferenceString(encoding="utf-8"),
    help="Reproject geometries into the given coordinate reference system. Accepts: 'EPSG:<code>'; proj text; OGC WKT; OGC URN; PROJJSON.)",
)
@click.option(
    "--output",
    "output_path",
    help="Output to a specific file/directory instead of stdout.",
    type=click.Path(writable=True, allow_dash=True),
)
@click.option(
    "--json-style",
    type=click.Choice(["extracompact", "compact", "pretty"]),
    help="[deprecated] How to format the output. Only used with -o json or -o geojson",
)
@click.option(
    "--only-feature-count",
    default=None,
    type=click.Choice(diff_estimation.ACCURACY_CHOICES),
    help=(
        "Returns only a feature count (the number of features modified in this diff). "
        "If the value is 'exact', the feature count is exact (this may be slow.) "
        "Otherwise, the feature count will be approximated with varying levels of accuracy."
    ),
)
@click.option(
    "--add-feature-count-estimate",
    default=None,
    type=click.Choice(diff_estimation.ACCURACY_CHOICES),
    help=(
        "Adds a feature count estimate to this diff (used with `--output-format json-lines` only.) "
        "The estimate will be calculated while the diff is being generated, and will be added to "
        "the stream when it is ready. If the estimate is not ready before the process exits, it will not be added."
    ),
)
@click.option(
    "--convert-to-dataset-format",
    is_flag=True,
    help="Ignores file format differences in any new files when generating the diff - assumes that the new files will "
    "also committed using --convert-to-dataset-format, so the conversion step will remove the format differences.",
)
@click.argument(
    "args",
    metavar="[REVISION RANGE] [--] [FILTERS]",
    nargs=-1,
    type=click.UNPROCESSED,
    shell_complete=path_completer,
)
def diff(
    ctx,
    output_format,
    crs,
    output_path,
    exit_code,
    json_style,
    only_feature_count,
    add_feature_count_estimate,
    convert_to_dataset_format,
    args,
):
    """
    Show changes between two commits, or between a commit and the working copy.

    COMMIT_SPEC -

    - if not supplied, the default is HEAD, to diff between HEAD and the working copy.

    - if a single ref is supplied: commit-A - diffs between commit-A and the working copy.

    - if supplied with the form: commit-A...commit-B - diffs between commit-A and commit-B.

    - supplying two seperate refs: commit-A commit-B - also diffs between commit-A and commit-B

    - if supplied with the form: commit-A..commit-B - diffs between (the common ancestor of
    commit-A and commit-B) and (commit-B).

    To list only particular changes, supply one or more FILTERS of the form [DATASET[:PRIMARY_KEY]]
    """
    repo = ctx.obj.get_repo(allowed_states=KartRepoState.ALL_STATES)
    options, commits, filters = parse_commits_and_filters(repo, args)
    output_type, fmt = parse_output_format(output_format, json_style)

    assert len(commits) <= 2
    if len(commits) == 2:
        if ".." in commits[0] or ".." in commits[1]:
            raise click.BadParameter(
                f"Can only show a single range - can't show {', '.join(commits)}"
            )
        commit_spec = "...".join(commits)
    elif len(commits) == 1:
        commit_spec = commits[0]
    else:
        commit_spec = "HEAD"

    if only_feature_count:
        return feature_count_diff(
            repo,
            output_type,
            commit_spec,
            output_path,
            exit_code,
            fmt,
            only_feature_count,
        )

    from .base_diff_writer import BaseDiffWriter

    diff_writer_class = BaseDiffWriter.get_diff_writer_class(output_type)
    diff_writer = diff_writer_class(
        repo,
        commit_spec,
        filters,
        output_path,
        json_style=fmt,
        target_crs=crs,
        diff_estimate_accuracy=add_feature_count_estimate,
    )
    diff_writer.convert_to_dataset_format(convert_to_dataset_format)
    diff_writer.write_diff()

    if exit_code or output_type == "quiet":
        diff_writer.exit_with_code()
