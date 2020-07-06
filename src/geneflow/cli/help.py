"""This module contains methods for the help CLI command."""


import os
from pathlib import Path

from geneflow.definition import Definition
from geneflow.log import Log


def init_subparser(subparsers):
    """Initialize the help CLI subparser."""
    parser = subparsers.add_parser('help', help='GeneFlow workflow help')
    parser.add_argument(
        'workflow',
        type=str,
        help='GeneFlow workflow definition or package directory'
    )
    parser.set_defaults(func=help_func)

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


def help_func(args, other_args, subparser=None):
    """
    GeneFlow workflow help.

    Args:
        args.workflow: workflow definition or package directory.

    Returns:
        On success: True.
        On failure: False.

    """
    # get absolute path to workflow
    workflow_yaml = resolve_workflow_path(args.workflow)
    if workflow_yaml:
        Log.some().info('workflow definition found: %s', workflow_yaml)
    else:
        Log.an().error('cannot find workflow definition: %s', args.workflow)
        return False

    # load workflow
    gf_def = Definition()
    if not gf_def.load(workflow_yaml):
        Log.an().error('workflow definition load failed: %s', workflow_yaml)
        return False

    # get first workflow dict
    workflow_dict = next(iter(gf_def.workflows().values()))
    print()
    print('{}: {}'.format(workflow_dict['name'], workflow_dict['description']))
    print()
    print('Execution Command:')
    print('\tgf [--log-level LOG_LEVEL] [--log-file LOG_FILE] run WORKFLOW_PATH')
    print('\t\t-o OUTPUT [-n NAME] [INPUTS] [PARAMETERS] [-w WORK_DIR [WORK_DIR ...]]')
    print('\t\t[--ec CONTEXT [CONTEXT ...]] [--em METHOD [METHOD ...]] [--ep PARAM [PARAM ...]]')
    print()
    print('\tWORKFLOW_PATH: Path to directory that contains workflow definition')
    print()
    print('Job Configuration:')
    print('\t-o,--output: Output directory')
    print('\t-n,--name: Job name, a directory with this name will be created in the output directory')
    print('\t\tdefault: geneflow-job')
    print('\t-w,--work: Work directories, for temporary or intermediate data')
    print('\t\tdefault: ~/.geneflow/work')
    print()
    print('Inputs: Workflow-Specific Files or Folders')
    for input_key in workflow_dict['inputs']:
        print(
            '\t--in.{}: {}: {}'.format(
                input_key,
                workflow_dict['inputs'][input_key]['label'],
                workflow_dict['inputs'][input_key]['description']
            )
        )
        print(
            '\t\ttype: {}, default: {}'.format(
                workflow_dict['inputs'][input_key]['type'],
                workflow_dict['inputs'][input_key]['default']
            )
        )
    print()
    print('Parameters: Workflow-Specific Values')
    for param_key in workflow_dict['parameters']:
        print(
            '\t--param.{}: {}: {}'.format(
                param_key,
                workflow_dict['parameters'][param_key]['label'],
                workflow_dict['parameters'][param_key]['description']
            )
        )
        print(
            '\t\ttype: {}, default: {}'.format(
                workflow_dict['parameters'][param_key]['type'],
                workflow_dict['parameters'][param_key]['default']
            )
        )
    print()
    print('Execution Configuration:')
    print('\t--ec,--exec-context: Execution contexts, e.g., local, agave, gridengine.')
    print('\t\tThese can be specified for all workflow steps with "default:[CONTEXT]"')
    print('\t\tor for specific steps with "step-name:[CONTEXT]".')
    print('\t--em,--exec-method: Exeuction methods, e.g., singularity, docker, environment.')
    print('\t\tThese can be specified for all workflow steps with "default:[METHOD]"')
    print('\t\tor for specific steps with "step-name:[METHOD]". By default each app associated')
    print('\t\twith a workflow step tries to automatically detect the execution method.')
    print('\t--ep,--exec-param: Execution parameters, e.g., slots, mem, or other.')
    print('\t\tThese can be specified for all workflow steps with "default.slots:[VALUE]"')
    print('\t\tor for specific steps with "step-name.slots:[VALUE]". Execution parameters')
    print('\t\tdepend on the execution context.')

    return True
