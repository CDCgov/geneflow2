"""This module contains the GeneFlow AgaveStep class."""


import pprint
import regex as re
from slugify import slugify
import urllib.parse

from geneflow.log import Log
from geneflow.data_manager import DataManager
from geneflow.workflow_step import WorkflowStep
from geneflow.extend.agave_wrapper import AgaveWrapper


class AgaveStep(WorkflowStep):
    """
    A class that represents Agave Workflow step objects. Inherits from the..

    "WorkflowStep" class.
    """

    def __init__(
            self,
            job,
            step,
            app,
            inputs,
            parameters,
            config,
            depend_uris,
            data_uris,
            source_context,
            clean=False,
            agave={}
    ):
        """
        Instantiate AgaveStep class by calling the super class constructor.

        Takes one parameter in addition to those described in the
        WorkflowStep base class __init__() method.

        Args:
            agave: dict of Agave context data:
                {
                    'agave_wrapper': agave wrapper object,
                    'parsed_archive_uri': archive URI for Agave jobs
                }

        Returns:
            AgaveStep object.

        """
        super(AgaveStep, self).__init__(
            job,
            step,
            app,
            inputs,
            parameters,
            config,
            depend_uris,
            data_uris,
            source_context,
            clean
        )

        # agave context data
        self._agave = agave


    def initialize(self):
        """
        Initialize the AgaveStep class.

        Validate that the step context is appropriate for this "agave" context.
        And that the app contains an "agave" definition.

        Args:
            self: class instance.

        Returns:
            On success: True.
            On failure: False.

        """
        if 'agave_wrapper' not in self._agave:
            msg = 'agave_wrapper object required'
            Log.an().error(msg)
            return self._fatal(msg)

        if 'parsed_archive_uri' not in self._agave:
            msg = 'agave parsed archive uri required'
            Log.an().error(msg)
            return self._fatal(msg)

        # make sure the step context is agave
        if self._step['execution']['context'] != 'agave':
            msg = (
                '"agave" step class can only be instantiated with a'
                ' step definition that has an "agave" execution context'
            )
            Log.an().error(msg)
            return self._fatal(msg)

        # make sure app has an agave implementation
        if 'agave' not in self._app['implementation']:
            msg = (
                '"agave" step class can only be instantiated with an app that'
                ' has an "agave" definition'
            )
            Log.an().error(msg)
            return self._fatal(msg)

        if not super(AgaveStep, self).initialize():
            msg = 'cannot initialize workflow step'
            Log.an().error(msg)
            return self._fatal(msg)

        return True


    def _init_data_uri(self):
        """
        Create output data URI for the source context (agave).

        Args:
            self: class instance.

        Returns:
            On success: True.
            On failure: False.

        """
        # make sure the source data URI has a compatible scheme (agave)
        if self._parsed_data_uris[self._source_context][0]['scheme'] != 'agave':
            msg = 'invalid data uri scheme for this step: {}'.format(
                self._parsed_data_uris[self._source_context][0]['scheme']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        # delete folder if it already exists and clean==True
        if (
                DataManager.exists(
                    parsed_uri=self._parsed_data_uris[self._source_context][0],
                    agave=self._agave
                )
                and self._clean
        ):
            if not DataManager.delete(
                    parsed_uri=self._parsed_data_uris[self._source_context][0],
                    agave=self._agave
            ):
                Log.a().warning(
                    'cannot delete existing data uri: %s',
                    self._parsed_data_uris[self._source_context][0]['chopped_uri']
                )

        # create folder
        if not DataManager.mkdir(
                parsed_uri=self._parsed_data_uris[self._source_context][0],
                recursive=True,
                agave=self._agave
        ):
            msg = 'cannot create data uri: {}'.format(
                self._parsed_data_uris[self._source_context][0]['chopped_uri']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        # create _log folder
        if not DataManager.mkdir(
                uri='{}/_log'.format(
                    self._parsed_data_uris[self._source_context][0]['chopped_uri']
                ),
                recursive=True,
                agave=self._agave
        ):
            msg = 'cannot create _log folder in data uri: {}/_log'.format(
                self._parsed_data_uris[self._source_context][0]['chopped_uri']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        return True


    def _get_map_uri_list(self):
        """
        Get the contents of the map URI (agave URI).

        Args:
            self: class instance.

        Returns:
            Array of base file names in the map URI. Returns False on
            exception.

        """
        combined_file_list = []
        for uri in self._parsed_map_uris:
            # make sure map URI is compatible scheme (agave)
            if uri['scheme'] != 'agave':
                msg = 'invalid map uri scheme for this step: {}'.format(
                    uri['scheme']
                )
                Log.an().error(msg)
                return self._fatal(msg)

            # get file list from URI
            file_list = DataManager.list(
                parsed_uri=uri,
                globstr=self._step['map']['glob'],
                agave=self._agave
            )
            if file_list is False:
                msg = 'cannot get contents of map uri: {}'\
                    .format(uri['chopped_uri'])
                Log.an().error(msg)
                return self._fatal(msg)

            for f in file_list:
                combined_file_list.append({
                    'chopped_uri': uri['chopped_uri'],
                    'filename': f
                })

        return combined_file_list


    def _run_map(self, map_item):
        """
        Run a job for each map item and store the job ID.

        Args:
            self: class instance.
            map_item: map item object (item of self._map).

        Returns:
            On success: True.
            On failure: False.

        """
        # load default app inputs overwrite with template inputs
        inputs = {}
        for input_key in self._app['inputs']:
            if input_key in map_item['template']:
                if map_item['template'][input_key]:
                    # only include an input if the value is a non-empty string
                    inputs[input_key] = urllib.parse.quote(
                        str(map_item['template'][input_key]),
                        safe='/:'
                    )
            else:
                if self._app['inputs'][input_key]['default']:
                    # only include an input if the value is a non-empty string
                    inputs[input_key] = urllib.parse.quote(
                        str(self._app['inputs'][input_key]['default']),
                        safe='/:'
                    )

        # load default app parameters, overwrite with template parameters
        parameters = {}
        for param_key in self._app['parameters']:
            if param_key in map_item['template']:
                parameters[param_key] = map_item['template'][param_key]
            else:
                if self._app['parameters'][param_key]['default'] not in [None, '']:
                    parameters[param_key] \
                        = self._app['parameters'][param_key]['default']

        # add execution method as parameter
        parameters['exec_method'] = self._step['execution']['method']

        # add execution init commands if 'init' param given
        if 'init' in self._step['execution']['parameters']:
            parameters['exec_init'] = self._step['execution']['parameters']['init']

        # construct agave app template
        name = 'gf-{}-{}-{}'.format(
            str(map_item['attempt']),
            slugify(self._step['name'], regex_pattern=r'[^-a-z0-9_]+'),
            slugify(map_item['template']['output'], regex_pattern=r'[^-a-z0-9_]+')
        )
        name = name[:62]+'..' if len(name) > 64 else name
        archive_path = '{}/{}'.format(
            self._agave['parsed_archive_uri']['chopped_path'],
            name
        )
        app_template = {
            'name': name,
            'appId': self._app['implementation']['agave']['agave_app_id'],
            'archive': True,
            'inputs': inputs,
            'parameters': parameters,
            'archiveSystem': self._agave['parsed_archive_uri']['authority'],
            'archivePath': archive_path
        }
        # specify processors if 'slots' param given
        if 'slots' in self._step['execution']['parameters']:
            app_template['processorsPerNode'] = int(
                self._step['execution']['parameters']['slots']
            )
        # specify memory if 'mem' param given
        if 'mem' in self._step['execution']['parameters']:
            app_template['memoryPerNode'] = '{}'.format(
                self._step['execution']['parameters']['mem']
            )

        Log.some().debug(
                "[step.%s]: agave app template:\n%s",
                self._step['name'],
                pprint.pformat(app_template)
        )

        # delete archive path if it exists
        if DataManager.exists(
                uri=self._agave['parsed_archive_uri']['chopped_uri']+'/'+name,
                agave=self._agave
        ):
            if not DataManager.delete(
                    uri=self._agave['parsed_archive_uri']['chopped_uri']+'/'+name,
                    agave=self._agave
            ):
                Log.a().warning(
                    'cannot delete archive uri: %s/%s',
                    self._agave['parsed_archive_uri']['chopped_uri'],
                    name
                )

        # submit job
        job = self._agave['agave_wrapper'].jobs_submit(app_template)
        if not job:
            msg = 'agave jobs submit failed for "{}"'.format(
                app_template['name']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        # log agave job id
        Log.some().debug(
            '[step.%s]: agave job id: %s -> %s',
            self._step['name'],
            map_item['template']['output'],
            job['id']
        )

        # record job info
        map_item['run'][map_item['attempt']]['agave_job_id'] = job['id']
        map_item['run'][map_item['attempt']]['archive_uri'] = '{}/{}'\
            .format(
                self._agave['parsed_archive_uri']['chopped_uri'],
                name
            )
        map_item['run'][map_item['attempt']]['hpc_job_id'] = ''

        # set status of process
        map_item['status'] = 'PENDING'
        map_item['run'][map_item['attempt']]['status'] = 'PENDING'

        return True


    def run(self):
        """
        Execute agave job for each of the map items.

        Store job IDs in run detail.

        Args:
            self: class instance.

        Returns:
            On success: True.
            On failure: False.

        """
        for map_item in self._map:

            if not self._run_map(map_item):
                msg = 'cannot run agave job for map item "{}"'\
                    .format(map_item['filename'])
                Log.an().error(msg)
                return self._fatal(msg)

        self._update_status_db('RUNNING', '')

        return True


    def _serialize_detail(self):
        """
        Serialize map-reduce items. No changes needed for Agave steps.

        Args:
            self: class instance.

        Returns:
            A dict of all map items and their run histories.

        """
        return self._map


    def check_running_jobs(self):
        """
        Check the status/progress of all map-reduce items..

        And update _map status.

        Args:
            self: class instance.

        Returns:
            True.

        """
        # check if jobs are still running
        for map_item in self._map:

            map_item['status'] = self._agave['agave_wrapper'].jobs_get_status(
                map_item['run'][map_item['attempt']]['agave_job_id']
            )

            # for status failures, set to 'UNKNOWN'
            if not map_item['status']:
                msg = 'cannot get job status for step "{}"'\
                    .format(self._step['name'])
                Log.a().warning(msg)
                map_item['status'] = 'UNKNOWN'

            # set status of run-attempt
            map_item['run'][map_item['attempt']]['status'] = map_item['status']

            # check hpc job ids
            if map_item['run'][map_item['attempt']]['hpc_job_id']:
                # already have it
                continue

            # job id listed in history
            response = self._agave['agave_wrapper'].jobs_get_history(
                map_item['run'][map_item['attempt']]['agave_job_id']
            )

            if not response:
                msg = 'cannot get hpc job id for job: agave_job_id={}'.format(
                    map_item['run'][map_item['attempt']]['agave_job_id']
                )
                Log.a().warning(msg)
                continue

            for item in response:
                if item['status'] == 'QUEUED':
                    match = re.match(
                        r'^HPC.*local job (\d*)$', item['description']
                    )
                    if match:
                        map_item['run'][map_item['attempt']]['hpc_job_id'] \
                            = match.group(1)

                        # log hpc job id
                        Log.some().debug(
                            '[step.%s]: hpc job id: %s -> %s',
                            self._step['name'],
                            map_item['template']['output'],
                            match.group(1)
                        )

                        break

            if map_item['status'] == 'FAILED' and map_item['attempt'] < 5:
                # retry job if not at limit
                if not self.retry_failed(map_item):
                    Log.a().warning(
                        '[step.%s]: cannot retry failed agave job (%s)',
                        self._step['name'],
                        map_item['template']['output']
                    )

        self._update_status_db(self._status, '')

        return True


    def retry_failed(self, map_item):
        """
        Retry a job.

        Args:
            self: class instance.

        Returns:
            True if failed/stopped job restarted successfully
            False if failed/stopped job not restarted due to error

        """
        # retry job
        Log.some().info(
            '[step.%s]: retrying agave job (%s), attempt number %s',
            self._step['name'],
            map_item['template']['output'],
            map_item['attempt']+1
        )

        # add another run to list
        map_item['attempt'] += 1
        map_item['run'].append({})
        if not self._run_map(map_item):
            Log.a().warning(
                '[step.%s]: cannot retry agave job (%s), attempt number %s',
                self._step['name'],
                map_item['template']['output'],
                map_item['attempt']
            )
            return False

        return True


    def clean_up(self):
        """
        Copy data from Agave archive location to step output location (data URI).

        Args:
            self: class instance.

        Returns:
            On success: True.
            On failure: False.

        """
        # destination _log directory, common for all map items
        dest_log_dir = '{}/{}'.format(
            self._parsed_data_uris[self._source_context][0]\
                ['chopped_uri'],
            '_log'
        )

        # copy data for each map item
        for map_item in self._map:

            # copy step output
            if not self._agave['agave_wrapper'].files_import_from_agave(
                    self._parsed_data_uris[self._source_context][0]['authority'],
                    self._parsed_data_uris[self._source_context][0]\
                        ['chopped_path'],
                    map_item['template']['output'],
                    '{}/{}'.format(
                        map_item['run'][map_item['attempt']]['archive_uri'],
                        map_item['template']['output']
                    )
            ):
                msg = 'agave import failed for step "{}"'\
                    .format(self._step['name'])
                Log.an().error(msg)
                return self._fatal(msg)

            # check for any agave log files (*.out and *.err files)
            agave_log_list = DataManager.list(
                uri=map_item['run'][map_item['attempt']]['archive_uri'],
                agave=self._agave
            )
            if agave_log_list is False:
                msg = 'cannot get agave log list for step "{}"'\
                    .format(self._step['name'])
                Log.an().error(msg)
                return self._fatal(msg)

            # copy each agave log file, the pattern is gf-{}-{}-{}.out or .err
            for item in agave_log_list:
                if re.match('^gf-\d*-.*\.(out|err)$', item):
                    if not self._agave['agave_wrapper'].files_import_from_agave(
                        self._parsed_data_uris[self._source_context][0]\
                            ['authority'],
                        '{}/{}'.format(
                            self._parsed_data_uris[self._source_context][0]\
                                ['chopped_path'],
                            '_log'
                        ),
                        item,
                        '{}/{}'.format(
                            map_item['run'][map_item['attempt']]\
                                ['archive_uri'],
                            item
                        )
                    ):
                        msg = 'cannot copy agave log item "{}"'.format(item)
                        Log.an().error(msg)
                        return self._fatal(msg)

            # check if anything is in the _log directory
            src_log_dir = '{}/{}'.format(
                map_item['run'][map_item['attempt']]['archive_uri'],
                '_log'
            )

            if DataManager.exists(
                uri=src_log_dir,
                agave=self._agave
            ):
                # create dest _log dir if it doesn't exist
                if not DataManager.exists(
                    uri=dest_log_dir,
                    agave=self._agave
                ):
                    if not DataManager.mkdir(
                        uri=dest_log_dir,
                        agave=self._agave
                    ):
                        msg = 'cannot create _log directory for step "{}"'\
                            .format(self._step['name'])
                        Log.an().error(msg)
                        return self._fatal(msg)

                # get list of all items in src_log_dir
                log_list = DataManager.list(
                    uri=src_log_dir,
                    agave=self._agave
                )
                if log_list is False:
                    msg = 'cannot get _log list for step "{}"'\
                        .format(self._step['name'])
                    Log.an().error(msg)
                    return self._fatal(msg)

                # copy each list item
                for item in log_list:
                    if not self._agave['agave_wrapper'].files_import_from_agave(
                        self._parsed_data_uris[self._source_context][0]\
                            ['authority'],
                        '{}/{}'.format(
                            self._parsed_data_uris[self._source_context][0]\
                                ['chopped_path'],
                            '_log'
                        ),
                        item,
                        '{}/{}/{}'.format(
                            map_item['run'][map_item['attempt']]\
                                ['archive_uri'],
                            '_log',
                            item
                        )
                    ):
                        msg = 'cannot copy log item "{}"'.format(item)
                        Log.an().error(msg)
                        return self._fatal(msg)

        self._update_status_db('FINISHED', '')

        return True
