"""SciUnit command line tools.

With SciUnit installed, a .sciunit configuration file can be created from
a *nix shell with:
`sciunit create`
and if models, tests, etc. are in locations specified by the configuration file
then they can be executed with
`sciunit run` (to run using the Python interpreter)
or
`sciunit make-nb` (to create Jupyter notebooks for test execution)
and
`sciunit run-nb` (to execute and save those notebooks)
"""

import sys
import os
import argparse
import re

import nbformat
from nbformat.v4.nbbase import new_notebook, new_markdown_cell
from nbconvert.preprocessors import ExecutePreprocessor
from typing import Tuple
import sciunit
from pathlib import Path
from typing import Union
import configparser

import codecs

import matplotlib
matplotlib.use('Agg')  #: Anticipate possible headless environments

NB_VERSION = 4


def main(*args):
    """Launch the main routine."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action",
                        help="create, check, run, make-nb, or run-nb")
    parser.add_argument("--directory", "-dir", default=os.getcwd(),
                        help="path to directory with a .sciunit file")
    parser.add_argument("--stop", "-s", default=True,
                        help="stop and raise errors, halting the program")
    parser.add_argument("--tests", "-t", default=False,
                        help="runs tests instead of suites")
    if args:
        args = parser.parse_args(args)
    else:
        args = parser.parse_args()
    file_path = os.path.join(args.directory, '.sciunit')
    config = None
    if args.action == 'create':
        create(file_path)
    elif args.action == 'check':
        config = parse(file_path, show=True)
        print("\nNo configuration errors reported.")
    elif args.action == 'run':
        config = parse(file_path)
        run(config, path=args.directory,
            stop_on_error=args.stop, just_tests=args.tests)
    elif args.action == 'make-nb':
        config = parse(file_path)
        make_nb(config, path=args.directory,
                stop_on_error=args.stop, just_tests=args.tests)
    elif args.action == 'run-nb':
        config = parse(file_path)
        run_nb(config, path=args.directory)
    else:
        raise NameError('No such action %s' % args.action)
    if config:
        cleanup(config, path=args.directory)


def create(file_path: str) -> None:
    """Create a default .sciunit config file if one does not already exist.

    Args:
        file_path (str): The path of sciunit config file that will be created.

    Raises:
        IOError: There is already a configuration file at the path.
    """
    if os.path.exists(file_path):
        raise IOError("There is already a configuration file at %s" %
                      file_path)
    with open(file_path, 'w') as f:
        config = configparser.ConfigParser()
        config.add_section('misc')
        config.set('misc', 'config-version', '1.0')
        default_nb_name = os.path.split(os.path.dirname(file_path))[1]
        config.set('misc', 'nb-name', default_nb_name)
        config.add_section('root')
        config.set('root', 'path', '.')
        config.add_section('models')
        config.set('models', 'module', 'models')
        config.add_section('tests')
        config.set('tests', 'module', 'tests')
        config.add_section('suites')
        config.set('suites', 'module', 'suites')
        config.write(f)


def parse(file_path: str=None, show: bool=False) -> configparser.RawConfigParser:
    """Parse a .sciunit config file.

    Args:
        file_path (str, optional): The path of sciunit config file that will be parsed. Defaults to None.
        show (bool, optional): Whether or not print the sections in the config file. Defaults to False.

    Raises:
        IOError: Raise an exception if no .sciunit file was found.

    Returns:
        RawConfigParser: The basic configuration object.
    """
    if file_path is None:
        file_path = os.path.join(os.getcwd(), '.sciunit')
    if not os.path.exists(file_path):
        raise IOError('No .sciunit file was found at %s' % file_path)

    # Load the configuration file
    config = configparser.RawConfigParser(allow_no_value=True)
    config.read(file_path)

    # List all contents
    for section in config.sections():
        if show:
            print(section)
        for options in config.options(section):
            if show:
                print("\t%s: %s" % (options, config.get(section, options)))
    return config


def prep(config: configparser.RawConfigParser=None, path: Union[str, Path]=None) -> None:
    """Prepare to read the configuration information.

    Args:
        config (RawConfigParser, optional): The configuration object. Defaults to None.
        path (Union[str, Path], optional): The path of config file. Defaults to None.
    """
    if config is None:
        config = parse()
    if path is None:
        path = os.getcwd()
    root = config.get('root', 'path')
    root = os.path.join(path, root)
    root = os.path.realpath(root)
    os.environ['SCIDASH_HOME'] = root
    if sys.path[0] != root:
        sys.path.insert(0, root)


def run(config: configparser.RawConfigParser, path: Union[str, Path]=None, 
        stop_on_error: bool=True, just_tests: bool=False) -> None:
    """Run sciunit tests for the given configuration.

    Args:
        config (RawConfigParser): The configuration object.
        path (Union[str, Path], optional): [description]. Defaults to None.
        stop_on_error (bool, optional): [description]. Defaults to True.
        just_tests (bool, optional): [description]. Defaults to False.
    """
    if path is None:
        path = os.getcwd()
    prep(config, path=path)

    models = __import__('models')
    tests = __import__('tests')
    suites = __import__('suites')

    print('\n')
    for x in ['models', 'tests', 'suites']:
        module = __import__(x)
        assert hasattr(module, x), "'%s' module requires attribute '%s'" %\
                                   (x, x)

    if just_tests:
        for test in tests.tests:
            _run(test, models, stop_on_error)

    else:
        for suite in suites.suites:
            _run(suite, models, stop_on_error)


def _run(test_or_suite: Union[sciunit.Test, sciunit.TestSuite], models: list, stop_on_error: bool) -> None:
    """[summary]

    Args:
        test_or_suite (Union[Test, TestSuite]): A test or suite instance to be executed.
        models (list): The list of sciunit Model.
        stop_on_error (bool): Whether to stop on error. 
    """
    score_array_or_matrix = test_or_suite.judge(models.models,
                                                stop_on_error=stop_on_error)
    kind = 'Test' if isinstance(test_or_suite, sciunit.Test) else 'Suite'
    print('\n%s %s:\n%s\n' % (kind, test_or_suite, score_array_or_matrix))


def nb_name_from_path(config: dict, path: Union[str, Path]) -> tuple:
    """Get a notebook name from a path to a notebook.

    Args:
        config (dict): [description]
        path (Union[str, Path]): The path of the notebook file.

    Returns:
        tuple: Notebook root node and name of the notebook.
    """
    if path is None:
        path = os.getcwd()
    root = config.get('root', 'path')
    root = os.path.join(path, root)
    root = os.path.realpath(root)
    default_nb_name = os.path.split(os.path.realpath(root))[1]
    nb_name = config.get('misc', 'nb-name', fallback=default_nb_name)
    return root, nb_name


def make_nb(config, path: Union[str, Path]=None, stop_on_error: bool=True, just_tests: bool=False) -> None:
    """Create a Jupyter notebook sciunit tests for the given configuration.

    Args:
        config ([type]): [description]
        path (Union[str, Path], optional): A path to the notebook file. Defaults to None.
        stop_on_error (bool, optional): Whether to stop on an error. Defaults to True.
        just_tests (bool, optional): [description]. Defaults to False.
    """
    root, nb_name = nb_name_from_path(config, path)
    clean = lambda varStr: re.sub('\W|^(?=\d)', '_', varStr)
    name = clean(nb_name)

    mpl_style = config.get('misc', 'matplotlib', fallback='inline')
    cells = [new_markdown_cell('## Sciunit Testing Notebook for %s' % nb_name)]
    add_code_cell(cells, (
        "%%matplotlib %s\n"
        "from IPython.display import display\n"
        "from importlib.machinery import SourceFileLoader\n"
        "%s = SourceFileLoader('scidash', '%s/__init__.py').load_module()") %
        (mpl_style, name, root))
    if just_tests:
        add_code_cell(cells, (
            "for test in %s.tests.tests:\n"
            "  score_array = test.judge(%s.models.models, stop_on_error=%r)\n"
            "  display(score_array)") % (name, name, stop_on_error))
    else:
        add_code_cell(cells, (
            "for suite in %s.suites.suites:\n"
            "  score_matrix = suite.judge("
            "%s.models.models, stop_on_error=%r)\n"
            "  display(score_matrix)") % (name, name, stop_on_error))
    write_nb(root, nb_name, cells)


def write_nb(root, nb_name, cells) -> None:
    """Write a jupyter notebook to disk.

    Takes a given a root directory, a notebook name, and a list of cells.

    Args:
        root ([type]): The root node (section) of the notebook.
        nb_name ([type]): [description]
        cells ([type]): The cells of the notebook.
    """
    nb = new_notebook(cells=cells,
                      metadata={
                        'language': 'python',
                        })
    nb_path = os.path.join(root, '%s.ipynb' % nb_name)
    with codecs.open(nb_path, encoding='utf-8', mode='w') as nb_file:
        nbformat.write(nb, nb_file, NB_VERSION)
    print("Created Jupyter notebook at:\n%s" % nb_path)


def run_nb(config, path: Union[str, Path]=None) -> None:
    """Run a notebook file.

    Runs the one specified by the config file, or the one at
    the location specificed by 'path'.

    Args:
        config ([type]): [description]
        path (Union[str, Path], optional): The path to the notebook file. Defaults to None.
    """
    if path is None:
        path = os.getcwd()
    root = config.get('root', 'path')
    root = os.path.join(path, root)
    nb_name = config.get('misc', 'nb-name')
    nb_path = os.path.join(root, '%s.ipynb' % nb_name)
    if not os.path.exists(nb_path):
        print(("No notebook found at %s. "
               "Create the notebook first with make-nb?") % path)
        sys.exit(0)

    with codecs.open(nb_path, encoding='utf-8', mode='r') as nb_file:
        nb = nbformat.read(nb_file, as_version=NB_VERSION)
    ep = ExecutePreprocessor(timeout=600)
    ep.preprocess(nb, {'metadata': {'path': root}})
    with codecs.open(nb_path, encoding='utf-8', mode='w') as nb_file:
        nbformat.write(nb, nb_file, NB_VERSION)


def add_code_cell(cells, source) -> None:
    """Add a code cell containing `source` to the notebook.

    Args:
        cells ([type]): [description]
        source ([type]): [description]
    """
    from nbformat.v4.nbbase import new_code_cell
    n_code_cells = len([c for c in cells if c['cell_type'] == 'code'])
    cells.append(new_code_cell(source=source, execution_count=n_code_cells+1))


def cleanup(config=None, path: Union[str, Path]=None) -> None:
    """Cleanup by removing paths added during earlier in configuration.

    Args:
        config ([type], optional): [description]. Defaults to None.
        path (Union[str, Path], optional): [description]. Defaults to None.
    """
    if config is None:
        config = parse()
    if path is None:
        path = os.getcwd()
    root = config.get('root', 'path')
    root = os.path.join(path, root)
    if sys.path[0] == root:
        sys.path.remove(root)


if __name__ == '__main__':
    main()
