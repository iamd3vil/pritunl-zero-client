import datetime
import re
import sys
import subprocess
import time
import math
import json
import requests
import os
import zlib
import werkzeug.http

CONSTANTS_PATH = 'ssh_client.py'
STABLE_PACUR_PATH = '../pritunl-pacur'
TEST_PACUR_PATH = '../pritunl-pacur-test'
BUILD_KEYS_PATH = 'build_keys.json'
BUILD_TARGETS = ('pritunl-ssh',)
REPO_NAME = 'pritunl-zero-client'
RELEASE_NAME = 'Pritunl Zero Client'

cur_date = datetime.datetime.utcnow()

with open(BUILD_KEYS_PATH, 'r') as build_keys_file:
    build_keys = json.loads(build_keys_file.read().strip())
    github_owner = build_keys['github_owner']
    github_token = build_keys['github_token']
    gitlab_token = build_keys['gitlab_token']
    mirror_url = build_keys['mirror_url']
    test_mirror_url = build_keys['test_mirror_url']

def wget(url, cwd=None, output=None):
    if output:
        args = ['wget', '-O', output, url]
    else:
        args = ['wget', url]
    subprocess.check_call(args, cwd=cwd)

def post_git_asset(release_id, file_name, file_path):
    for i in xrange(5):
        file_size = os.path.getsize(file_path)
        response = requests.post(
            'https://uploads.github.com/repos/%s/%s/releases/%s/assets' % (
                github_owner, REPO_NAME, release_id),
            verify=False,
            headers={
                'Authorization': 'token %s' % github_token,
                'Content-Type': 'application/octet-stream',
                'Content-Size': str(file_size),
            },
            params={
                'name': file_name,
            },
            data=open(file_path, 'rb').read(),
            )

        if response.status_code == 201:
            return
        else:
            time.sleep(1)

    data = response.json()
    errors = data.get('errors')
    if not errors or errors[0].get('code') != 'already_exists':
        print 'Failed to create asset on github'
        print data
        sys.exit(1)

def get_ver(version):
    day_num = (cur_date - datetime.datetime(2015, 11, 24)).days
    min_num = int(math.floor(((cur_date.hour * 60) + cur_date.minute) / 14.4))
    ver = re.findall(r'\d+', version)
    ver_str = '.'.join((ver[0], ver[1], str(day_num), str(min_num)))
    ver_str += ''.join(re.findall('[a-z]+', version))

    return ver_str

def get_int_ver(version):
    ver = re.findall(r'\d+', version)

    if 'snapshot' in version:
        pass
    elif 'alpha' in version:
        ver[-1] = str(int(ver[-1]) + 1000)
    elif 'beta' in version:
        ver[-1] = str(int(ver[-1]) + 2000)
    elif 'rc' in version:
        ver[-1] = str(int(ver[-1]) + 3000)
    else:
        ver[-1] = str(int(ver[-1]) + 4000)

    return int(''.join([x.zfill(4) for x in ver]))

def iter_packages():
    for target in BUILD_TARGETS:
        target_path = os.path.join(pacur_path, target)
        for name in os.listdir(target_path):
            if name.endswith(".pkg.tar.xz"):
                pass
            elif name.endswith(".rpm"):
                pass
            elif name.endswith(".deb"):
                pass
            else:
                continue

            path = os.path.join(target_path, name)

            yield name, path

def generate_last_modifited_etag(file_path):
    file_name = os.path.basename(file_path).encode(sys.getfilesystemencoding())
    file_mtime = datetime.datetime.utcfromtimestamp(
        os.path.getmtime(file_path))
    file_size = int(os.path.getsize(file_path))
    last_modified = werkzeug.http.http_date(file_mtime)

    return (last_modified, 'wzsdm-%d-%s-%s' % (
        time.mktime(file_mtime.timetuple()),
        file_size,
        zlib.adler32(file_name) & 0xffffffff,
    ))

cmd = sys.argv[1]

with open(CONSTANTS_PATH, 'r') as constants_file:
    cur_version = re.findall('= "(.*?)"', constants_file.read())[0]

if cmd == 'version':
    print get_ver(sys.argv[2])

elif cmd == 'set-version':
    new_version = get_ver(sys.argv[2])

    with open(CONSTANTS_PATH, 'r') as constants_file:
        constants_data = constants_file.read()

    with open(CONSTANTS_PATH, 'w') as constants_file:
        constants_file.write(re.sub(
            '(= ".*?")',
            '= "%s"' % new_version,
            constants_data,
            count=1,
        ))


    # Check for duplicate version
    response = requests.get(
        'https://api.github.com/repos/%s/%s/releases' % (
            github_owner, REPO_NAME),
        headers={
            'Authorization': 'token %s' % github_token,
            'Content-type': 'application/json',
        },
    )

    if response.status_code != 200:
        print 'Failed to get repo releases on github'
        print response.json()
        sys.exit(1)

    for release in response.json():
        if release['tag_name'] == new_version:
            print 'Version already exists in github'
            sys.exit(1)


    subprocess.check_call(['git', 'reset', 'HEAD', '.'])
    subprocess.check_call(['git', 'add', CONSTANTS_PATH])
    subprocess.check_call(['git', 'commit', '-S', '-m', 'Create new release'])
    subprocess.check_call(['git', 'push'])


    # Create release
    response = requests.post(
        'https://api.github.com/repos/%s/%s/releases' % (
            github_owner, REPO_NAME),
        headers={
            'Authorization': 'token %s' % github_token,
            'Content-type': 'application/json',
        },
        data=json.dumps({
            'tag_name': new_version,
            'name': '%s v%s' % (RELEASE_NAME, new_version),
            'body': '',
            'prerelease': False,
            'target_commitish': 'master',
        }),
    )

    if response.status_code != 201:
        print 'Failed to create release on github'
        print response.json()
        sys.exit(1)

    subprocess.check_call(['git', 'pull'])
    subprocess.check_call(['git', 'push', '--tags'])
    time.sleep(6)


    # Create gitlab release
    response = requests.post(
        'https://git.pritunl.com/api/v3/projects' + \
        '/%s%%2F%s/repository/tags/%s/release' % (
            github_owner, REPO_NAME, new_version),
        headers={
            'Private-Token': gitlab_token,
            'Content-type': 'application/json',
        },
        data=json.dumps({
            'tag_name': new_version,
            'description': '',
        }),
    )

    if response.status_code != 201:
        print 'Failed to create release on gitlab'
        print response.json()
        sys.exit(1)


elif cmd == 'build' or cmd == 'build-test':
    if cmd == 'build':
        pacur_path = STABLE_PACUR_PATH
    else:
        pacur_path = TEST_PACUR_PATH


    # Get sha256 sum
    archive_name = '%s.tar.gz' % cur_version
    archive_path = os.path.join(os.path.sep, 'tmp', archive_name)
    if os.path.isfile(archive_path):
        os.remove(archive_path)
    wget('https://github.com/%s/%s/archive/%s' % (
        github_owner, REPO_NAME, archive_name),
        output=archive_name,
        cwd=os.path.join(os.path.sep, 'tmp'),
    )
    archive_sha256_sum = subprocess.check_output(
        ['sha256sum', archive_path]).split()[0]
    os.remove(archive_path)


    for target in BUILD_TARGETS:
        pkgbuild_path = os.path.join(pacur_path, target, 'PKGBUILD')

        with open(pkgbuild_path, 'r') as pkgbuild_file:
            pkgbuild_data = re.sub(
                'pkgver="(.*)"',
                'pkgver="%s"' % cur_version,
                pkgbuild_file.read(),
            )
            pkgbuild_data = re.sub(
                '"[a-f0-9]{64}"',
                '"%s"' % archive_sha256_sum,
                pkgbuild_data,
            )

        with open(pkgbuild_path, 'w') as pkgbuild_file:
            pkgbuild_file.write(pkgbuild_data)

    for build_target in BUILD_TARGETS:
        subprocess.check_call(
            ['sudo', 'pacur', 'project', 'build', build_target],
            cwd=pacur_path,
        )

elif cmd == 'upload' or cmd == 'upload-test':
    if cmd == 'upload':
        mirror_urls = mirror_url
        pacur_path = STABLE_PACUR_PATH
    else:
        mirror_urls = test_mirror_url
        pacur_path = TEST_PACUR_PATH


    # Get release id
    release_id = None
    response = requests.get(
        'https://api.github.com/repos/%s/%s/releases' % (
            github_owner, REPO_NAME),
        headers={
            'Authorization': 'token %s' % github_token,
            'Content-type': 'application/json',
        },
    )

    for release in response.json():
        if release['tag_name'] == cur_version:
            release_id = release['id']

    if not release_id:
        print 'Version does not exists in github'
        sys.exit(1)


    subprocess.check_call(
        ['sudo', 'pacur', 'project', 'repo'],
        cwd=pacur_path,
    )

    for mir_url in mirror_urls:
        subprocess.check_call([
            'rsync',
            '--human-readable',
            '--archive',
            '--progress',
            '--delete',
            '--acls',
            'mirror/',
            mir_url,
        ], cwd=pacur_path)


    for name, path in iter_packages():
        post_git_asset(release_id, name, path)