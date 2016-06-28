# Check packsible.yml file
# Download the each of the dependencies
# Copy each of the dependencies into a roles directory
# Copy the current directory as if it's a role
# Generate a playbook with the correct roles
import yaml
import click
import os
import shutil
import subprocess
import errno
import json
import copy
import git
from .utils import TemporaryDirectory
from .server import run_server


BASE_ANSIBLE = [dict(
  hosts='all',
  become=True,
  connection='local'
)]


@click.group()
@click.option('--config-dir', type=click.Path(exists=False),
              default=click.get_app_dir('packsible', force_posix=True))
@click.pass_context
def cli(ctx, config_dir):
    config_path = os.path.join(config_dir, 'config.yml')

    # If the config path doesn't exist default to the system config
    system_config_path = '/etc/packsible/config.yml'

    if not os.path.exists(config_path) and os.path.exists(system_config_path):
        config_path = system_config_path

    raw_config = {}
    if os.path.exists(config_path):
        raw_config = yaml.load(open(config_path))

    ctx.obj = PacksibleConfig.setup(raw_config)


@cli.command()
@click.option('--remote/--no-remote', default=False)
@click.option('--base-image')
@click.option('--rebuild-image')
@click.pass_context
def build(ctx, remote, base_image, rebuild_image):
    project_dir = os.path.abspath('.')

    config = ctx.obj

    # Make sure the directory is a git repo for now
    # FIXME in the future we want to allow any directory
    if not os.path.isdir(os.path.join(project_dir, '.git')):
        raise Exception("Cannot continue")

    # Look for a packsible.yml file in the local directory
    packsible_path = os.path.abspath('packsible.yml')

    packsible_def = yaml.load(open(packsible_path)) or {}
    packsible_def.setdefault('base_image', base_image or config.default_base_image_name)
    if rebuild_image:
        packsible_def['rebuild_image'] = rebuild_image

    preparer = BuildPreparer.from_packsible_def(config, project_dir, packsible_def)

    if remote:
        pass
    else:
        # Move prepared file into a temporary directory
        with TemporaryDirectory() as tmp_dir:
            preparer.unpack_prepared_file_to(tmp_dir)


@cli.command()
@click.pass_context
def server(ctx):
    run_server(ctx.obj)


class PacksibleConfig(object):
    @classmethod
    def setup(cls, raw_config):
        config = cls(raw_config)
        config.process_raw_config()
        return config

    def __init__(self, raw_config):
        self._raw_config = raw_config
        self._default_base_image = {
            'image': 'ubuntu'
        }
        self._base_image_map = {}

    @property
    def default_base_image_name(self):
        return self._default_base_image.get('image')

    def get_base_image(self, base_image_name):
        return self._base_image_map.get(base_image_name, {})

    def find_best_base_image(self, dependencies):
        dependencies_set = set(dependencies)
        for base_image_name, base_image in self._base_image_map.iteritems():
            provides_set = set(base_image.get('provides', []))

            provides_set

    def process_raw_config(self):
        for base_image in self._raw_config.get('base_images', []):
            if base_image.get('is_default', False):
                self._default_base_image = base_image
            self._base_image_map[base_image['image']] = base_image

    def get(self, *args, **kwargs):
        return self._raw_config.get(*args, **kwargs)


class BuildPreparer(object):
    @classmethod
    def from_packsible_def(cls, packsible_config, project_dir, packsible_def):
        builder = cls(packsible_config, project_dir, packsible_def)
        builder.prepare()
        return builder

    def __init__(self, packsible_config, project_dir, packsible_def):
        self._packsible_config = packsible_config
        self._project_dir = project_dir
        self._packsible_def = packsible_def

    def prepare(self):
        # Ensure that .packsible file exists in project dir
        packsible_working_dir = self.packsible_working_dir()
        mkdir_p(packsible_working_dir)

        # Create a tarball using the shell
        response = subprocess.call(
            'git ls-files -c -o --exclude-standard | tar -czf %s/build.tar.gz -T -' % packsible_working_dir,
            shell=True,
            cwd=self._project_dir
        )

        if response != 0:
            raise Exception('Could not package directory')

    def packsible_working_dir(self, *joins):
        return os.path.join(self._project_dir, '.packsible', *joins)

    def unpack_prepared_file_to(self, dest_dir):
        source = self.packsible_working_dir('build.tar.gz')
        dest = os.path.join(dest_dir, 'build.tar.gz')
        shutil.copy(source, dest)

        response = subprocess.call('tar xvf %s' % 'build.tar.gz', cwd=dest_dir,
                                   shell=True)

        if response != 0:
            raise Exception('Could not unpack the prepared build')

        mkdir_p(os.path.join(dest_dir, 'roles'))

        base_image_name = self._packsible_def['base_image']

        base_image = self._packsible_config.get_base_image(base_image_name)

        initial_skip_list = base_image.get('provides', [])

        # Download dependencies
        role_paths = self.download_dependencies(
            dest_dir,
            self._packsible_def.get('dependencies', []),
            skip_list=initial_skip_list
        )
        # Add self to the roles in case this has role definitions
        role_paths.append(dest_dir)

        is_a_rebuild = False
        if self._packsible_def.get('rebuild_image'):
            is_a_rebuild = True

        template = dict(
            builders=[
                dict(
                    type="docker",
                    image=self._packsible_def.get('rebuild_image', self._packsible_def['base_image']),
                    export_path="image.tar",
                    pull=False
                )
            ],
            provisioners=[
                {
                    "type": "file",
                    "source": "/home/vagrant/.ssh/id_rsa",
                    "destination": "/tmp/id_rsa",
                },
                {
                    "type": "shell",
                    "inline": [
                        "mkdir -p ~/.ssh",
                        "mv /tmp/id_rsa ~/.ssh/id_rsa",
                        "chmod 700 ~/.ssh/id_rsa",
                        "mkdir -p /app",
                    ]
                },
                {
                    "type": "file",
                    "source": source,
                    "destination": "/app/build.tar.gz",
                },
                {
                    "type": "shell",
                    "inline": [
                        "cd /app; tar xvf /app/build.tar.gz",
                        "rm /app/build.tar.gz",
                    ]
                },
                dict(
                    type="ansible-local",
                    playbook_file="./playbook.yml",
                    role_paths=role_paths,
                    extra_arguments=[
                        '--extra-vars "packsible_rebuild=%s"' % is_a_rebuild
                    ]
                ),
                {
                    "type": "shell",
                    "inline": [
                        "rm ~/.ssh/id_rsa",
                    ]
                },
            ]
        )

        if not self._packsible_def.get('is_app', True):
            # Remove the app directory if this isn't actually meant to be an
            # app. This will happen if it's only meant to be some kind of role.
            template['provisioners'].append({
                'type': 'shell',
                'inline': [
                    'rm -rf /app'
                ]
            })

        json.dump(template, open(os.path.join(dest_dir, 'template.json'), 'w'))

        # generate playbook
        ansible = copy.deepcopy(BASE_ANSIBLE)

        ansible[0]['roles'] = map(os.path.basename, role_paths)

        playbook_file = open(os.path.join(dest_dir, 'playbook.yml'), 'w')
        playbook_file.write(yaml.dump(ansible, default_flow_style=False))
        playbook_file.close()

        response = subprocess.call(
            ['packer', 'build', 'template.json'],
            cwd=dest_dir,
        )

        if response != 0:
            raise Exception("Failed to build image")

        shutil.move(os.path.join(dest_dir, 'image.tar'),
                    self.packsible_working_dir('image.tar'))

    def download_dependencies(self, dest_dir, dependencies, skip_list=None):
        role_paths = []
        skip_list = skip_list or []
        for dependency in dependencies:
            if type(dependency) in [str, unicode]:
                dependency = self.details_for_dependency_from_str(dependency)

            dest_path = os.path.join(dest_dir, 'roles', dependency['name'])
            tag_or_branch = dependency.get('tag', dependency.get('branch'))

            optional_args = dict()
            if tag_or_branch:
                optional_args['branch'] = tag_or_branch

            if dependency['name'] in skip_list:
                continue
            git.Git().clone(dependency['url'], dest_path, depth=1,
                            **optional_args)

            skip_list.append(dependency['name'])

            # Read dependencies recursively
            packsible_path_for_dep = os.path.join(dest_path, 'packsible.yml')
            packsible_def_for_dep = yaml.load(open(packsible_path_for_dep)) or {}
            dependent_role_paths = self.download_dependencies(
                dest_dir,
                packsible_def_for_dep.get('dependencies', []),
                skip_list=skip_list
            )

            for dependent_role_path in dependent_role_paths:
                if dependent_role_path in role_paths:
                    continue
                role_paths.append(dependent_role_path)

            role_paths.append(dest_path)
        return role_paths

    def details_for_dependency_from_str(self, dependency):
        details = dict(
            name=dependency.split('/')[1],
            url='git@github.com:%s.git' % dependency,
        )

        fragment_split = dependency.split('#')
        if len(fragment_split) == 2:
            if fragment_split[1].startswith('tag='):
                details['tag'] = fragment_split[1][4:]
            else:
                details['branch'] = fragment_split[1]
        return details


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


if __name__ == "__main__":
    cli()
