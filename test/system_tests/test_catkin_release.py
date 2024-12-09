"""
These system tests are testing the release of melodic+ catkin projects.
"""

from __future__ import print_function

import os
import re
import sys

try:
    from vcstools.vcs_abstraction import get_vcs_client
except ImportError:
    print("vcstools was not detected, please install it.", file=sys.stderr)
    sys.exit(1)

from .common import create_release_repo

from ..utils.common import bloom_answer
from ..utils.common import change_directory
from ..utils.common import in_temporary_directory
from ..utils.common import set_up_fake_rosdep
from ..utils.common import user
from ..utils.package_version import change_upstream_version

from bloom.git import branch_exists
from bloom.git import inbranch

from bloom.util import code

from bloom.commands.git.patch import export_cmd
from bloom.commands.git.patch import import_cmd
from bloom.commands.git.patch import remove_cmd

from bloom.generators.debian.generator import sanitize_package_name


def create_upstream_repository(packages, directory=None, format_versions=None):
    upstream_dir = 'upstream_repo_melodic'
    user('mkdir ' + upstream_dir)
    with change_directory(upstream_dir):
        user('git init .')
        user('echo "readme stuff" >> README.md')
        user('git add README.md')
        user('git commit -m "Initial commit" --allow-empty')
        user('git checkout -b melodic_devel')
        if format_versions is None:
            format_versions = [1] * len(packages)
        for package, format_version in zip(packages, format_versions):
            user('mkdir ' + package)
            with change_directory(package if len(packages) != 1 else '.'):
                package_xml = """\
<?xml version="1.0"?>
<package format="{format_version}">
  <name>{package}</name>
  <version>0.1.0</version>
  <description>A catkin (melodic) ROS package called '{package}'</description>
  <maintainer email="bar@baz.com">Bar</maintainer>
  <license{license_file_attr}>BSD</license>

  <url type="bugtracker">https://github.com/ros/this/issues</url>
  <url type="repository">https://github.com/ros/this</url>

  {catkin_depend}

  <!-- required for messages generated by gencpp -->
  <{depend_tag}>roscpp_core</{depend_tag}>
</package>
""".format(package=package,
           format_version=format_version,
           catkin_depend='<buildtool_depend>catkin</buildtool_depend>'
           if format_version > 1 else '<build_depend>catkin</build_depend>\n  <run_depend>catkin</run_depend>',
           depend_tag='depend' if format_version > 1 else 'run_depend',
           license_file_attr=' file="LICENSE"' if format_version > 2 else '')
                with open('package.xml', 'w+') as f:
                    f.write(package_xml)
                user('touch .cproject')
                user('touch .project')
                user('touch white space.txt~')
                user('mkdir -p include/sym')
                user('touch include/{0}.h'.format(package))
                os.symlink('../{0}.h'.format(package), 'include/sym/{0}.h'.format(package))
                user('mkdir debian')
                user('touch debian/something.udev')
                user('echo "{0} license" > LICENSE'.format(package))
                user('git add package.xml .cproject .project include debian "white space.txt~" LICENSE')
        user('git commit -m "Releasing version 0.1.0" --allow-empty')
        user('git tag 0.1.0 -m "Releasing version 0.1.0"')
        return os.getcwd()


def _test_unary_package_repository(release_dir, version, directory=None, env=None):
    print("Testing in {0} at version {1}".format(release_dir, version))
    with change_directory(release_dir):
        # First run everything
        with bloom_answer(bloom_answer.ASSERT_NO_QUESTION):
            cmd = 'git-bloom-release{0} melodic'
            if 'BLOOM_VERBOSE' not in os.environ:
                cmd = cmd.format(' --quiet')
            else:
                cmd = cmd.format('')
            user(cmd, silent=False, env=env)
        ###
        ### Import upstream
        ###
        # does the upstream branch exist?
        assert branch_exists('upstream', local_only=True), "no upstream branch"
        # does the upstrea/<version> tag exist?
        ret, out, err = user('git tag', return_io=True)
        assert out.count('upstream/' + version) == 1, "no upstream tag created"
        # Is the package.xml from upstream in the upstream branch now?
        with inbranch('upstream'):
            assert os.path.exists('package.xml'), \
                "upstream did not import: '" + os.getcwd() + "': " + \
                str(os.listdir(os.getcwd()))
            assert os.path.exists(os.path.join('debian', 'something.udev')), \
                "Lost the debian overlaid files in upstream branch"
            assert os.path.exists('white space.txt~'), \
                "Lost file with whitespace in name in upstream branch"
            with open('package.xml') as f:
                package_xml = f.read()
                assert package_xml.count(version), "not right file"

        ###
        ### Release generator
        ###
        # patch import should have reported OK
        assert ret == code.OK, "actually returned ({0})".format(ret)
        # do the proper branches exist?
        assert branch_exists('release/melodic/foo'), \
            "no release/melodic/foo branch"
        assert branch_exists('patches/release/melodic/foo'), \
            "no patches/release/melodic/foo branch"
        # was the release tag created?
        ret, out, err = user('git tag', return_io=True)
        expected = 'release/melodic/foo/' + version + '-1'
        assert out.count(expected) == 1, \
            "no release tag created, expected: '{0}'".format(expected)

        ###
        ### Make patch
        ###
        with inbranch('release/melodic/foo'):
            assert os.path.exists(os.path.join('debian', 'something.udev')), \
                "Lost the debian overlaid files in release branch"
            assert os.path.exists('white space.txt~'), \
                "Lost file with whitespace in name in release branch"
            assert os.path.islink('include/sym/foo.h'), "Symbolic link lost during pipeline"
            if os.path.exists('include/foo.h'):
                user('git rm include/foo.h')
            else:
                if not os.path.exists('include'):
                    os.makedirs('include')
                user('touch include/foo.h')
                user('git add include/foo.h')
            user('git commit -m "A release patch" --allow-empty')

        ###
        ### Test import and export
        ###
        with inbranch('release/melodic/foo'):
            export_cmd.export_patches()
            remove_cmd.remove_patches()
            import_cmd.import_patches()

        ###
        ### Release generator, again
        ###
        # patch import should have reported OK
        assert ret == code.OK, "actually returned ({0})".format(ret)
        # do the proper branches exist?
        assert branch_exists('release/melodic/foo'), \
            "no release/melodic/foo branch"
        assert branch_exists('patches/release/melodic/foo'), \
            "no patches/release/melodic/foo branch"
        # was the release tag created?
        ret, out, err = user('git tag', return_io=True)
        assert out.count('release/melodic/foo/' + version) == 1, \
            "no release tag created"


@in_temporary_directory
def test_unary_package_repository(directory=None):
    """
    Release a single package catkin (melodic) repository.
    """
    directory = directory if directory is not None else os.getcwd()
    # Initialize rosdep
    rosdep_dir = os.path.join(directory, 'foo_rosdep')
    env = dict(os.environ)
    fake_distros = {'melodic': {'ubuntu': ['bionic']}}
    fake_rosdeps = {
        'catkin': {'ubuntu': []},
        'roscpp_core': {'ubuntu': []}
    }
    env.update(set_up_fake_rosdep(rosdep_dir, fake_distros, fake_rosdeps))
    # Setup
    upstream_dir = create_upstream_repository(['foo'], directory)
    upstream_url = 'file://' + upstream_dir
    release_url = create_release_repo(
        upstream_url,
        'git',
        'melodic_devel',
        'melodic')
    release_dir = os.path.join(directory, 'foo_release_clone')
    release_client = get_vcs_client('git', release_dir)
    assert release_client.checkout(release_url)
    versions = ['0.1.0', '0.1.1', '0.2.0']
    import bloom.commands.git.release
    for index in range(len(versions)):
        _test_unary_package_repository(release_dir, versions[index], directory, env=env)
        bloom.commands.git.release.upstream_repos = {}
        if index != len(versions) - 1:
            change_upstream_version(upstream_dir, versions[index + 1])


@in_temporary_directory
def test_multi_package_repository(directory=None):
    """
    Release a multi package catkin (melodic) repository.
    """
    directory = directory if directory is not None else os.getcwd()
    # Initialize rosdep
    rosdep_dir = os.path.join(directory, 'foo_rosdep')
    env = dict(os.environ)
    fake_distros = {
        'melodic': {
            'debian': ['stretch'],
            'ubuntu': ['bionic']
        }
    }
    fake_rosdeps = {
        'catkin': {'debian': [], 'ubuntu': []},
        'roscpp_core': {'debian': [], 'ubuntu': []}
    }
    env.update(set_up_fake_rosdep(rosdep_dir, fake_distros, fake_rosdeps))
    # Setup
    pkgs = ['foo', 'bar_ros', 'baz']
    upstream_dir = create_upstream_repository(pkgs, directory, format_versions=[1, 2, 3])
    upstream_url = 'file://' + upstream_dir
    release_url = create_release_repo(
        upstream_url,
        'git',
        'melodic_devel',
        'melodic')
    release_dir = os.path.join(directory, 'foo_release_clone')
    release_client = get_vcs_client('git', release_dir)
    assert release_client.checkout(release_url)
    with change_directory(release_dir):
        # First run everything
        with bloom_answer(bloom_answer.ASSERT_NO_QUESTION):
            cmd = 'git-bloom-release{0} melodic'
            if 'BLOOM_VERBOSE' not in os.environ:
                cmd = cmd.format(' --quiet')
            else:
                cmd = cmd.format('')
            user(cmd, silent=False, env=env)
        ###
        ### Import upstream
        ###
        # does the upstream branch exist?
        assert branch_exists('upstream', local_only=True), "no upstream branch"
        # does the upstrea/0.1.0 tag exist?
        ret, out, err = user('git tag', return_io=True)
        assert out.count('upstream/0.1.0') == 1, "no upstream tag created"
        # Is the package.xml from upstream in the upstream branch now?
        with inbranch('upstream'):
            for pkg in pkgs:
                with change_directory(pkg):
                    assert os.path.exists(
                        os.path.join('debian', 'something.udev')), \
                        "Lost the debian overlaid files in upstream branch"
                    assert os.path.exists('white space.txt~'), \
                        "Lost file with whitespace in name in upstream branch"
                    assert os.path.exists('package.xml'), \
                        "upstream did not import: " + os.listdir()
                    with open('package.xml') as f:
                        assert f.read().count('0.1.0'), "not right file"

        ###
        ### Release generator
        ###
        # Check the environment after the release generator
        ret, out, err = user('git tag', return_io=True)
        for pkg in pkgs:
            # Does the release/pkg branch exist?
            assert branch_exists('release/melodic/' + pkg), \
                "no release/melodic/" + pkg + " branch"
            # Does the patches/release/pkg branch exist?
            assert branch_exists('patches/release/melodic/' + pkg), \
                "no patches/release/melodic/" + pkg + " branch"
            # Did the release tag get created?
            assert out.count('release/melodic/' + pkg + '/0.1.0-1') == 1, \
                "no release tag created for " + pkg
            # Is there a package.xml in the top level?
            with inbranch('release/melodic/' + pkg):
                assert os.path.exists('package.xml'), "release branch invalid"
                # Is it the correct package.xml for this pkg?
                package_xml = open('package.xml', 'r').read()
                assert package_xml.count('<name>' + pkg + '</name>'), \
                    "incorrect package.xml for " + str(pkg)

        # Make a patch
        with inbranch('release/melodic/' + pkgs[0]):
            user('echo "This is a change" >> README.md')
            user('git add README.md')
            user('git commit -m "added a readme" --allow-empty')

        ###
        ### Release generator, again
        ###
        with bloom_answer(bloom_answer.ASSERT_NO_QUESTION):
            ret = user('git-bloom-generate -y rosrelease melodic -s upstream', env=env)
        # patch import should have reported OK
        assert ret == code.OK, "actually returned ({0})".format(ret)
        # Check the environment after the release generator
        ret, out, err = user('git tag', return_io=True)
        for pkg in pkgs:
            # Does the release/pkg branch exist?
            assert branch_exists('release/melodic/' + pkg), \
                "no release/melodic/" + pkg + " branch"
            # Does the patches/release/pkg branch exist?
            assert branch_exists('patches/release/melodic/' + pkg), \
                "no patches/release/melodic/" + pkg + " branch"
            # Did the release tag get created?
            assert out.count('release/melodic/' + pkg + '/0.1.0-1') == 1, \
                "no release tag created for " + pkg
            # Is there a package.xml in the top level?
            with inbranch('release/melodic/' + pkg):
                assert os.path.exists(os.path.join('debian', 'something.udev')), \
                    "Lost the debian overlaid files in release branch"
                assert os.path.exists('white space.txt~'), \
                    "Lost file with whitespace in name in release branch"
                assert os.path.exists('package.xml'), "release branch invalid"
                # Is it the correct package.xml for this pkg?
                with open('package.xml', 'r') as f:
                    assert f.read().count('<name>' + pkg + '</name>'), \
                        "incorrect package.xml for " + str(pkg)

        ###
        ### ROSDebian Generator
        ###
        # Check the environment after the release generator
        ret, out, err = user('git tag', return_io=True)
        for pkg in pkgs:
            for distro in ['bionic', 'stretch']:
                pkg_san = sanitize_package_name(pkg)
                # Does the debian/distro/pkg branch exist?
                assert branch_exists('debian/melodic/' + distro + '/' + pkg), \
                    "no debian/melodic/" + pkg + " branch"
                # Does the patches/debian/distro/pkg branch exist?
                patches_branch = 'patches/debian/melodic/' + distro + '/' + pkg
                assert branch_exists(patches_branch), \
                    "no " + patches_branch + " branch"
                # Did the debian tag get created?
                tag = 'debian/ros-melodic-' + pkg_san + '_0.1.0-1_' + distro
                assert out.count(tag) == 1, \
                    "no '" + tag + "'' tag created for '" + pkg + "': `\n" + \
                    out + "\n`"
            # Is there a package.xml in the top level?
            with inbranch('debian/melodic/' + distro + '/' + pkg):
                assert os.path.exists(
                    os.path.join('debian', 'something.udev')), \
                    "Lost the debian overlaid files in debian branch"
                assert os.path.exists('white space.txt~'), \
                    "Lost file with whitespace in name in debian branch"
                assert os.path.exists('package.xml'), "debian branch invalid"
                # Is there blank lins due to no Conflicts/Replaces?
                # See: https://github.com/ros-infrastructure/bloom/pull/329
                with open(os.path.join('debian', 'control'), 'r') as f:
                    assert f.read().count('\n\nHomepage:') == 0, \
                        "Extra blank line before Homepage detected."
                # Is it the correct package.xml for this pkg?
                with open('package.xml', 'r') as f:
                    package_xml = f.read()
                    assert package_xml.count('<name>' + pkg + '</name>'), \
                        "incorrect package.xml for " + str(pkg)
                    format_version = int(re.search(r'format="(\d+)"',
                                                   package_xml).group(1))
                # Is there a copyright file for this pkg?
                with open('debian/copyright', 'r') as f:
                    assert (format_version <= 2) ^ (pkg + ' license' in f.read()), \
                        "debian/copyright does not include right license text"

@in_temporary_directory
def test_upstream_tag_special_tag(directory=None):
    """
    Release a single package catkin (melodic) repository, first put
    an upstream tag into the release repository to test that bloom
    can handle it.
    """
    directory = directory if directory is not None else os.getcwd()
    # Initialize rosdep
    rosdep_dir = os.path.join(directory, 'foo_rosdep')
    env = dict(os.environ)
    fake_distros = {'melodic': {'ubuntu': ['bionic']}}
    fake_rosdeps = {
        'catkin': {'ubuntu': []},
        'roscpp_core': {'ubuntu': []}
    }
    env.update(set_up_fake_rosdep(rosdep_dir, fake_distros, fake_rosdeps))
    # Setup
    upstream_dir = create_upstream_repository(['foo'], directory)
    upstream_url = 'file://' + upstream_dir
    release_url = create_release_repo(
        upstream_url,
        'git',
        'melodic_devel',
        'melodic')
    release_dir = os.path.join(directory, 'foo_release_clone')
    release_client = get_vcs_client('git', release_dir)
    assert release_client.checkout(release_url)

    with change_directory(release_dir):
        user('git tag upstream/0.0.0@baz')

    import bloom.commands.git.release
    _test_unary_package_repository(release_dir, '0.1.0', directory, env=env)