"""This module contains the GeneFlow LocalStep class."""


from slugify import slugify
from wcmatch import glob

from geneflow.log import Log
from geneflow.workflow_step import WorkflowStep
from geneflow.data_manager import DataManager
from geneflow.uri_parser import URIParser
from geneflow.shell_wrapper import ShellWrapper


class LocalStep(WorkflowStep):
    """
    A class that represents Local Workflow step objects.

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
            local={}
    ):
        """
        Instantiate LocalStep class by calling the super class constructor.

        See documentation for WorkflowStep __init__().
        """
        super(LocalStep, self).__init__(
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


    def initialize(self):
        """
        Initialize the LocalStep class.

        Validate that the step context is appropriate for this "local" context.
        And that the app contains a "local" definition.

        Args:
            self: class instance.

        Returns:
            On success: True.
            On failure: False.

        """
        # make sure the step context is local
        if self._step['execution']['context'] != 'local':
            msg = (
                '"local" step class can only be instantiated with a'
                ' step definition that has a "local" execution context'
            )
            Log.an().error(msg)
            return self._fatal(msg)

        # make sure app has a local implementation
        if 'local' not in self._app['implementation']:
            msg = (
                '"local" step class can only be instantiated with an app that'
                ' has a "local" implementation'
            )
            Log.an().error(msg)
            return self._fatal(msg)

        if not super(LocalStep, self).initialize():
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

            if self._step['map']['inclusive']:
                # filter with glob
                if glob.globfilter(
                    [uri['name']],
                    self._step['map']['glob'],
                    flags=glob.EXTGLOB|glob.GLOBSTAR
                ):
                    combined_file_list.append({
                        'chopped_uri': '{}://{}{}'.format(
                            uri['scheme'],
                            uri['authority'],
                            uri['folder']
                        ),
                        'filename': uri['name']
                    })

            for f in file_list:
                if '/' in f:
                    # reparse uri to correctly represent recursive elements
                    new_uri = URIParser.parse('{}/{}'.format(uri['chopped_uri'], f))
                    combined_file_list.append({
                        'chopped_uri': '{}://{}{}'.format(
                            new_uri['scheme'],
                            new_uri['authority'],
                            new_uri['folder']
                        ),
                        'filename': new_uri['name']
                    })
                else:
                    combined_file_list.append({
                        'chopped_uri': uri['chopped_uri'],
                        'filename': f
                    })

        return combined_file_list


    def _run_map(self, map_item):
        """
        Run a job for each map item and store the proc and PID.

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

        # construct shell command
        cmd = self._app['implementation']['local']['script']
        for input_key in inputs:
            if inputs[input_key]:
                cmd += ' --{}="{}"'.format(
                    input_key,
                    URIParser.parse(inputs[input_key])['chopped_path']
                )
        for param_key in parameters:
            if param_key == 'output':
                cmd += ' --output="{}/{}"'.format(
                    self._parsed_data_uris[self._source_context][0]\
                        ['chopped_path'],
                    parameters['output']
                )

            else:
                cmd += ' --{}="{}"'.format(
                    param_key, parameters[param_key]
                )

        # add exeuction method
        cmd += ' --exec_method="{}"'.format(self._step['execution']['method'])

        # specify execution init commands if 'init' param given
        if 'init' in self._step['execution']['parameters']:
            cmd += ' --exec_init="{}"'.format(self._step['execution']['parameters']['init'])

        # add stdout and stderr
        log_path = '{}/_log/gf-{}-{}-{}'.format(
            self._parsed_data_uris[self._source_context][0]['chopped_path'],
            map_item['attempt'],
            slugify(self._step['name'], regex_pattern=r'[^-a-z0-9_]+'),
            slugify(map_item['template']['output'], regex_pattern=r'[^-a-z0-9_]+')
        )
        cmd += ' > "{}.out" 2> "{}.err"'.format(log_path, log_path)

        Log.a().debug('command: %s', cmd)

        # launch process
        proc = ShellWrapper.spawn(cmd)
        if proc is False:
            msg = 'shell process error: {}'.format(cmd)
            Log.an().error(msg)
            return self._fatal(msg)

        # record job info
        map_item['run'][map_item['attempt']]['proc'] = proc
        map_item['run'][map_item['attempt']]['pid'] = proc.pid

        # set status of process
        map_item['status'] = 'RUNNING'
        map_item['run'][map_item['attempt']]['status'] = 'RUNNING'

        return True


    def run(self):
        """
        Execute shell scripts for each of the map items, as long as
        number of running jobs is < throttle limit.

        Then store PIDs in run detail.

        Args:
            self: class instance.

        Returns:
            On success: True.
            On failure: False.

        """
        if self._throttle_limit > 0 and self._num_running >= self._throttle_limit:
            # throttle limit reached
            # exit without running anything new
            return True

        for map_item in self._map:
            if map_item['status'] == 'PENDING':
                if not self._run_map(map_item):
                    msg = 'cannot run script for map item "{}"'\
                        .format(map_item['filename'])
                    Log.an().error(msg)
                    map_item['status'] = 'FAILED'
                    map_item['run'][map_item['attempt']]['status']\
                        = map_item['status']

                else:
                    self._num_running += 1
                    if (
                        self._throttle_limit > 0
                        and self._num_running >= self._throttle_limit
                    ):
                        # reached throttle limit
                        break

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
        return {
            map_item['filename']: [
                {
                    'status': run_item.get('status', 'PENDING'),
                    'pid': run_item.get('pid', 0)
                } for run_item in map_item['run']
            ] for map_item in self._map
        }


    def check_running_jobs(self):
        """
        Check the status/progress of all map-reduce items and update _map status.

        Args:
            self: class instance.

        Returns:
            True.

        """
        # check if procs are running, finished, or failed
        for map_item in self._map:
            if map_item['status'] in ['RUNNING','UNKNOWN']:
                try:
                    if not ShellWrapper.is_running(
                            map_item['run'][map_item['attempt']]['proc']
                    ):
                        returncode = map_item['run'][map_item['attempt']]['proc'].returncode
                        if returncode:
                            map_item['status'] = 'FAILED'
                        else:
                            map_item['status'] = 'FINISHED'

                        Log.a().debug(
                            '[step.%s]: exit status: %s -> %s',
                            self._step['name'],
                            map_item['template']['output'],
                            returncode
                        )

                        # decrease num running procs
                        if self._num_running > 0:
                            self._num_running -= 1

                except (OSError, AttributeError) as err:
                    Log.a().warning(
                        'process polling failed for map item "%s" [%s]',
                        map_item['filename'], str(err)
                    )
                    map_item['status'] = 'UNKNOWN'

                map_item['run'][map_item['attempt']]['status']\
                    = map_item['status']

        self._update_status_db(self._status, '')

        return True


    def retry_failed(self):
        """
        Retry any map-reduce jobs that failed.

        This is not-yet supported for local apps.

        Args:
            self: class instance.

        Returns:
            False.

        """
        msg = 'retry not yet supported for local apps'
        Log.an().error(msg)
        return self._fatal(msg)
