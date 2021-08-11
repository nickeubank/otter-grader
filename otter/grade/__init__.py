"""Local grading of submissions in Docker containers for Otter-Grader"""

import os
import pandas as pd
import re

from .containers import launch_grade
from .metadata import GradescopeParser, CanvasParser, JSONParser, YAMLParser
from .utils import merge_csv, prune_images

from ..utils import assert_path_exists


def main(*, path="./", output_dir="./", autograder="./autograder.zip", gradescope=False, 
         canvas=False, json=False, yaml=False, containers=None, scripts=False, no_kill=False, 
         debug=False, zips=False, image="ucbdsinfra/otter-grader", pdfs=False, verbose=False,
         prune=False, force=False):
    """
    Runs Otter Grade

    Grades a directory of submissions in parallel Docker containers. Results are outputted as a CSV file
    called ``final_grades.csv``. If ``prune`` is ``True``, Otter's dangling grading images are pruned 
    and the program exits.

    Args:
        path (``str``): path to directory of submissions
        output_dir (``str``): directory in which to write ``final_grades.csv``
        autograder (``str``): path to Otter autograder configuration zip file
        gradescope (``bool``): whether submissions are a Gradescope export
        canvas (``bool``): whether submissions are a Canvas export
        json (``str``): path to a JSON metadata file
        yaml (``str``): path to a YAML metadata file
        containers (``int``): number of containers to run in parallel
        scripts (``bool``): whether Python scripts are being graded
        no_kill (``bool``): whether to keep containers after grading is finished
        debug (``bool``): whether to print the stdout of each container
        zips (``bool``): whether the submissions are Otter-exported zip files
        image (``bool``): base image from which to build grading image
        pdfs (``bool``): whether to copy notebook PDFs out of the containers
        verbose (``bool``): whether to log status messages to stdout
        prune (``bool``): whether to prune the grading images; if true, no grading is performed
        force (``bool``): whether to force-prune the images (do not ask for confirmation)

    Raises:
        ``AssertionError``: if invalid arguments are provided
    """
    if prune:
        prune_images(force=force)
        return

    # Asserts that exactly one metadata flag is provided
    assert sum([meta != False for meta in [
        gradescope,
        canvas,
        json,
        yaml
    ]]) <= 1, "You can specify at most one metadata flag (-g, -j, -y, -c)"

    # check file paths
    assert_path_exists([
        (path, True),
        (output_dir, True),
        (autograder, False),
    ])

    if json:
        assert_path_exists([(json, False)])

    if yaml:
        assert_path_exists([(yaml, False)])

    # Hand off metadata to parser
    if gradescope:
        meta_parser = GradescopeParser(path)
        if verbose:
            print("Found Gradescope metadata...")
    elif canvas:
        meta_parser = CanvasParser(path)
        if verbose:
            print("Found Canvas metadata...")
    elif json:
        meta_parser = JSONParser(os.path.join(json))
        if verbose:
            print("Found JSON metadata...")
    elif yaml:
        meta_parser = YAMLParser(os.path.join(yaml))
        if verbose:
            print("Found YAML metadata...")
    else:
        meta_parser = None

    if verbose:
        print("Launching docker containers...")

    #Docker
    grade_dfs = launch_grade(autograder,
        notebooks_dir=path,
        verbose=verbose,
        num_containers=containers,
        scripts=scripts,
        no_kill=no_kill,
        output_path=output_dir,
        debug=debug,
        zips=zips,
        image=image,
        pdfs=pdfs
    )

    if verbose:
        print("Combining grades and saving...")

    # Merge Dataframes
    output_df = merge_csv(grade_dfs)

    def map_files_to_ids(row):
        """Returns the identifier for the filename in the specified row"""
        return meta_parser.file_to_id(row["file"])

    # add in identifier column
    if meta_parser is not None:
        output_df["identifier"] = output_df.apply(map_files_to_ids, axis=1)
        output_df.drop("file", axis=1, inplace=True)

        # reorder cols in output_df
        cols = output_df.columns.tolist()
        output_df = output_df[cols[-1:] + cols[:-1]]

    # write to CSV file
    output_df.to_csv(os.path.join(output_dir, "final_grades.csv"), index=False)
