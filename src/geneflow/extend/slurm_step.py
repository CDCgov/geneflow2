"""This module contains the GeneFlow SlurmStep class."""


import drmaa
import os
from slugify import slugify
import shutil

from geneflow.log import Log
from geneflow.workflow_step import WorkflowStep
from geneflow.data_manager import DataManager
from geneflow.uri_parser import URIParser


class SlurmStep(WorkflowStep):
    """
    A class that represents SLURM Workflow Step objects.

    Inherits from the "WorkflowStep" class.
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
            slurm={}
    ):
        """
        Instantiate SlurmStep class by calling the super class constructor.

        See documentation for WorkflowStep __init__().
        """
        super(SlurmStep, self).__init__(
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

        # slurm context data
        self._slurm = slurm

        self._job_status_map = {
            drmaa.JobState.UNDETERMINED: 'UNKNOWN',
            drmaa.JobState.QUEUED_ACTIVE: 'PENDING',
            drmaa.JobState.SYSTEM_ON_HOLD: 'PENDING',
            drmaa.JobState.USER_ON_HOLD: 'PENDING',
            drmaa.JobState.USER_SYSTEM_ON_HOLD: 'PENDING',
            drmaa.JobState.RUNNING: 'RUNNING',
            drmaa.JobState.SYSTEM_SUSPENDED: 'RUNNING',
            drmaa.JobState.USER_SUSPENDED: 'RUNNING',
            drmaa.JobState.DONE: 'FINISHED',
            drmaa.JobState.FAILED: 'FAILED'
        }


    def initialize(self):
        """
        Initialize the SlurmStep class.

        Validate that the step context is appropriate for this "slurm" context.
        And that the app contains a "slurm" definition.

        Args:
            self: class instance.

        Returns:
            On success: True.
            On failure: False.

        """
        # make sure the step context is local
        if self._step['execution']['context'] != 'slurm':
            msg = (
                '"slurm" step class can only be instantiated with a'
                ' step definition that has a "slurm" execution context'
            )
            Log.an().error(msg)
            return self._fatal(msg)

        # make sure app has a local implementation
        #   local def can be used by slurm because it just needs a shell script
        if 'local' not in self._app['implementation']:
            msg = (
                '"slurm" step class can only be instantiated with an app that'
                ' has a "local" implementation'
            )
            Log.an().error(msg)
            return self._fatal(msg)

        if not super(SlurmStep, self).initialize():
            msg = 'cannot initialize workflow step'
            Log.an().error(msg)
            return self._fatal(msg)

        return True


    def _init_data_uri(self):
        """
        Create output data URI for the source context (local).

        Args:
            self: class instance.

        Returns:
            On success: True.
            On failure: False.

        """
        # make sure the source data URI has a compatible scheme (local)
        if self._parsed_data_uris[self._source_context][0]['scheme'] != 'local':
            msg = 'invalid data uri scheme for this step: {}'.format(
                self._parsed_data_uris[self._source_context][0]['scheme']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        # delete old folder if it exists and clean==True
        if (
                DataManager.exists(
                    parsed_uri=self._parsed_data_uris[self._source_context][0]
                )
                and self._clean
        ):
            if not DataManager.delete(
                    parsed_uri=self._parsed_data_uris[self._source_context][0]
            ):
                Log.a().warning(
                    'cannot delete existing data uri: %s',
                    self._parsed_data_uris[self._source_context][0]['chopped_uri']
                )

        # create folder
        if not DataManager.mkdir(
                parsed_uri=self._parsed_data_uris[self._source_context][0],
                recursive=True
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
                recursive=True
        ):
            msg = 'cannot create _log folder in data uri: {}/_log'.format(
                self._parsed_data_uris[self._source_context][0]['chopped_uri']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        return True


    def _get_map_uri_list(self):
        """
        Get the contents of the map URI (local URI).

        Args:
            self: class instance.

        Returns:
            Array of base file names in the map URI. Returns False on
            exception.

        """
        combined_file_list = []
        for uri in self._parsed_map_uris:
            # make sure map URI is compatible scheme (local)
            if uri['scheme'] != 'local':
                msg = 'invalid map uri scheme for this step: {}'.format(
                    uri['scheme']
                )
                Log.an().error(msg)
                return self._fatal(msg)

            # get file list from URI
            file_list = DataManager.list(
                parsed_uri=uri,
                globstr=self._step['map']['glob']
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
        # load default app inputs, overwrite with template inputs
        inputs = {}
        for input_key in self._app['inputs']:
            if input_key in map_item['template']:
                inputs[input_key] = map_item['template'][input_key]
            else:
                if self._app['inputs'][input_key]['default']:
                    inputs[input_key] = self._app['inputs'][input_key]['default']

        # load default app parameters, overwrite with template parameters
        parameters = {}
        for param_key in self._app['parameters']:
            if param_key in map_item['template']:
                parameters[param_key] = map_item['template'][param_key]
            else:
                if self._app['parameters'][param_key]['default'] not in [None, '']:
                    parameters[param_key] \
                        = self._app['parameters'][param_key]['default']

        # get full path of wrapper script
        path = shutil.which(self._app['implementation']['local']['script'])
        if not path:
            msg = 'wrapper script not found in path: %s'.format(
                self._app['implementation']['local']['script']
            )
            Log.an().error(msg)
            return self._fatal(msg)

        # construct argument list for wrapper script
        args = [path]
        for input_key in inputs:
            if inputs[input_key]:
                args.append('--{}={}'.format(
                    input_key,
                    URIParser.parse(inputs[input_key])['chopped_path']
                ))
        for param_key in parameters:
            if param_key == 'output':
                args.append('--output={}/{}'.format(
                    self._parsed_data_uris[self._source_context][0]\
                        ['chopped_path'],
                    parameters['output']
                ))

            else:
                args.append('--{}={}'.format(
                    param_key, parameters[param_key]
                ))

        # add exeuction method
        args.append('--exec_method={}'.format(self._step['execution']['method']))

        # specify execution init commands if 'init' param given
        if 'init' in self._step['execution']['parameters']:
            args.append('--exec_init={}'.format(self._step['execution']['parameters']['init']))

        Log.a().debug(
            '[step.%s]: command: %s -> %s',
            self._step['name'],
            map_item['template']['output'],
            ' '.join(args)
        )

        # construct job name
        name = 'gf-{}-{}-{}'.format(
            map_item['attempt'],
            slugify(self._step['name'], regex_pattern=r'[^-a-z0-9_]+'),
            slugify(map_item['template']['output'], regex_pattern=r'[^-a-z0-9_]+')
        )

        # construct paths for logging stdout and stderr
        log_path = '{}/_log/{}'.format(
            self._parsed_data_uris[self._source_context][0]['chopped_path'],
            name
        )

        # create and populate job template
        jt = self._slurm['drmaa_session'].createJobTemplate()
        jt.remoteCommand = '/bin/bash'
        jt.args = args
        jt.jobName = name
        jt.errorPath = ':{}.err'.format(log_path)
        jt.outputPath = ':{}.out'.format(log_path)

        # pass execution parameters to job template
        native_spec = ' --nodes=1 --ntasks=1'
        if 'queue' in self._step['execution']['parameters']:
            native_spec += ' -p {}'.format(
                self._step['execution']['parameters']['queue']
            )
        if 'slots' in self._step['execution']['parameters']:
            native_spec += ' --cpus-per-task={}'.format(
                self._step['execution']['parameters']['slots']
            )
        if 'other' in self._step['execution']['parameters']:
            native_spec += ' {}'.format(
                self._step['execution']['parameters']['other']
            )
        jt.nativeSpecification = native_spec

        # submit hpc job using drmaa library
        try:
            job_id = self._slurm['drmaa_session'].runJob(jt)

        except drmaa.DrmCommunicationException as err:
            msg = 'cannot submit slurm job for step "{}" [{}]'\
                    .format(self._step['name'], str(err))
            Log.a().warning(msg)

            # set to failed, but return True so that it's retried
            map_item['status'] = 'FAILED'
            map_item['run'][map_item['attempt']]['status'] = 'FAILED'

            return True

        self._slurm['drmaa_session'].deleteJobTemplate(jt)

        Log.a().debug(
            '[step.%s]: hpc job id: %s -> %s',
            self._step['name'],
            map_item['template']['output'],
            job_id
        )

        # record job info
        map_item['run'][map_item['attempt']]['hpc_job_id'] = job_id

        # set status of process
        map_item['status'] = 'PENDING'
        map_item['run'][map_item['attempt']]['status'] = 'PENDING'

        return True


    def run(self):
        """
        Execute shell scripts for each of the map items.

        Then store PIDs in run detail.

        Args:
            self: class instance.

        Returns:
            On success: True.
            On failure: False.

        """
        for map_item in self._map:

            if not self._run_map(map_item):
                msg = 'cannot run script for map item "{}"'\
                    .format(map_item['filename'])
                Log.an().error(msg)
                return self._fatal(msg)

        self._update_status_db('RUNNING', '')

        return True


    def _serialize_detail(self):
        """
        Serialize map-reduce items.

        But leave out non-serializable Popen proc item, keep pid.

        Args:
            self: class instance.

        Returns:
            A dict of all map items and their run histories.

        """
        return self._map


    def check_running_jobs(self):
        """
        Check the status/progress of all map-reduce items and update _map status.

        Args:
            self: class instance.

        Returns:
            True.

        """
        # check if jobs are running, finished, or failed
        for map_item in self._map:
            if map_item['status'] != 'FINISHED' and map_item['status'] != 'FAILED':

                try:
                    # can only get job status if it has not already been disposed with "wait"
                    status = self._slurm['drmaa_session'].jobStatus(
                        map_item['run'][map_item['attempt']]['hpc_job_id']
                    )
                    map_item['status'] = self._job_status_map[status]

                except drmaa.DrmCommunicationException as err:
                    msg = 'cannot get job status for step "{}" [{}]'\
                            .format(self._step['name'], str(err))
                    Log.a().warning(msg)
                    map_item['status'] = 'UNKNOWN'

                if map_item['status'] == 'FINISHED' or map_item['status'] == 'FAILED':
                    # check exit status
                    job_info = self._slurm['drmaa_session'].wait(
                        map_item['run'][map_item['attempt']]['hpc_job_id'],
                        self._slurm['drmaa_session'].TIMEOUT_NO_WAIT
                    )
                    Log.a().debug(
                        '[step.%s]: exit status: %s -> %s',
                        self._step['name'],
                        map_item['template']['output'],
                        job_info.exitStatus
                    )
                    if job_info.exitStatus > 0:
                        # job actually failed
                        map_item['status'] = 'FAILED'

            map_item['run'][map_item['attempt']]['status'] = map_item['status']

            if map_item['status'] == 'FAILED' and map_item['attempt'] < 5:
                # retry job if not at limit
                if not self.retry_failed(map_item):
                    Log.a().warning(
                        '[step.%s]: cannot retry failed slurm job (%s)',
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
            '[step.%s]: retrying slurm job (%s), attempt number %s',
            self._step['name'],
            map_item['template']['output'],
            map_item['attempt']+1
        )

        # add another run to list
        map_item['attempt'] += 1
        map_item['run'].append({})
        if not self._run_map(map_item):
            Log.a().warning(
                '[step.%s]: cannot retry slurm job (%s), attempt number %s',
                self._step['name'],
                map_item['template']['output'],
                map_item['attempt']
            )
            return False

        return True
