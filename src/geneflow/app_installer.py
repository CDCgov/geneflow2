"""This module contains the GeneFlow App Installer class."""


from pathlib import Path
import pprint
import cerberus
import shutil
from git import Repo
from git.exc import GitError
import os
from slugify import slugify
import stat
import yaml
from slugify import slugify

from geneflow.data_manager import DataManager
from geneflow.definition import Definition
from geneflow.log import Log
from geneflow.shell_wrapper import ShellWrapper
from geneflow.template_compiler import TemplateCompiler
from geneflow.uri_parser import URIParser
from geneflow.extend.agave_wrapper import AgaveWrapper


class AppInstaller:
    """
    GeneFlow AppInstaller class.

    The AppInstaller class is used to download, generate, and install apps
    from a GeneFlow git repo.
    """

    def __init__(
            self,
            path,
            app_info
    ):
        """
        Initialize the GeneFlow AppInstaller class.

        Args:
            self: class instance
            path: local path to the app package
            app_info: app information from workflow definition (name, git repo, version)

        Returns:
            None

        """
        self._path = Path(path)
        self._app_info = app_info

        # app definition, which should be in the root of the app package
        self._app = None


    @classmethod
    def _yaml_to_dict(cls, path):

        # read yaml file
        try:
            with open(path, 'rU') as yaml_file:
                yaml_data = yaml_file.read()
        except IOError as err:
            Log.an().warning('cannot read yaml file: %s [%s]', path, str(err))
            return False

        # convert to dict
        try:
            yaml_dict = yaml.safe_load(yaml_data)
        except yaml.YAMLError as err:
            Log.an().warning('invalid yaml file: %s [%s]', path, str(err))
            return False

        return yaml_dict


    def clone_git_repo(self):
        """
        Clone app from git repo.

        Args:
            self: class instance

        Returns:
            On success: True
            On failure: False

        """
        # remove app folder if it exists
        if self._path.is_dir():
            shutil.rmtree(str(self._path))

        # recreate app folder
        self._path.mkdir()

        # clone app's git repo into target location
        try:
            if self._app_info['version']:
                Repo.clone_from(
                    self._app_info['git'], str(self._path), branch=self._app_info['version'],
                    config='http.sslVerify=false'
                )
            else:
                Repo.clone_from(
                    self._app_info['git'], str(self._path),
                    config='http.sslVerify=false'
                )
        except GitError as err:
            Log.an().error(
                'cannot clone app git repo: %s [%s]',
                self._app_info['git'], str(err)
            )
            return False

        return True


    def load_app(self):
        """
        Load app definition.

        Args:
            self: class instance

        Returns:
            On success: True
            On failure: False

        """
        # read yaml file
        self._app = self._yaml_to_dict(
            str(Path(self._path / 'app.yaml'))
        )

        # empty dict?
        if not self._app:
            Log.an().error(
                'cannot load/parse app.yaml file in app: %s', self._path
            )
            return False

        valid_def = Definition.validate_app(self._app)
        if not valid_def:
            Log.an().error('app validation error')
            return False

        # check formatting of version
        self._app['agave_version'] = slugify(self._app['version'].lower()).replace('-','.')
        if self._app['agave_version'].islower():
            # contains letters, invalid version
            Log.an().error(
                'app config validation error: app version cannot contain letters'
            )
            return False

        return True


    def make(self):
        """
        Generate GeneFlow app files from templates.

        Args:
            self: class instance

        Returns:
            On success: True
            On failure: False

        """
        if not self.make_agave():
            return False
        if not self.make_wrapper():
            return False
        if not self.make_test():
            return False

        return True


    def update_def(self, agave):
        """
        Update GeneFlow app definition by adding the implementation section.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        Log.some().info('updating %s', str(self._path / 'app.yaml'))

        try:
            with open(str(self._path / 'app.yaml'), 'a') as app_yaml:
                app_yaml.write('\n\nimplementation:')
                if agave:
                    app_yaml.write('\n  agave:')
                    app_yaml.write(
                        '\n    agave_app_id: {}-{}-{}{}'.format(
                            agave['apps_prefix'],
                            slugify(self._app['name'], regex_pattern=r'[^-a-z0-9_]+'),
                            self._app['agave_version'],
                            agave['revision']
                        )
                    )
                app_yaml.write('\n  local:')
                app_yaml.write(
                    '\n    script: {}.sh'.format(slugify(self._app['name'], regex_pattern=r'[^-a-z0-9_]+'))
                )
        except IOError as err:
            Log.an().error('cannot update GeneFlow app definition: %s', err)
            return False

        return True


    def make_agave(self):
        """
        Generate the GeneFlow Agave app definition.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        Log.some().info('compiling %s', str(self._path / 'agave-app-def.json.j2'))

        if not TemplateCompiler.compile_template(
                None,
                'agave-app-def.json.j2.j2',
                str(self._path / 'agave-app-def.json.j2'),
                slugify_name=slugify(self._app['name'], regex_pattern=r'[^-a-z0-9_]+'),
                **self._app
        ):
            Log.an().error('cannot compile GeneFlow Agave app definition template')
            return False

        return True


    def make_wrapper(self):
        """
        Generate the GeneFlow app wrapper script.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        # make assets folder, if it doesn't already exist
        asset_path = Path(self._path / 'assets')
        asset_path.mkdir(exist_ok=True)

        script_path = str(asset_path / '{}.sh'.format(slugify(self._app['name'], regex_pattern=r'[^-a-z0-9_]+')))
        Log.some().info('compiling %s', script_path)

        # compile jinja2 template
        if not TemplateCompiler.compile_template(
                None,
                'wrapper-script.sh.j2',
                script_path,
                **self._app
        ):
            Log.an().error('cannot compile GeneFlow app wrapper script')
            return False

        # make script executable by owner
        os.chmod(script_path, stat.S_IRWXU)

        return True


    def make_test(self):
        """
        Generate the GeneFlow app test script.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        # make test folder, if it doesn't already exist
        test_path = Path(self._path / 'test')
        test_path.mkdir(exist_ok=True)

        script_path = str(test_path / 'test.sh')
        Log.some().info('compiling %s', script_path)

        # compile jinja2 template
        if not TemplateCompiler.compile_template(
                None,
                'test.sh.j2',
                script_path,
                **self._app
        ):
            Log.an().error('cannot compile GeneFlow app test script')
            return False

        # make script executable by owner
        os.chmod(script_path, stat.S_IRWXU)

        return True


    def register_agave_app(self, agave_wrapper, agave_params, agave_publish):
        """
        Register app in Agave.

        Args:
            self: class instance

        Returns:
            On success: True.
            On failure: False.

        """
        Log.some().info('registering agave app %s', str(self._path))
        Log.some().info('app version: %s', self._app['version'])

        # compile agave app template
        if not TemplateCompiler.compile_template(
                self._path,
                'agave-app-def.json.j2',
                self._path / 'agave-app-def.json',
                version=self._app['version'],
                agave=agave_params['agave']
        ):
            Log.a().warning(
                'cannot compile agave app "%s" definition from template',
                self._app_info['name']
            )
            return False

        # create main apps URI
        parsed_agave_apps_uri = URIParser.parse(
            'agave://{}/{}'.format(
                agave_params['agave']['deploymentSystem'],
                agave_params['agave']['appsDir']
            )
        )
        Log.some().info(
            'creating main apps uri: %s',
            parsed_agave_apps_uri['chopped_uri']
        )
        if not DataManager.mkdir(
                parsed_uri=parsed_agave_apps_uri,
                recursive=True,
                agave={
                    'agave_wrapper': agave_wrapper
                }
        ):
            Log.a().warning('cannot create main agave apps uri')
            return False

        # delete app uri if it exists
        parsed_app_uri = URIParser.parse(
            'agave://{}/{}/{}-{}'.format(
                agave_params['agave']['deploymentSystem'],
                agave_params['agave']['appsDir'],
                slugify(self._app['name'], regex_pattern=r'[^-a-z0-9_]+'),
                self._app['version']
            )
        )
        Log.some().info(
            'deleting app uri if it exists: %s',
            parsed_app_uri['chopped_uri']
        )
        if not DataManager.delete(
                parsed_uri=parsed_app_uri,
                agave={
                    'agave_wrapper': agave_wrapper
                }
        ):
            # log warning, but ignore.. deleting non-existant uri returns False
            Log.a().warning(
                'cannot delete app uri: %s', parsed_app_uri['chopped_uri']
            )

        # upload app assets
        parsed_assets_uri = URIParser.parse(str(self._path / 'assets'))
        Log.some().info(
            'copying app assets from %s to %s',
            parsed_assets_uri['chopped_uri'],
            parsed_app_uri['chopped_uri']
        )

        if not DataManager.copy(
                parsed_src_uri=parsed_assets_uri,
                parsed_dest_uri=parsed_app_uri,
                local={},
                agave={
                    'agave_wrapper': agave_wrapper
                }
        ):
            Log.a().warning(
                'cannot copy app assets from %s to %s',
                parsed_assets_uri['chopped_uri'],
                parsed_app_uri['chopped_uri']
            )
            return False

        # upload test script
        parsed_test_uri = URIParser.parse(
            '{}/{}'.format(
                parsed_app_uri['chopped_uri'],
                'test'
            )
        )
        Log.some().info(
            'creating test uri: %s', parsed_test_uri['chopped_uri']
        )
        if not DataManager.mkdir(
                parsed_uri=parsed_test_uri,
                recursive=True,
                agave={
                    'agave_wrapper': agave_wrapper
                }
        ):
            Log.a().warning(
                'cannot create test uri: %s', parsed_test_uri['chopped_uri']
            )
            return False

        parsed_local_test_script = URIParser.parse(
            str(self._path / 'test' / 'test.sh')
        )
        parsed_agave_test_script = URIParser.parse(
            '{}/{}'.format(parsed_test_uri['chopped_uri'], 'test.sh')
        )
        Log.some().info(
            'copying test script from %s to %s',
            parsed_local_test_script['chopped_uri'],
            parsed_agave_test_script['chopped_uri']
        )
        if not DataManager.copy(
                parsed_src_uri=parsed_local_test_script,
                parsed_dest_uri=parsed_agave_test_script,
                local={},
                agave={
                    'agave_wrapper': agave_wrapper
                }
        ):
            Log.a().warning(
                'cannot copy test script from %s to %s',
                parsed_local_test_script['chopped_uri'],
                parsed_agave_test_script['chopped_uri']
            )
            return False

        # update existing app, or register new app
        Log.some().info('registering agave app')

        app_definition = self._yaml_to_dict(
            str(self._path / 'agave-app-def.json')
        )
        if not app_definition:
            Log.a().warning(
                'cannot load agave app definition: %s',
                str(self._path / 'agave-app-def.json')
            )
            return False

        app_add_result = agave_wrapper.apps_add_update(app_definition)
        if not app_add_result:
            Log.a().warning(
                'cannot register agave app:\n%s', pprint.pformat(app_definition)
            )
            return False

        register_result = {}

        # publish app
        if agave_publish:
            Log.some().info('publishing agave app')

            app_publish_result = agave_wrapper.apps_publish(app_add_result['id'])
            if not app_publish_result:
                Log.a().warning(
                    'cannot publish agave app: %s', app_add_result['id']
                )
                return False

            # return published id and revision
            register_result = {
                'id': app_publish_result['id'],
                'version': self._app['version'],
                'revision': 'u{}'.format(app_publish_result['revision'])
            }

        else:
            # return un-published id and blank revision
            register_result = {
                'id': app_add_result['id'],
                'version': self._app['version'],
                'revision': ''
            }

        return register_result
