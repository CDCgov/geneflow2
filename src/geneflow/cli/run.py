"""This module contains methods for the run CLI command."""


import os
import sys
import argparse
from itertools import chain
from pathlib import Path
from multiprocessing import Pool
from functools import partial

try:
    from gooey import Gooey, GooeyParser
except ImportError: pass

import geneflow.cli.common
from geneflow.config import Config
from geneflow.definition import Definition
from geneflow.environment import Environment
from geneflow.log import Log
from geneflow.data import DataSource, DataSourceException
from geneflow.uri_parser import URIParser


def init_subparser(subparsers):
    """Initialize the run CLI subparser."""
    parser = subparsers.add_parser('run', help='run a GeneFlow workflow')
    parser.add_argument(
        'workflow_path',
        type=str,
        help='GeneFlow workflow definition or package directory'
    )
    parser.add_argument(
        '-g','--gui',
        action='store_true',
        default=False,
        help='Use a GUI argument parser'
    )
    parser.set_defaults(func=run)

    return parser


def resolve_workflow_path(workflow_identifier):
    """
    Search GENEFLOW_PATH env var to find workflow definition.

    Args:
        workflow_identifier: workflow identifier

    Returns:
        On success: Full path of workflow yaml file (str).
        On failure: False.

    """
    # check if abs path or in current directory first (.)
    abs_path = Path.absolute(Path(workflow_identifier))
    if abs_path.is_file():
        return str(abs_path)

    if abs_path.is_dir(): # assume this is the name of workflow package dir
        yaml_path = Path(abs_path / 'workflow.yaml')
        if yaml_path.is_file():
            return str(yaml_path)

    # search GENEFLOW_PATH
    gf_path = os.environ.get('GENEFLOW_PATH')

    if gf_path:
        for path in gf_path.split(':'):
            if path:
                wf_path = Path(path) / workflow_identifier
                if wf_path.is_dir():
                    yaml_path = Path(wf_path / 'workflow.yaml')
                    if yaml_path.is_file():
                        return str(yaml_path)

    Log.an().error(
        'workflow "%s" not found, check GENEFLOW_PATH', workflow_identifier
    )
    return False


def set_dict_key_list(dict_obj, keys, val):
    """Update a dict based on given hierarchy of keys and val."""
    for key in keys[:-1]:
        dict_obj = dict_obj.setdefault(key, {})
    dict_obj[keys[-1]] = val


def apply_job_modifiers(jobs_dict, job_mods):
    """Update the jobs_dict with the given modifiers."""
    for key in job_mods:
        # split key at .
        keys = key.split('.')

        # apply to all jobs
        for job in jobs_dict.values():
            set_dict_key_list(job, keys, job_mods[key])


def run(args, other_args, subparser):
    """
    Run GeneFlow workflow engine.

    Args:
        args.workflow_path: workflow definition or package directory.
        args.job: path to job definition

    Returns:
        On success: True.
        On failure: False.

    """
    # get absolute path to workflow
    workflow_path = resolve_workflow_path(args.workflow_path)
    if workflow_path:
        Log.some().info('workflow definition found: %s', workflow_path)
    else:
        Log.an().error('cannot find workflow definition: %s', args.workflow_path)
        return False

    # setup environment
    env = Environment(workflow_path=workflow_path)
    if not env.initialize():
        Log.an().error('cannot initialize geneflow environment')
        return False

    # create default config file and SQLite db
    cfg = Config()
    cfg.default(env.get_sqlite_db_path())
    cfg.write(env.get_config_path())
    config_dict = cfg.config('local')

    # load workflow into db
    try:
        data_source = DataSource(config_dict['database'])
    except DataSourceException as err:
        Log.an().error('data source initialization error [%s]', str(err))
        return False

    defs = data_source.import_definition(workflow_path)
    if not defs:
        Log.an().error('workflow definition load failed: %s', workflow_path)
        return False

    if not defs['workflows']:
        Log.an().error('workflow definition load failed: %s', workflow_path)
        return False

    data_source.commit()

    for workflow in defs['workflows']:
        Log.some().info(
            'workflow loaded: %s -> %s', workflow, defs['workflows'][workflow]
        )

    # get workflow definition back from database to ensure
    # that it's a valid definition
    workflow_id = next(iter(defs['workflows'].values()))
    workflow_dict = data_source.get_workflow_def_by_id(workflow_id)
    if not workflow_dict:
        Log.an().error(
            'cannot get workflow definition from data source: workflow_id=%s',
            workflow_id
        )
        return False

    ### define arg parsing methods
    def parse_dynamic_args(workflow_dict):
        """
        Parse dynamic args based on workflow dictionary as well as
        some static args.

        Args:
            other_args: List of remaining args from initial parse of
                workflow path.
            workflow_dict: Workflow dictionary

        Returns:
            On success: List of parsed arguments.
            On failure: False.

        """
        # parse dynamic args. these are determined from workflow definition
        dynamic_parser = argparse.ArgumentParser()

        dynamic_parser.add_argument(
            '-j', '--job',
            type=str,
            default=None,
            dest='job_path',
            help='Job Definition(s)'
        )
        for input_key in workflow_dict['inputs']:
            dynamic_parser.add_argument(
                '--in.{}'.format(input_key),
                nargs='+',
                type=str,
                dest='inputs.{}'.format(input_key),
                required=False,
                default=workflow_dict['inputs'][input_key]['default'] \
                    if isinstance(workflow_dict['inputs'][input_key]['default'], list) \
                    else [workflow_dict['inputs'][input_key]['default']],
                help=workflow_dict['inputs'][input_key]['label']
            )
        for param_key in workflow_dict['parameters']:
            dynamic_parser.add_argument(
                '--param.{}'.format(param_key),
                dest='parameters.{}'.format(param_key),
                required=False,
                default=workflow_dict['parameters'][param_key]['default'],
                help=workflow_dict['parameters'][param_key]['label']
            )
        dynamic_parser.add_argument(
            '-o', '--output',
            type=str,
            default='~/geneflow-output',
            help='Output Folder'
        )
        dynamic_parser.add_argument(
            '-n', '--name',
            type=str,
            default='geneflow-job',
            help='Name of Job'
        )
        dynamic_parser.add_argument(
            '-w', '--work',
            nargs='+',
            type=str,
            default=[],
            help='Work Directory'
        )
        dynamic_parser.add_argument(
            '--exec-context', '--ec',
            nargs='+',
            type=str,
            dest='exec_context',
            default=[],
            help='Execution Contexts'
        )
        dynamic_parser.add_argument(
            '--exec-method', '--em',
            nargs='+',
            type=str,
            dest='exec_method',
            default=[],
            help='Execution Methods'
        )
        dynamic_parser.add_argument(
            '--exec-param', '--ep',
            nargs='+',
            type=str,
            dest='exec_param',
            default=[],
            help='Execution Parameters'
        )

        dynamic_args = dynamic_parser.parse_known_args(other_args)

        return dynamic_args[0]

    if 'gooey' in sys.modules:
        @Gooey(
            program_name='GeneFlow: {}'.format(workflow_dict['name']),
            program_description=workflow_dict['description'],
            target='gf --log-level={} run {}'.format(args.log_level, args.workflow_path),
            monospace_display=True
        )
        def parse_dynamic_args_gui(workflow_dict):
            """
            Parse dynamic args based on workflow dictionary as well as
            some static args. Display a GUI interface.

            Args:
                other_args: List of remaining args from initial parse of
                    workflow path.
                workflow_dict: Workflow dictionary

            Returns:
                On success: List of parsed arguments.
                On failure: False.

            """
            # parse dynamic args. these are determined from workflow definition
            dynamic_parser = GooeyParser()
            input_group = dynamic_parser.add_argument_group(
                "Workflow Inputs",
                "Files or folders to be passed to the workflow"
            )
            for input_key in workflow_dict['inputs']:
                widget = 'FileChooser'
                if workflow_dict['inputs'][input_key]['type'] == 'Directory':
                    widget = 'DirChooser'
                input_group.add_argument(
                    '--in.{}'.format(input_key),
                    nargs='+',
                    type=str,
                    dest='inputs.{}'.format(input_key),
                    required=False,
                    default=workflow_dict['inputs'][input_key]['default'] \
                        if isinstance(workflow_dict['inputs'][input_key]['default'], list) \
                        else [workflow_dict['inputs'][input_key]['default']],
                    help=workflow_dict['inputs'][input_key]['label'],
                    widget=widget
                )
            param_group = dynamic_parser.add_argument_group(
                "Workflow Parameters",
                "Number or string parameters to be passed to the workflow"
            )
            for param_key in workflow_dict['parameters']:
                param_group.add_argument(
                    '--param.{}'.format(param_key),
                    dest='parameters.{}'.format(param_key),
                    required=False,
                    default=workflow_dict['parameters'][param_key]['default'],
                    help=workflow_dict['parameters'][param_key]['label']
                )
            job_group = dynamic_parser.add_argument_group(
                "Job Options",
                "Output/intermediate folders and job name"
            )
            job_group.add_argument(
                '-o', '--output',
                type=str,
                default='~/geneflow-output',
                help='Output Folder',
                widget='DirChooser'
            )
            job_group.add_argument(
                '-n', '--name',
                type=str,
                default='geneflow-job',
                help='Name of Job'
            )
            job_group.add_argument(
                '-w', '--work',
                nargs='+',
                type=str,
                default=[],
                help='Work Directory'
            )
            exec_group = dynamic_parser.add_argument_group(
                "Execution Options",
                "Customize workflow execution"
            )
            exec_group.add_argument(
                '--exec-context', '--ec',
                nargs='+',
                type=str,
                dest='exec_context',
                default=[],
                help='Execution Contexts'
            )
            exec_group.add_argument(
                '--exec-method', '--em',
                nargs='+',
                type=str,
                dest='exec_method',
                default=[],
                help='Execution Methods'
            )
            exec_group.add_argument(
                '--exec-param', '--ep',
                nargs='+',
                type=str,
                dest='exec_param',
                default=[],
                help='Execution Parameters'
            )

            dynamic_args = dynamic_parser.parse_args(other_args)

            return dynamic_args

    # get dynamic args
    if args.gui and 'gooey' in sys.modules:
        dynamic_args = parse_dynamic_args_gui(workflow_dict)
    else:
        dynamic_args = parse_dynamic_args(workflow_dict)

    # get absolute path to job file if provided
    job_path = None
    if dynamic_args.job_path:
        job_path = Path(dynamic_args.job_path).absolute()

    # load job definition if provided
    jobs_dict = {}
    gf_def = Definition()
    if job_path:
        if not gf_def.load(job_path):
            Log.an().error('Job definition load failed')
            return False
        jobs_dict = gf_def.jobs()
    else:
        # create default definition
        jobs_dict = {
            'job': {
                'name': 'GeneFlow job',
                'output_uri': 'geneflow_output',
                'work_uri': {
                    'local': '~/.geneflow/work'
                }
            }
        }

    # override with known cli parameters
    apply_job_modifiers(
        jobs_dict,
        {
            'name': dynamic_args.name,
            'output_uri': dynamic_args.output
        }
    )

    # insert workflow name into job, if not provided
    workflow_name = next(iter(defs['workflows']))
    for job in jobs_dict.values():
        if 'workflow_name' not in job:
            job['workflow_name'] = workflow_name

    # add inputs and parameters to job definition
    apply_job_modifiers(
        jobs_dict,
        {
            dynamic_arg: getattr(dynamic_args, dynamic_arg)
            for dynamic_arg in vars(dynamic_args) \
                if dynamic_arg.startswith('inputs.') or dynamic_arg.startswith('parameters.')
        }
    )

    # add work URIs to job definition
    work_uris = {}
    for work_arg in dynamic_args.work:
        parsed_work_uri = URIParser.parse(work_arg)
        if not parsed_work_uri:
            # skip if invalid URI
            Log.a().warning('invalid work uri: %s', work_arg)
        else:
            work_uris[parsed_work_uri['scheme']] = parsed_work_uri['chopped_uri']

    apply_job_modifiers(
        jobs_dict,
        {
            'work_uri.{}'.format(context): work_uris[context]
            for context in work_uris
        }
    )

    # add execution options to job definition
    ec_dict = {}
    for exec_arg in dynamic_args.exec_context:
        parts = exec_arg.split(':', 1)[0:2]
        ec_dict['execution.context.{}'.format(parts[0])] = parts[1]
    em_dict = {}
    for exec_arg in dynamic_args.exec_method:
        parts = exec_arg.split(':', 1)[0:2]
        em_dict['execution.method.{}'.format(parts[0])] = parts[1]
    ep_dict = {}
    for exec_arg in dynamic_args.exec_param:
        parts = exec_arg.split(':', 1)[0:2]
        ep_dict['execution.parameters.{}'.format(parts[0])] = parts[1]

    apply_job_modifiers(
        jobs_dict,
        dict(chain(ec_dict.items(), em_dict.items(), ep_dict.items()))
    )

    # get default values from workflow definition
    for job in jobs_dict.values():
        if 'inputs' not in job:
            job['inputs'] = {}
        if 'parameters' not in job:
            job['parameters'] = {}
        for input_key in workflow_dict['inputs']:
            if input_key not in job['inputs']:
                job['inputs'][input_key]\
                    = workflow_dict['inputs'][input_key]['default'] \
                        if isinstance(workflow_dict['inputs'][input_key]['default'], list) \
                        else [workflow_dict['inputs'][input_key]['default']]
        for param_key in workflow_dict['parameters']:
            if param_key not in job['parameters']:
                job['parameters'][param_key]\
                    = workflow_dict['parameters'][param_key]['default']

    # expand URIs
    for job in jobs_dict.values():
        # output URI
        parsed_uri = URIParser.parse(job['output_uri'])
        if not parsed_uri:
            Log.an().error('invalid output uri: %s', job['output_uri'])
            return False
        # expand relative path if local
        if parsed_uri['scheme'] == 'local':
            job['output_uri'] = str(
                Path(parsed_uri['chopped_path']).expanduser().resolve()
            )
        # work URIs
        for context in job['work_uri']:
            parsed_uri = URIParser.parse(job['work_uri'][context])
            if not parsed_uri:
                Log.an().error('invalid work uri: %s', job['work_uri'])
                return False
            # expand relative path if local
            if parsed_uri['scheme'] == 'local':
                job['work_uri'][context] = str(
                    Path(parsed_uri['chopped_path']).expanduser().resolve()
                )
        # input URIs
        for input_key in job['inputs']:
            for i, input_uri in enumerate(job['inputs'][input_key]):
                parsed_uri = URIParser.parse(input_uri)
                if not parsed_uri:
                    Log.an().error(
                        'invalid input uri: %s', input_uri
                    )
                    return False
                # expand relative path if local
                if parsed_uri['scheme'] == 'local':
                    job['inputs'][input_key][i] = str(
                        Path(parsed_uri['chopped_path']).expanduser().resolve()
                    )

    # import jobs into database
    job_ids = data_source.import_jobs_from_dict(jobs_dict)
    if job_ids is False:
        Log.an().error('cannot import jobs')
        return False
    data_source.commit()

    # create process pool to run workflows in parallel
    pool = Pool(min(5, len(job_ids)))
    jobs = [
        {
            'name': job,
            'id': job_ids[job],
            'log': None
        } for job in job_ids
    ]

    result = pool.map(
        partial(
            geneflow.cli.common.run_workflow,
            config=config_dict,
            log_level=args.log_level
        ),
        jobs
    )

    pool.close()
    pool.join()

    if not all(result):
        Log.an().error('some jobs failed')

    return result
