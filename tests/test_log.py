import re
import json
import pytest


H = pytest.helpers.helpers()


@pytest.mark.parametrize("output_format", ["text", "json", "json-lines"])
def test_log(output_format, data_archive_readonly, cli_runner):
    """ review commit history """
    with data_archive_readonly("points"):
        extra_args = ["--dataset-changes"] if output_format.startswith("json") else []
        r = cli_runner.invoke(["log", f"--output-format={output_format}"] + extra_args)
        assert r.exit_code == 0, r
        if output_format == "text":
            assert r.stdout.splitlines() == [
                f"commit {H.POINTS.HEAD_SHA}",
                "Author: Robert Coup <robert@coup.net.nz>",
                "Date:   Thu Jun 20 15:28:33 2019 +0100",
                "",
                "    Improve naming on Coromandel East coast",
                "",
                f"commit {H.POINTS.HEAD1_SHA}",
                "Author: Robert Coup <robert@coup.net.nz>",
                "Date:   Tue Jun 11 12:03:58 2019 +0100",
                "",
                "    Import from nz-pa-points-topo-150k.gpkg",
            ]
        elif output_format == "json":
            assert json.loads(r.stdout) == [
                {
                    "commit": H.POINTS.HEAD_SHA,
                    "abbrevCommit": H.POINTS.HEAD_SHA[:7],
                    "message": "Improve naming on Coromandel East coast",
                    "refs": ["HEAD -> main"],
                    "authorEmail": "robert@coup.net.nz",
                    "authorName": "Robert Coup",
                    "authorTime": "2019-06-20T14:28:33Z",
                    "authorTimeOffset": "+01:00",
                    "commitTime": "2019-06-20T14:28:33Z",
                    "commitTimeOffset": "+01:00",
                    "committerEmail": "robert@coup.net.nz",
                    "committerName": "Robert Coup",
                    "parents": [H.POINTS.HEAD1_SHA],
                    "abbrevParents": [H.POINTS.HEAD1_SHA[:7]],
                    "datasetChanges": ["nz_pa_points_topo_150k"],
                },
                {
                    "commit": H.POINTS.HEAD1_SHA,
                    "abbrevCommit": H.POINTS.HEAD1_SHA[:7],
                    "message": "Import from nz-pa-points-topo-150k.gpkg",
                    "refs": [],
                    "authorEmail": "robert@coup.net.nz",
                    "authorName": "Robert Coup",
                    "authorTime": "2019-06-11T11:03:58Z",
                    "authorTimeOffset": "+01:00",
                    "commitTime": "2019-06-11T11:03:58Z",
                    "commitTimeOffset": "+01:00",
                    "committerEmail": "robert@coup.net.nz",
                    "committerName": "Robert Coup",
                    "parents": [],
                    "abbrevParents": [],
                    "datasetChanges": ["nz_pa_points_topo_150k"],
                },
            ]
        else:
            assert json.loads(r.stdout.splitlines()[1]) == {
                "commit": H.POINTS.HEAD1_SHA,
                "abbrevCommit": H.POINTS.HEAD1_SHA[:7],
                "message": "Import from nz-pa-points-topo-150k.gpkg",
                "refs": [],
                "authorEmail": "robert@coup.net.nz",
                "authorName": "Robert Coup",
                "authorTime": "2019-06-11T11:03:58Z",
                "authorTimeOffset": "+01:00",
                "commitTime": "2019-06-11T11:03:58Z",
                "commitTimeOffset": "+01:00",
                "committerEmail": "robert@coup.net.nz",
                "committerName": "Robert Coup",
                "parents": [],
                "abbrevParents": [],
                "datasetChanges": ["nz_pa_points_topo_150k"],
            }


def test_log_arg_parsing_with_range(data_archive_readonly, cli_runner):
    with data_archive_readonly("points"):
        EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        r = cli_runner.invoke(
            [
                "log",
                f"--output-format=json",
                f"{EMPTY_TREE_SHA}..{H.POINTS.HEAD1_SHA}",
            ]
        )
        assert r.exit_code == 0, r.stderr
        commits = json.loads(r.stdout)
        assert len(commits) == 1
        assert commits[0]["commit"] == H.POINTS.HEAD1_SHA


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_log_shallow_clone(
    output_format, data_archive_readonly, cli_runner, tmp_path, chdir
):
    """ review commit history """
    with data_archive_readonly("points") as path:

        clone_path = tmp_path / "shallow.clone"
        r = cli_runner.invoke(
            ["clone", "--bare", "--depth=1", f"file://{path}", str(clone_path)]
        )
        assert r.exit_code == 0, r.stderr

        with chdir(clone_path):
            r = cli_runner.invoke(["log", f"--output-format={output_format}"])
            assert r.exit_code == 0, r.stderr

        if output_format == "text":
            assert r.stdout.splitlines() == [
                f"commit {H.POINTS.HEAD_SHA}",
                "Author: Robert Coup <robert@coup.net.nz>",
                "Date:   Thu Jun 20 15:28:33 2019 +0100",
                "",
                "    Improve naming on Coromandel East coast",
            ]
        else:
            assert json.loads(r.stdout) == [
                {
                    "commit": H.POINTS.HEAD_SHA,
                    "abbrevCommit": H.POINTS.HEAD_SHA[:7],
                    "message": "Improve naming on Coromandel East coast",
                    "refs": ["grafted", "HEAD -> main"],
                    "authorEmail": "robert@coup.net.nz",
                    "authorName": "Robert Coup",
                    "authorTime": "2019-06-20T14:28:33Z",
                    "authorTimeOffset": "+01:00",
                    "commitTime": "2019-06-20T14:28:33Z",
                    "commitTimeOffset": "+01:00",
                    "committerEmail": "robert@coup.net.nz",
                    "committerName": "Robert Coup",
                    "parents": [H.POINTS.HEAD1_SHA],
                    "abbrevParents": [H.POINTS.HEAD1_SHA],
                },
            ]


def test_log_with_feature_count(data_archive, cli_runner):
    """ review commit history """
    with data_archive("points"):
        r = cli_runner.invoke(
            ["log", "--output-format=json", "--with-feature-count=exact"]
        )
        assert r.exit_code == 0, r
        result = json.loads(r.stdout)
        result = [c["featureChanges"] for c in result]
        assert result == [
            {"nz_pa_points_topo_150k": 5},
            {"nz_pa_points_topo_150k": 2143},
        ]
        r = cli_runner.invoke(
            ["log", "--output-format=json", "--with-feature-count=good"]
        )
        assert r.exit_code == 0, r
        result = json.loads(r.stdout)
        result = [c["featureChanges"] for c in result]
        assert result == [
            # in fact these are exactly right (!)
            {"nz_pa_points_topo_150k": 5},
            {"nz_pa_points_topo_150k": 2143},
        ]
        r = cli_runner.invoke(
            ["log", "--output-format=json", "--with-feature-count=veryfast"]
        )
        assert r.exit_code == 0, r
        result = json.loads(r.stdout)
        result = [c["featureChanges"] for c in result]
        assert result == [
            # not quite so accurate, but veryfast
            {"nz_pa_points_topo_150k": 5},
            {"nz_pa_points_topo_150k": 2176},
        ]


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_log_arg_handling(data_archive, cli_runner, output_format):
    """ review commit history """

    def num_commits(r):
        if output_format == "text":
            return len(re.findall(r"(?m)^commit [0-9a-f]{40}$", r.stdout))
        else:
            return len(json.loads(r.stdout))

    with data_archive("points"):
        r = cli_runner.invoke(
            ["log", "-o", output_format, "--", "nz_pa_points_topo_150k"]
        )
        assert r.exit_code == 0, r.stderr
        assert num_commits(r) == 2

        r = cli_runner.invoke(
            ["log", "-o", output_format, "HEAD^", "--", "nz_pa_points_topo_150k"]
        )
        assert r.exit_code == 0, r.stderr
        assert num_commits(r) == 1

        r = cli_runner.invoke(
            ["log", "-o", output_format, "HEAD^", "--", "nonexistent"]
        )
        assert r.exit_code == 0, r.stderr
        assert num_commits(r) == 0

        r = cli_runner.invoke(
            ["log", "-o", output_format, "HEAD^", "nz_pa_points_topo_150k"]
        )
        assert r.exit_code == 0, r.stderr
        assert num_commits(r) == 1

        r = cli_runner.invoke(
            [
                "log",
                "-o",
                output_format,
                "HEAD^",
                "nz_pa_points_topo_150k/.table-dataset/feature/",
            ]
        )
        assert r.exit_code == 0, r.stderr
        assert num_commits(r) == 1

        r = cli_runner.invoke(
            [
                "log",
                "-o",
                output_format,
                "nz_pa_points_topo_150k/.table-dataset/feature/",
            ]
        )
        assert r.exit_code == 0, r.stderr
        assert num_commits(r) == 2

        if output_format == "text":
            # check that we support passing unknown options (e.g. `-p`) on to git log
            r = cli_runner.invoke(
                [
                    "log",
                    "-o",
                    output_format,
                    "1582725544d9122251acd4b3fc75b5c88ac3fd17",
                    "-p",
                    "nz_pa_points_topo_150k/.table-dataset/feature/A/A/A/R/kc0EQA==",
                ]
            )
            assert r.exit_code == 0, r.stderr
            assert "diff --git" in r.stdout

        # NOTE: this will fail the 0.12 release ; at that point we need to remove the code that
        # generates the warning.
        with pytest.warns(
            UserWarning,
            match="Using '--' twice is no longer needed, and will behave differently or fail in Kart 0.12",
        ):
            r = cli_runner.invoke(
                ["log", "-o", output_format, "--", "--", "nz_pa_points_topo_150k"]
            )
            assert r.exit_code == 0, r.stderr
            assert num_commits(r) == 2


@pytest.mark.parametrize(
    "args,expected_commits",
    [
        pytest.param(["-n", "0"], [], id="-n 0"),
        pytest.param(["-n", "1"], [H.POINTS.HEAD_SHA], id="-n 1"),
        pytest.param(["-n1"], [H.POINTS.HEAD_SHA], id="-n1"),
        pytest.param(["-n", "99"], [H.POINTS.HEAD_SHA, H.POINTS.HEAD1_SHA], id="-n 99"),
        pytest.param(["--skip", "1"], [H.POINTS.HEAD1_SHA], id="skip-1"),
        pytest.param(["--", "--skip", "1"], [], id="skip-interpreted-as-path"),
        pytest.param(
            ["--skip", "1", "--"],
            [H.POINTS.HEAD1_SHA],
            id="skip-1-followed-by-doubledash",
        ),
        pytest.param(["--since", "a-broken-date"], [], id="since-broken"),
        pytest.param(["--since", "9999-01-01"], [], id="since-future"),
        pytest.param(
            ["--since", "2000-01-01"],
            [H.POINTS.HEAD_SHA, H.POINTS.HEAD1_SHA],
            id="since-ancient-past",
        ),
        pytest.param(
            ["--since", "2019-06-15"], [H.POINTS.HEAD_SHA], id="since-halfway"
        ),
        pytest.param(
            ["--until", "2019-06-15"], [H.POINTS.HEAD1_SHA], id="until-halfway"
        ),
        pytest.param(
            ["--author", "Robert"],
            [H.POINTS.HEAD_SHA, H.POINTS.HEAD1_SHA],
            id="author-match",
        ),
        pytest.param(["--author", "Telemachus"], [], id="author-no-match"),
        pytest.param(
            ["--committer", "Robert"],
            [H.POINTS.HEAD_SHA, H.POINTS.HEAD1_SHA],
            id="committer-match",
        ),
        pytest.param(["--committer", "Telemachus"], [], id="committer-no-match"),
        pytest.param(["--grep", "Coromandel.*coast"], [H.POINTS.HEAD_SHA], id="grep"),
    ],
)
def test_extra_git_log_options(data_archive, cli_runner, args, expected_commits):
    def get_log_hashes(r):
        return re.findall(r"(?m)^commit ([0-9a-f]{40})$", r.stdout)

    with data_archive("points"):
        r = cli_runner.invoke(["log", *args])
        assert r.exit_code == 0, r.stderr
        assert get_log_hashes(r) == expected_commits
