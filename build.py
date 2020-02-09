# coding=utf8

import os, sys
import argparse, subprocess, requests, json
import distutils.dir_util as dirutil
from uritemplate import URITemplate

requests.packages.urllib3.disable_warnings()

args = argparse.ArgumentParser()
args.add_argument('-cc', type=str)
args.add_argument('-cxx', type=str)
args.add_argument('-o', type=str)
args.add_argument('--mms-path', type=str)
args.add_argument('--mysql-path', type=str)
args.add_argument('--hl2sdk-root', type=str)
args = args.parse_args()

script_dir = os.path.dirname(os.path.abspath(__file__))
sourcemod_dir = os.getcwd()
release_uploads = {}

# predefines
OUT = args.o or os.path.realpath(os.path.join(sourcemod_dir, '..', 'OUT'))
SUPPRESS_OUTPUT = '>nul 2>&1' if sys.platform.startswith('win') else '>/dev/null 2>&1'
SAVE_OUTPUT = 'powershell "{0} |& tee build.log"' if sys.platform.startswith('win') else '{0} |& tee build.log'

# functions defines
def _update():
   print('[Update] Attempting to update...')

   os.chdir(script_dir)
   try:
       subprocess.check_call('git fetch -t {0}'.format(SUPPRESS_OUTPUT), shell=True)
       print('[Update] Successfully updated')
   except:
       print('[Update] Failed to update build.py')
   os.chdir(sourcemod_dir)

def _config():
    try:
        with open(os.path.join(script_dir, 'config.json'), 'r') as hFile:
            config = json.load(hFile)
    except IOError as e:
        raise Exception('[Config] Error reading file: config.json')

    if not sm_branch in config:
        raise Exception('[Config] Couldn\'t find branch <{0}> in config.json'.format(sm_branch))

    commit_selected = 0
    for commit_id, commit_config in config[sm_branch].items():
        commit_id = int(commit_id)
        if sm_commit >= commit_id and commit_id > commit_selected:
            commit_selected = commit_id

    if commit_selected == 0:
        raise Exception('[Config] Couldn\'t find config for <{0}#{1}>'.format(sm_branch, sm_commit))

    print('[Config] Selected config for <{1}#{0}> is <{1}#{2}>'.format(sm_commit, sm_branch, commit_selected))
    return  config[sm_branch][str(commit_selected)]

def _patch():
    print('[Patch] Attempting to patching...')

    try:
        subprocess.check_call('git reset --hard', shell=True)
        subprocess.check_call('git submodule update --init --recursive -f', shell=True)
        # subprocess.check_call('git submodule foreach --recursive git reset --hard', shell=True)
        subprocess.check_call('git apply --ignore-space-change --ignore-whitespace {0} {1}'.format(os.path.join(script_dir, 'patches', sm_branch, config['patch']), SUPPRESS_OUTPUT), shell=True)
    except:
        raise Exception('[Patch] Failed to patching')

    print('[Patch] Successfully patched')

def _bootstrap():
    print('[Bootstrap] Attempting to reconfigure...')

    os.chdir('..')

    if sys.platform.startswith('win'):
       command = 'powershell -executionpolicy bypass -nologo -File "{0}"'.format(os.path.join(sourcemod_dir, 'tools', 'checkout-deps.ps1'))
    else:
       command = os.path.join(sourcemod_dir, 'tools', 'checkout-deps.sh')

    try:
        subprocess.check_call(command, shell=True)
    except:
        raise Exception('[Bootstrap] Could not run checkout-deps')

    conf_argv = [
        '--enable-optimize',
        '--no-color',
        '--sdks episode1,ep1',
    ]

    if args.mms_path:
        conf_argv.append('--mms-path {0}'.format(args.mms_path))
    if args.mysql_path:
        conf_argv.append('--mysql-path {0}'.format(args.mysql_path))
    if args.hl2sdk_root:
        conf_argv.append('--hl2sdk-root {0}'.format(args.hl2sdk_root))

    conf_argv = ' '.join(conf_argv)
    command = ('' if sys.platform.startswith('win') else 'CC={0} CXX={1} '.format(args.cc or config['CC'], args.cxx or config['CXX'])) + 'python {0} {1}'.format(os.path.join(sourcemod_dir, 'configure.py'), conf_argv)

    try:
        os.mkdir(OUT)
    except Exception:
        pass
    os.chdir(OUT)

    try:
        subprocess.check_call(command, shell=True)
    except:
        raise Exception('[Bootstrap] Could not configure')

    print('[Bootstrap] Configured')

def _build():
    print('[Build] Start')

    try:
        subprocess.check_call('ambuild --no-color', shell=True)
    except:
        raise Exception('[Build] Failed')

    _strip_debug()

def _strip_debug():
    if sys.platform.startswith('win'):
        return

    print('[Objcopy] Stripping debug...')
    for dirname, subdirs, files in os.walk('package/addons'):
        subdirs.sort()
        files.sort()
        for filen in files:
            if filen[-3:] == '.so':
                subprocess.check_call('objcopy --strip-debug {0}'.format(os.path.join(dirname, filen)), shell=True)
                print(os.path.join(dirname, filen))

def _package():
    import zipfile, tarfile, gzip
    import shutil, re
    from io import StringIO, BytesIO
    from time import localtime, time

    translator = 'https://sm.alliedmods.net/translator/index.php?go=translate&op='
    gamedata_w = (
        'funcommands.games.txt',
        'core.games/blacklist.plugins.txt'
    )

    os.chdir('package')

    print('[Package] Downloading languages.cfg...')
    r = requests.get('{0}export_langs'.format(translator), verify=False)

    try:
        with open('addons/sourcemod/configs/languages.cfg', 'w+') as hFile:
            hFile.write(r.content.decode('utf-8'))
            hFile.seek(0)
            for line in hFile:
                k = re.search(r'"([^"]+)"\s*"[^"]+.*\((\d+)\) ', line)
                if k:
                    print('Downloading language pack {0}.zip...'.format(k.group(1)))
                    r = requests.get('{0}export&lang_id={1}'.format(translator, k.group(2)), verify=False)

                    archive = zipfile.ZipFile(BytesIO(r.content), 'r')
                    archive.extractall('addons/sourcemod/translations/')
                    archive.close()
    except IOError as e:
        raise Exception('[Package] Could not open languages.cfg ({0})'.format(e.strerror))

    needNewGeoIP = True
    geoIPfrom = '../../GeoIP.dat'

    if os.path.isfile(geoIPfrom):
        stats = os.stat(geoIPfrom)
        if stats.st_size != 0:
            fileModifiedTime = stats.st_mtime
            fileModifiedMonth = localtime(fileModifiedTime).tm_mon
            currentMonth = localtime().tm_mon
            thirtyOneDays = 60 * 60 * 24 * 31

            # GeoIP file only updates once per month
            if currentMonth == fileModifiedMonth or (time() - fileModifiedTime) < thirtyOneDays:
                needNewGeoIP = False

    if needNewGeoIP:
        print('[Package] Downloading GeoIP.dat...')
        try:
            r = requests.get('https://sm.alliedmods.net/GeoIP.dat.gz', verify=False)
            archive = gzip.GzipFile(fileobj=BytesIO(r.content), mode='rb')
            with open(geoIPfrom, 'wb') as hFile:
                hFile.write(archive.read())
            archive.close()
        except:
            print('[Package] Failed to download GeoIP.dat!')

    else:
        print('[Package] Reusing existing GeoIP.dat')

    geoIPfile = 'addons/sourcemod/configs/geoip/GeoIP.dat'

    if os.path.isfile(geoIPfile):
        os.remove(geoIPfile)
    shutil.copy(geoIPfrom, geoIPfile)

    gamedata_dir_in = os.path.join(script_dir, 'patches', sm_branch, 'gamedata')
    if os.path.isdir(gamedata_dir_in):
        gamedata_dir_out = os.path.join('addons', 'sourcemod', 'gamedata')

        print('[Package] Copying gamedata...')
        dirutil.remove_tree(gamedata_dir_out)
        dirutil.copy_tree(gamedata_dir_in, gamedata_dir_out, preserve_times=0)

        for filename in gamedata_w:
            try:
                shutil.copy(os.path.join(sourcemod_dir, 'gamedata', filename), os.path.join('addons', 'sourcemod', 'gamedata', filename))
            except:
                pass

    output = 'sourcemod-{0}-git{1}-'.format(sm_version, sm_commit)
    print('Output file IS: {0}'.format(output))

    in_archive = ('addons', 'cfg')
    func = None

    if sys.platform.startswith('linux'):
        output = output + 'linux.tar.gz' 
        print('tar zcvf {0} {1}'.format(output, ' '.join(in_archive)))
        archive = tarfile.open(output, 'w:gz')
        func = archive.add
    elif sys.platform.startswith('win'):
        output = output + 'windows.zip'
        print('zip -r {0} {1}'.format(output, ' '.join(in_archive)))
        archive = zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED)
        func = archive.write
    else:
        output = output + 'mac.zip'
        print('zip -r {0} {1}'.format(output, ' '.join(in_archive)))
        archive = zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED)
        func = archive.write

    try:
        shutil.copy(os.path.join(script_dir, 'metamod.vdf'), 'addons/metamod.vdf')
    except:
        pass

    for f in in_archive:
        for dirname, subdirs, files in os.walk(f):
            subdirs.sort()
            files.sort()

            try:
                func(dirname + os.sep, recursive=False)
            except:
                try:
                    func(dirname + os.sep)
                except:
                    pass

            print(dirname + os.sep)
            for filename in files:
                func(os.path.join(dirname, filename))
                print(os.path.join(dirname, filename))
    archive.close()

    _upload_github(output)
    _upload_bitbucket(output)
    _discord_notify()

    print('{0}{1} -- build succeeded.'.format('File sent to drop site as ' if release_uploads else '', output))

def _upload_github(out_archive):
    variables = ('GITHUB_LOGIN', 'GITHUB_TOKEN', 'GITHUB_API_PATH')
    for var in variables:
        if var not in os.environ:
            print('[Upload:GitHub] Not found required variable <{0}> in environment. SKIP!'.format(var))
            return

    headers = {'Accept': 'application/vnd.github.v3+json'}
    auth = (os.environ['GITHUB_LOGIN'], os.environ['GITHUB_TOKEN'])

    # create release
    print('[Upload:GitHub] Creating a release...')
    response = requests.post('{0}/releases'.format(os.environ['GITHUB_API_PATH']), auth=auth, headers=headers, json={
        'tag_name': 'v{0}.{1}'.format(sm_version, sm_commit),
        'target_commitish': build_commit,
        'name': 'Build v{0}.{1}'.format(sm_version, sm_commit),
        'body': 'Build artifacts',
    })

    try:
        response = response.json()
        if response['errors'][0]['code'] == 'already_exists':
            # get release
            print('[Upload:GitHub] Release already exists. Get a release!')
            response = requests.get('{0}/releases/tags/v{1}.{2}'.format(os.environ['GITHUB_API_PATH'], sm_version, sm_commit), auth=auth, headers=headers).json()
        else:
            print('[Upload:GitHub] FAILED to create a release! ({0})'.format(response['errors'][0]['code']))
            return
    except:
        if 'message' in response:
            print('[Upload:GitHub] FAILED to create a release! ({0} - {1})'.format(response['message'], response['documentation_url']))
            return
        print('[Upload:GitHub] Success created a release.')
        pass

    # check upload_url exists
    try:
        response['upload_url']
    except:
        print('[Upload:GitHub] FAILED to get response[upload_url]!')
        return

    file_from = os.path.join(out_archive)
    file_to = URITemplate(response['upload_url']).expand(name=out_archive)

    # upload release asset
    print('[Upload:GitHub] Trying to upload release asset...')
    try:
        with open(file_from, 'rb') as f:
            response = requests.post(file_to, data=f, auth=auth, headers={'Content-Type': 'application/octet-stream'}).json()
    except:
        print('[Upload:GitHub] FAILED to upload release asset. SKIP!')
        return

    global release_uploads
    release_uploads['GitHub'] = response['browser_download_url']

    print('[Upload:GitHub] Success upload release asset.')


def _upload_bitbucket(out_archive):
    variables = ('BITBUCKET_LOGIN', 'BITBUCKET_TOKEN', 'BITBUCKET_API_PATH')
    for var in variables:
        if var not in os.environ:
            print('[Upload:BitBucket] Not found required variable <{0}> in environment. SKIP!'.format(var))
            return

    headers = {'Accept': 'application/json'}
    auth = (os.environ['BITBUCKET_LOGIN'], os.environ['BITBUCKET_TOKEN'])
    api_path =  URITemplate(os.environ['BITBUCKET_API_PATH']).expand(sm_branch=sm_branch)
    repo_created = True

    request = {'scm': 'git'}
    if 'BITBUCKET_PROJECT' in os.environ:
        request['project'] = {'key': os.environ['BITBUCKET_PROJECT']}


    # create repository if not exists
    response = requests.post(api_path, auth=auth, headers=headers, json=request)
    try:
        response = response.json()
        if response['error']['message'] != 'Repository with this Slug and Owner already exists.':
            repo_created = False
    except:
        repo_created = False

    if not repo_created:
        print('[Upload:Bitbucket] FAILED to create repository (status: {0}). SKIP!'.format(response.status_code))
        return

    file_from = os.path.join(out_archive)

    # upload release asset
    print('[Upload:Bitbucket] Trying to upload release asset...')
    try:
        with open(file_from, 'rb') as f:
            response = requests.post('{0}/downloads'.format(api_path), files={'files': f}, auth=auth)
    except:
        print('[Upload:Bitbucket] FAILED to upload release asset. SKIP!')
        return

    if response.status_code != 201:
        print('[Upload:Bitbucket] FAILED to upload release asset (status: {0}). SKIP!'.format(response.status_code))
        return

    global release_uploads
    release_uploads['Bitbucket'] = '{0}/downloads/{1}'.format(api_path.replace('https://api.bitbucket.org/2.0/repositories/', 'https://bitbucket.org/'), out_archive)

    print('[Upload:Bitbucket] Success upload release asset.')

def _discord_notify():
    if 'DISCORD_WEBHOOK' not in os.environ:
        print('[Discord] Not found required variable <{0}> in environment. SKIP!'.format('DISCORD_WEBHOOK'))
        return

    if not release_uploads:
        print('[Discord] Not found uploaded releases. SKIP!'.format(var))

    from discord_webhook import DiscordWebhook, DiscordEmbed

    if sys.platform.startswith('win'):
        _os = 'Windows'
        _color = 0x0F3674
    elif sys.platform.startswith('linux'):
        _os = 'Linux'
        _color = 0x20BF55
    else:
        _os = 'MacOS'
        _color = 0x31393C

    webhook = DiscordWebhook(url=os.environ['DISCORD_WEBHOOK'])
    embed = DiscordEmbed(title='[{2}] SourceMod Build {0}.{1}'.format(sm_version, sm_commit, _os), description='SourceMod Build {0}.{1} available for download.'.format(sm_version, sm_commit), color=_color)

    for name, value in release_uploads.items():
        embed.add_embed_field(name=name, value=value)

    webhook.add_embed(embed)
    response = webhook.execute()

# get sourcemod version info
try:
    with open('product.version', 'r') as hFile:
        sm_version = hFile.readline().strip()
        sm_version = sm_version.split('-')[0]
        sm_branch = '.'.join(sm_version.split('.')[:2])
except IOError as e:
    raise Exception('[Init] Error reading file: <sourcemod_dir>/product.version')

sm_commit = int(subprocess.check_output('git rev-list --count HEAD', shell=True).strip())
sm_revision = subprocess.check_output('git rev-parse HEAD', shell=True).strip()

os.chdir(script_dir)
try:
    build_commit = subprocess.check_output('git rev-parse HEAD', shell=True).strip()
except:
    build_commit = 'master'
os.chdir(sourcemod_dir)

# get build config
config = _config()
# run!
_update()
_patch()
_bootstrap()
_build()
_package()