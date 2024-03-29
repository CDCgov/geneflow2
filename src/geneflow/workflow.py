"""This module contains the GeneFlow Workflow class."""


import time

import copy
import requests
from slugify import slugify
import yaml

from geneflow.log import Log
from geneflow.data import DataSource, DataSourceException
from geneflow.data_manager import DataManager
from geneflow.definition import Definition
from geneflow.workflow_dag import WorkflowDAG, WorkflowDAGException
from geneflow.uri_parser import URIParser
from geneflow.extend.contexts import Contexts


class Workflow:
    """Wraps workflow, job, app loading and running calls."""

    def __init__(self, job_id, config):
        """
        Initialize the GeneFlow Workflow class.

        Initialize the class by loading the job and the config.

        Args:
            self: class instance
            job_id: Job identifier
            config: the Workflow subsection of the GeneFlow configuration

        Returns:
            Class instance.

        """
        self._config = config        # configuration structure
        self._job_id = job_id
        self._job = None             # job definition
        self._workflow = None        # workflow definition
        self._apps = None            # app definitions
        self._dag = None             # WorkflowDAG class instance
        self._status = 'PENDING'

        self._parsed_job_work_uri = {}
        self._parsed_job_output_uri = {}

        self._exec_contexts = set() # all execution contexts
        self._data_contexts = set() # all data contexts

        # context-specific data and methods
        self._workflow_context = {}


    def initialize(self):
        """
        Initialize the GeneFlow Workflow class.

        Initialize the class by loading the workflow and job definitions
        from the database, creating work and output URIs, and creating step
        objects.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        # load and validate job definition from database
        if not self._load_job():
            msg = 'cannot load job definition'
            Log.an().error(msg)
            return self._fatal(msg)

        # load and validate workflow definition from database
        if not self._load_workflow():
            msg = 'cannot load workflow definition'
            Log.an().error(msg)
            return self._fatal(msg)

        # load and validate app definitions from database
        if not self._load_apps():
            msg = 'cannot load app definitions'
            Log.an().error(msg)
            return self._fatal(msg)

        # inject job parameters into workflow def
        if not self._inject_job_params():
            msg = 'cannot inject job parameters into workflow definition'
            Log.an().error(msg)
            return self._fatal(msg)

        # initialize set of execution contexts
        if not self._init_exec_context_set():
            msg = 'cannot initialize set of execution contexts'
            Log.an().error(msg)
            return self._fatal(msg)

        # initialize set of data contexts
        if not self._init_data_context_set():
            msg = 'cannot initialize set of data contexts'
            Log.an().error(msg)
            return self._fatal(msg)

        # validate all work and output URIs
        if not self._init_job_uris():
            msg = 'cannot construct and validate work and output uris'
            Log.an().error(msg)
            return self._fatal(msg)

        # initialize context-specific workflow items (e.g., agave connection)
        if not self._init_workflow_contexts():
            msg = 'cannot initialize context-specific workflow properties'
            Log.an().error(msg)
            return self._fatal(msg)

        # create all work and output URIs
        if not self._create_job_uris():
            msg = 'cannot create work and output uris'
            Log.an().error(msg)
            return self._fatal(msg)

        # initialize context-specific workflow data items (e.g., archive_uri
        #  for agave)
        if not self._init_workflow_context_data():
            msg = 'cannot initialize context-specific workflow data'
            Log.an().error(msg)
            return self._fatal(msg)

        # initialize directed acyclic graph structure
        if not self._init_dag():
            msg = 'cannot initialize workflow graph structure'
            Log.an().error(msg)
            return self._fatal(msg)

        return True


    def __str__(self):
        """
        Workflow string representation.

        Args:
            None.

        Returns:
            A string representation of the workflow.

        """
        str_rep = (
            'Job: {} ({})'
            '\n    Workflow: {}'
            '\n        Version: {}'
            '\n        Description: {}'
            '\n        Git: {}'
        ).format(
            self._job['name'],
            self._job_id,
            self._workflow['name'],
            self._workflow['version'],
            self._workflow['description'],
            self._workflow['git']
        )

        str_rep += '\n    Inputs: '
        for input_key in self._workflow['inputs']:
            str_rep += '\n        {}: {}'.format(
                input_key, self._workflow['inputs'][input_key]['value']
            )

        str_rep += '\n    Parameters: '
        for parameter_key in self._workflow['parameters']:
            str_rep += '\n        {}: {}'.format(
                parameter_key,
                self._workflow['parameters'][parameter_key]['value']
            )

        str_rep += '\n    Work URIs: '
        for context in self._parsed_job_work_uri:
            str_rep += '\n        {}: {}'.format(
                context, self._parsed_job_work_uri[context]['chopped_uri']
            )

        str_rep += '\n    Output URI: {}'.format(
            self._parsed_job_output_uri['chopped_uri']
        )

        return str_rep


    def _fatal(self, msg):

        self._update_status_db('ERROR', msg)

        return False


    def _load_job(self):
        """
        Load and validate job definition from the database.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        try:
            data_source = DataSource(self._config['database'])
        except DataSourceException as err:
            msg = 'data source initialization error [{}]'.format(str(err))
            Log.an().error(msg)
            return self._fatal(msg)

        self._job = data_source.get_job_def_by_id(self._job_id)
        if self._job is False:
            msg = 'cannot load job from data source: job_id={}'\
                .format(self._job_id)
            Log.an().error(msg)
            return self._fatal(msg)

        if not self._job:
            msg = 'job not found: job_id={}'.format(self._job_id)
            Log.an().error(msg)
            return self._fatal(msg)

        # validate the job definition
        valid_def = Definition.validate_job(self._job)
        if valid_def is False:
            msg = 'invalid job definition:\n{}'.format(yaml.dump(self._job))
            Log.an().error(msg)
            return self._fatal(msg)

        self._job = valid_def

        return True


    def _load_workflow(self):
        """
        Load and validate workflow definition from the database.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        try:
            data_source = DataSource(self._config['database'])
        except DataSourceException as err:
            msg = 'data source initialization error [{}]'.format(str(err))
            Log.an().error(msg)
            return self._fatal(msg)

        self._workflow = data_source.get_workflow_def_by_id(
            self._job['workflow_id']
        )
        if self._workflow is False:
            msg = 'cannot load workflow from data source: workflow_id={}'.\
                format(self._job['workflow_id'])
            Log.an().error(msg)
            return self._fatal(msg)

        if not self._workflow:
            msg = 'workflow not found: workflow_id={}'\
                .format(self._job['workflow_id'])
            Log.an().error(msg)
            return self._fatal(msg)

        # validate the workflow definition
        valid_def = Definition.validate_workflow(self._workflow)
        if valid_def is False:
            msg = 'invalid workflow definition:\n{}'\
                .format(yaml.dump(self._workflow))
            Log.an().error(msg)
            return self._fatal(msg)

        self._workflow = valid_def

        return True


    def _load_apps(self):
        """
        Load and validate app definitions from the database.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        try:
            data_source = DataSource(self._config['database'])
        except DataSourceException as err:
            msg = 'data source initialization error [{}]'.format(str(err))
            Log.an().error(msg)
            return self._fatal(msg)

        self._apps = data_source.get_app_defs_by_workflow_id(
            self._job['workflow_id']
        )
        if self._apps is False:
            msg = 'cannot load apps from data source: workflow_id={}'.\
                format(self._job['workflow_id'])
            Log.an().error(msg)
            return self._fatal(msg)

        if not self._apps:
            msg = 'no apps found for workflow: workflow_id={}'.\
                format(self._job['workflow_id'])
            Log.an().error(msg)
            return self._fatal(msg)

        # validate the app definitions
        for app in self._apps:
            valid_def = Definition.validate_app(self._apps[app])
            if valid_def is False:
                msg = 'invalid app definition:\n{}'\
                    .format(yaml.dump(self._apps[app]))
                Log.an().error(msg)
                return self._fatal(msg)

            self._apps[app] = valid_def

        return True


    def _inject_job_params(self):

        # substitute inputs
        for input_key in self._workflow['inputs']:
            self._workflow['inputs'][input_key]['value']\
                = self._workflow['inputs'][input_key]['default']
        for input_key in self._job['inputs']:
            if input_key in self._workflow['inputs']:
                self._workflow['inputs'][input_key]['value']\
                    = self._job['inputs'][input_key]

        # substitute parameters
        for parameter_key in self._workflow['parameters']:
            self._workflow['parameters'][parameter_key]['value']\
                = self._workflow['parameters'][parameter_key]['default']
        for parameter_key in self._job['parameters']:
            if parameter_key in self._workflow['parameters']:
                self._workflow['parameters'][parameter_key]['value']\
                    = self._job['parameters'][parameter_key]

        # update final output
        if self._job['final_output']:
            self._workflow['final_output'] = self._job['final_output']

        # insert step execution parameters
        for step_name, step in self._workflow['steps'].items():
            step['execution'] = {
                'context': self._job['execution']['context']['default'],
                'method': self._job['execution']['method']['default'],
                'parameters': copy.deepcopy(self._job['execution']['parameters']['default'])
            }
            if step_name in self._job['execution']['context']:
                step['execution']['context'] \
                    = self._job['execution']['context'][step_name]
            if step_name in self._job['execution']['method']:
                step['execution']['method'] \
                    = self._job['execution']['method'][step_name]
            if step_name in self._job['execution']['parameters']:
                # only copy params that have been set to avoid deleting default params
                for param_name in self._job['execution']['parameters'][step_name]:
                    step['execution']['parameters'][param_name] \
                        = self._job['execution']['parameters'][step_name][param_name]

        return True


    def _init_exec_context_set(self):
        """
        Initialize set of execution contexts, which is specified by the execution.context job
        parameters.

        Args:
            self: class instance

        Returns:
            On success: True.

        """
        # get explicit execution contexts from the job parameters
        self._exec_contexts = set(self._job['execution']['context'].values())

        # check validity of exec contexts
        for context in self._exec_contexts:
            if not Contexts.is_exec_context(context):
                msg = 'invalid exec context: {}'.format(context)
                Log.an().error(msg)
                return self._fatal(msg)

        Log.some().debug('execution contexts: %s', self._exec_contexts)

        return True


    def _init_data_context_set(self):
        """
        Initialize set of data contexts, which is determined by inputs and output.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        # check input URIs for data contexts
        for input_key in self._workflow['inputs']:
            parsed_uri = URIParser.parse(self._workflow['inputs'][input_key]['value'][0])
            if not parsed_uri:
                msg = 'invalid input uri: {}'.format(
                    self._workflow['inputs'][input_key]['value'][0]
                )
                Log.an().error(msg)
                return self._fatal(msg)

            self._data_contexts.add(parsed_uri['scheme'])

        # add output URI data context
        parsed_output_uri = URIParser.parse(self._job['output_uri'])
        if not parsed_output_uri:
            msg = 'invalid base of job output uri: {}'.format(
                self._job['output_uri']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        self._data_contexts.add(parsed_output_uri['scheme'])

        # check validity of data contexts
        for context in self._data_contexts:
            if not Contexts.is_data_context(context):
                msg = 'invalid data context: {}'.format(context)
                Log.an().error(msg)
                return self._fatal(msg)

        Log.some().debug('data contexts: %s', self._data_contexts)

        return True


    def _init_job_uris(self):
        """
        Initialize all work and output URIs.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        # name of the job directory
        job_dir = slugify(self._job['name'], regex_pattern=r'[^-a-z0-9_]+')
        job_dir_hash = '{}-{}'.format(job_dir, self._job['job_id'][:8])

        # validate work URI for each exec context
        #   use the 'data_scheme' for each execution context
        #   and place into a set to remove repeats
        for context in {
                Contexts.get_data_scheme_of_exec_context(con)
                for con in self._exec_contexts
        }:
            # work_uri must be set for each exec_context
            if context not in self._job['work_uri']:
                msg = 'missing work_uri for context: {}'.format(context)
                Log.an().error(msg)
                return self._fatal(msg)

            parsed_uri = URIParser.parse(self._job['work_uri'][context])
            if not parsed_uri:
                msg = 'invalid base of job work uri for context: {}->{}'.format(
                    context, self._job['work_uri'][context]
                )
                Log.an().error(msg)
                return self._fatal(msg)

            # append hashed job dir to each context
            full_job_work_uri = (
                '{}{}' if parsed_uri['chopped_path'] == '/' else '{}/{}'
            ).format(parsed_uri['chopped_uri'], job_dir_hash)

            # validate again after appending
            parsed_job_work_uri = URIParser.parse(full_job_work_uri)

            if not parsed_job_work_uri:
                msg = 'invalid job work uri for context: {}->{}'.format(
                    context, full_job_work_uri
                )
                Log.an().error(msg)
                return self._fatal(msg)

            self._parsed_job_work_uri[context] = parsed_job_work_uri


        # validate output URI
        parsed_uri = URIParser.parse(self._job['output_uri'])
        if not parsed_uri:
            msg = 'invalid base of job output uri: {}'.format(
                self._job['output_uri']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        # append job dir (hashed or not) to output uri
        full_job_output_uri = (
            '{}{}' if parsed_uri['chopped_path'] == '/' else '{}/{}'
        ).format(
            parsed_uri['chopped_uri'],
            job_dir if self._job['no_output_hash'] else job_dir_hash
        )

        # validate again after appending
        parsed_job_output_uri = URIParser.parse(full_job_output_uri)

        if not parsed_job_output_uri:
            msg = 'invalid job output uri: {}'.format(
                full_job_output_uri
            )
            Log.an().error(msg)
            return self._fatal(msg)

        self._parsed_job_output_uri = parsed_job_output_uri

        return True


    def _init_workflow_context_data(self):
        """
        Initialize data components of workflow contexts.

        Args:
            None.

        Returns:
            On success: True.
            On failure: False.

        """
        for exec_context in self._exec_contexts:
            if not self._workflow_context[exec_context].init_data():
                msg = (
                    'cannot initialize data for workflow context: {}'\
                        .format(exec_context)
                )
                Log.an().error(msg)
                return self._fatal(msg)

        return True


    def _init_workflow_contexts(self):
        """
        Import modules and load classes for each workflow context.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        # currently the union of all execution and data contexts will be used
        # to initialize workflow contexts/classes. the reason is that all supported
        # data contexts are also execution contexts. This may change in the future
        # with data-only contexts (e.g., http/s). In that case, a new method
        # (_init_data_contexts) will be added to populate a _data_context variable.
        for context in self._exec_contexts | self._data_contexts:

            mod_name = '{}_workflow'.format(context)
            cls_name = '{}Workflow'.format(context.capitalize())

            try:
                workflow_mod = __import__(
                    'geneflow.extend.{}'.format(mod_name),
                    fromlist=[cls_name]
                )
            except ImportError as err:
                msg = 'cannot import workflow module: {} [{}]'.format(
                    mod_name, str(err)
                )
                Log.an().error(msg)
                return self._fatal(msg)

            try:
                workflow_class = getattr(workflow_mod, cls_name)
            except AttributeError as err:
                msg = 'cannot import workflow class: {} [{}]'.format(
                    cls_name, str(err)
                )
                Log.an().error(msg)
                return self._fatal(msg)

            self._workflow_context[context] = workflow_class(
                self._config, self._job, self._parsed_job_work_uri
            )

            # perform context-specific init
            if not self._workflow_context[context].initialize():
                msg = (
                    'cannot initialize workflow context: {}'.format(cls_name)
                )
                Log.an().error(msg)
                return self._fatal(msg)

        return True


    def _create_job_uris(self):
        """
        Create all work and output URIs.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        # create work URIs. a work URI is required for each workflow context
        for context in {
                Contexts.mapping[exec_context]['data_scheme']
                for exec_context in self._exec_contexts
        }:
            if not DataManager.mkdir(
                    parsed_uri=self._parsed_job_work_uri[context],
                    recursive=True,
                    **{
                        context: self._workflow_context[context]\
                        .get_context_options()
                    }
            ):
                msg = 'cannot create job work uri for context: {}->{}'.format(
                    context, self._parsed_job_work_uri[context]['chopped_uri']
                )
                Log.an().error(msg)
                return self._fatal(msg)

        # create output URI. output URI scheme must be in the set of data contexts
        output_context = self._parsed_job_output_uri['scheme']
        if output_context not in self._data_contexts:
            msg = 'invalid output context: {}'.format(output_context)
            Log.an().error(msg)
            return self._fatal(msg)

        if not DataManager.mkdir(
                parsed_uri=self._parsed_job_output_uri,
                recursive=True,
                **{
                    output_context: self._workflow_context[output_context]\
                        .get_context_options()
                }
        ):
            msg = 'cannot create job output uri: {}'.format(
                self._parsed_job_output_uri['chopped_uri']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        return True


    def _init_dag(self):
        """
        Initialize NetworkX graph with workflow info from database.

        Args:
            self: class instance.

        Returns:
            Result of DAG initialization (True/False).

        """
        self._dag = WorkflowDAG(
            self._job,
            self._workflow,
            self._apps,
            self._parsed_job_work_uri,
            self._parsed_job_output_uri,
            self._exec_contexts,
            self._data_contexts,
            self._config,
            **{
                context: self._workflow_context[context].get_context_options()\
                for context in self._workflow_context
            }
        )

        try:
            self._dag.initialize()
        except WorkflowDAGException as err:
            msg = 'cannot initialize workflow graph class'
            Log.an().error(msg)
            return self._fatal(str(err)+'|'+msg)

        return True


    def _re_init(self):
        """Reinitialize connection object."""
        return True


    def run(self):
        """
        Run Workflow.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        self._update_status_db('RUNNING', '')

        for node_name in self._dag.get_topological_sort():
            node = self._dag.graph().nodes[node_name]
            if node['type'] == 'input':

                Log.some().debug('[%s]: staging input', node_name)
                if not node['node'].stage(
                        move_final=False,
                        **{
                            context: self._workflow_context[context]\
                                .get_context_options()\
                            for context in self._workflow_context
                        }
                ):
                    msg = 'staging failed for input {}'.format(node_name)
                    Log.an().error(msg)
                    return self._fatal(msg)

            else: # step node

                # Reinit connection to exec context
                if not self._re_init():
                    msg = 'cannot reinit exec context'
                    Log.an().error(msg)
                    return self._fatal(msg)

                Log.some().info(
                    '[%s]: app: %s:%s [%s]',
                    node_name,
                    node['node']._app['name'],
                    node['node']._app['version'],
                    node['node']._app['git']
                )

                Log.some().debug('[%s]: iterating map uri', node_name)
                if not node['node'].iterate_map_uri():
                    msg = 'iterate map uri failed for step {}'.format(node_name)
                    Log.an().error(msg)
                    return self._fatal(msg)

                # run new jobs and poll until all job(s) done
                Log.some().info('[%s]: running', node_name)
                while not node['node'].all_done():
                    if not node['node'].run():
                        msg = 'run failed for step {}'.format(node_name)
                        Log.an().error(msg)
                        return self._fatal(msg)
                    node['node'].check_running_jobs()
                    time.sleep(self._config['run_poll_delay'])

                Log.some().debug('[%s]: all jobs complete', node_name)

                # check if step satisfies checkpoint of all, any, or none job completion
                if not node['node'].checkpoint():
                    msg = 'failed checkpoint for step {}'.format(node_name)
                    Log.an().error(msg)
                    return self._fatal(msg)

                # cleanup jobs
                Log.some().debug('[%s]: cleaning', node_name)
                if not node['node'].clean_up():
                    msg = 'clean up failed for step {}'.format(node_name)
                    Log.an().error(msg)
                    return self._fatal(msg)

                # stage outputs (non-final)
                Log.some().debug('[%s]: staging output', node_name)
                if not node['node'].stage(
                        **{
                            context: self._workflow_context[context]\
                                .get_context_options()\
                            for context in self._workflow_context
                        }
                ):
                    msg = 'staging failed for step {}'.format(node_name)
                    Log.an().error(msg)
                    return self._fatal(msg)


        # stage final outputs
        for node_name in self._dag.get_topological_sort():
            node = self._dag.graph().nodes[node_name]
            if node['type'] == 'step':

                Log.some().debug('[%s]: staging final output', node_name)
                if not node['node'].stage_final(
                        **{
                            context: self._workflow_context[context]\
                                .get_context_options()\
                            for context in self._workflow_context
                        }
                ):
                    msg = 'staging final output failed for step {}'.format(node_name)
                    Log.an().error(msg)
                    return self._fatal(msg)

                Log.some().info('[%s]: complete', node_name)

        self._update_status_db('FINISHED', '')

        return True


    def _send_notifications(self, status):

        # construct message
        msg_data = {
            'to': '',
            'from': 'geneflow@geneflow.biotech.cdc.gov',
            'subject': 'GeneFlow Job "{}": {}'.format(
                self._job['name'], status
            ),
            'content': (
                'Your GeneFlow job status has changed to {}'
                '\nJob Name: {}'
                '\nJob ID: {}'
            ).format(status, self._job['name'], self._job_id)
        }

        # use agave token as header if available
        if 'agave' in self._workflow_context:
            msg_headers = {
                'Authorization':'Bearer {}'.format(
                    self._workflow_context['agave']\
                        .get_context_options()['agave_wrapper']\
                        ._agave.token.token_info.get('access_token')
                )
            }

        else:
            msg_headers = {}

        Log.some().info('message headers: %s', str(msg_headers))

        for notify in self._job['notifications']:
            Log.some().info(
                'sending notification(s) to %s @ %s',
                str(notify['to']),
                notify['url'],
            )

            to_list = notify['to']
            if isinstance(notify['to'], str):
                to_list = [notify['to']]

            for to_item in to_list:
                msg_data['to'] = to_item
                try:
                    response = requests.post(
                        notify['url'], data=msg_data, headers=msg_headers
                    )

                except requests.exceptions.RequestException as err:
                    Log.a().warning(
                        'cannot send notification to %s @ %s: %s',
                        to_item, notify['url'], str(err)
                    )

                if response.status_code != 201:
                    Log.a().warning(
                        'cannot send notification to %s @ %s: %s',
                        to_item, notify['url'], response.text
                    )


    def _update_status_db(self, status, msg):
        """
        Update workflow status in DB.

        Args:
            self: class instance
            status: Workflow status
            msg: Success, error or warning message

        Returns:
            On success: True.
            On failure: False.

        """
        try:
            data_source = DataSource(self._config['database'])
        except DataSourceException as err:
            msg = 'data source initialization error [{}]'.format(str(err))
            Log.an().error(msg)
            return False

        # set start time (if started, or errored immediatedly)
        if (
                status in ['RUNNING', 'ERROR']
                and self._status == 'PENDING'
        ):
            if not data_source.set_job_started(self._job_id):
                Log.a().warning('cannot set job start time in data source')
                data_source.rollback()

        # set finished time (even on error)
        if status in ['FINISHED', 'ERROR']:
            if not data_source.set_job_finished(self._job_id):
                Log.a().warning('cannot set job finish time in data source')
                data_source.rollback()

        # if state change, contact notification endpoint
        if status != self._status:
            if self._job['notifications']:
                self._send_notifications(status)

        # update database
        self._status = status
        if not data_source.update_job_status(self._job_id, status, msg):
            Log.a().warning('cannot update job status in data source')
            data_source.rollback()

        data_source.commit()
        return True


    def get_status_struct(self):
        """
        Get a workflow status dictionary.

        Args:
            self: class instance

        Returns:
            False

        """
        struct = {
            'id': self._job_id[:8],
            'name': self._job['name'],
            'status': self._status,
        }

        return struct


    def get_job(self):
        """
        Get workflow job info.

        Args:
            self: class instance

        Returns:
            workflow job dict

        """
        return self._job


    def get_status(self):
        """
        Get workflow status.

        Args:
            self: class instance

        Returns:
            workflow status string

        """
        return self._status


    def clean_up(self):
        """
        Copy/move workflow data to final output location.

        Args:
            self: class instance

        Returns:
            True

        """
        return True
