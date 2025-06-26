#!/usr/bin/env python

from os import makedirs as os_makedirs, \
               rmdir as os_rmdir, \
               listdir as os_listdir, \
               symlink as os_symlink, \
               rename as os_rename, \
               getpid as os_getpid
from os.path import exists as os_path_exists, \
                    abspath as os_path_abspath, \
                    isdir as os_path_isdir, \
                    islink as os_path_islink
from glob import iglob as glob_iglob
from shutil import rmtree as shutil_rmtree
from requests import get as requests_get
from json import load as json_load, \
                 dump as json_dump
from re import compile as re_compile
from asyncio import run as asyncio_run
from argparse import ArgumentParser as argparse_ArgumentParser
from azure.identity import InteractiveBrowserCredential as azure_identity_InteractiveBrowserCredential
from msgraph import GraphServiceClient as msgraph_GraphServiceClient
from msal import PublicClientApplication as msal_PublicClientApplication


async def get_directory_files(client, drive_id: str, drive_directory_id: str) -> list:
    filename2id = {}

    response = await client.drives.by_drive_id(drive_id).items.by_drive_item_id(drive_directory_id).children.get()
    while response is not None:
        for child_item in response.value:
            if child_item.folder is None:
                filename2id[child_item.name] = child_item.id
        if response.odata_next_link is not None:
            response = await client.drives.by_drive_id(drive_id).items.by_drive_item_id(drive_directory_id).children.with_url(response.odata_next_link).get()
        else:
            response = None
    return filename2id


async def get_directory_tree(client, drive_id: str, drive_directory_id: str, drive_directory_path: str='') -> list:
    dirtree2id = {}

    response = await client.drives.by_drive_id(drive_id).items.by_drive_item_id(drive_directory_id).children.get()
    while response is not None:
        for drive_item_child in response.value:
            if drive_item_child.folder is not None:
                path = f'{drive_directory_path}/{drive_item_child.name}'
                dirtree2id[path] = drive_item_child.id
                dirtree2id.update(await get_directory_tree(client, drive_id, drive_item_child.id, path))
        if response.odata_next_link is not None:
            response = await client.drives.by_drive_id(drive_id).items.by_drive_item_id(drive_directory_id).children.with_url(response.odata_next_link).get()
        else:
            response = None
    return dirtree2id



async def get_drive_files(client, drive_id):
    dirpath2files = {}

    dirtree2id = await get_directory_tree(client, drive_id, 'root')
    for directory_path, directory_id in dirtree2id.items():
        dirpath2files[directory_path] = await get_directory_files(client, drive_id, directory_id)
    return dirpath2files


async def get_file_details(client, user_id, drive_name, filename):
    response = await client.drives.by_drive_id(drive_id).items.by_drive_item_id(drive_item_id).children.with_url(response.odata_next_link).get()


async def download_objects(client, user_id, drive_id, target_directory):
    os_makedirs(f'{target_directory}/objects/', exist_ok=True)
    dirpath2files = await get_drive_files(client, drive_id)
    for directory_path, directory_files in dirpath2files.items():
        print(f"  ...{len(directory_files)} files ({directory_path})")
        for filename_name, filename_id in directory_files.items():
            if os_path_exists(f'{target_directory}/objects/{filename_id}') is False:
                content = await client.drives.by_drive_id(drive_id).items.by_drive_item_id(filename_id).content.get()
                with open(f'{target_directory}/objects/{filename_id}', 'wb') as f:
                    f.write(content)
    return dirpath2files


async def command_get_drives(client, user_id, drive_name, target_directory):
    drive2id = {}
    os_makedirs(target_directory, exist_ok=True)
    print("Downloading list of onedrives...")
    for drive in (await client.users.by_user_id(user_id).drives.get()).value:
        if drive_name is None or drive_name == drive.name:
            drive2id[drive.name] = drive.id
    with open(f'{target_directory}/onedrive-drives.json', 'w') as f:
        json_dump(drive2id, f)


async def command_download_files(client, user_id, drive_name, target_directory):
    os_makedirs(target_directory, exist_ok=True)
    with open(f'{target_directory}/onedrive-drives.json', 'r') as f_drives:
        for drive_name, drive_id in json_load(f_drives).items():
            print(f"Downloading onedrive objects (drive '{drive_name}')...")
            dirpath2files = await download_objects(client, user_id, drive_id, target_directory)
            with open(f'{target_directory}/onedrive-files_{drive_name}.json', 'w') as f_files:
                json_dump(dirpath2files, f_files)
            if os_path_exists(f'{target_directory}/onedrive/{drive_name}-original') is True:
                shutil_rmtree(f'{target_directory}/onedrive/{drive_name}-original')
            for directory_path, directory_files in dirpath2files.items():
                os_makedirs(f'{target_directory}/onedrive/{drive_name}-original/{directory_path}')
                for filename_name, filename_id in directory_files.items():
                    os_symlink(os_path_abspath(f'{target_directory}/objects/{filename_id}'), f'{target_directory}/onedrive/{drive_name}-original/{directory_path}/{filename_name}')


async def command_download_activities(session, user_domain, drive_name, target_directory):
    os_makedirs(target_directory, exist_ok=True)
    with open(f'{target_directory}/onedrive-drives.json', 'r') as f_drives:
        for drive_name, drive_id in json_load(f_drives).items():
            files2activities = {}
            print(f"Downloading onedrive file activities (drive '{drive_name}')...")
            with open(f'{target_directory}/onedrive-files_{drive_name}.json', 'r') as f_files:
                for directory_path, directory_files in json_load(f_files).items():
                    for filename_name, filename_id in directory_files.items():
                        filename_path = f'{directory_path}/{filename_name}'
                        files2activities[filename_path] = []
                        url = f'https://{user_domain}-my.sharepoint.com/_api/v2.0/drives/{drive_id}/items/{filename_id}/activities'
                        activities = requests_get(url, headers={'Authorization': 'Bearer ' + session['access_token']}).json()
                        for activity in activities['value']:
                            if 'action' in activity and 'rename' in activity['action']:
                                files2activities[filename_path].append({'datetime': activity['times']['recordedTime'], 'filename': activity['action']['rename']['oldName']})
                with open(f'{target_directory}/onedrive-activities_{drive_name}.json', 'w') as f_activities:
                    json_dump(files2activities, f_activities)


async def command_deslush(target_directory, slushed_datetime):
    dirpath2files = {}
    files2activities = {}
    slushed2filename = {}
    filename2dirs = {}
    os_makedirs(target_directory, exist_ok=True)
    with open(f'{target_directory}/onedrive-drives.json', 'r') as f_drives:
        for drive_name, drive_id in json_load(f_drives).items():
            print(f"Deslushing onedrive '{drive_name}'...")
            with open(f'{target_directory}/onedrive-files_{drive_name}.json', 'r') as f_files:
                dirpath2files = json_load(f_files)
            with open(f'{target_directory}/onedrive-activities_{drive_name}.json', 'r') as f_activities:
                files2activities = json_load(f_activities)
                for filename_path, activities in files2activities.items():
                    for activity in activities:
                        if activity['datetime'] >= slushed_datetime:
                            slushed2filename[filename_path] = activity['filename']
            if os_path_exists(f'{target_directory}/onedrive/{drive_name}-deslushed') is True:
                shutil_rmtree(f'{target_directory}/onedrive/{drive_name}-deslushed')
            os_makedirs(f'{target_directory}/onedrive/{drive_name}-deslushed')
            for directory_path, directory_files in dirpath2files.items():
                for filename_name, filename_id in directory_files.items():
                    if filename_name not in filename2dirs:
                        filename2dirs[filename_name] = []
                    filename2dirs[filename_name].append(directory_path)
            # create symlinks to objects as per current onedrive state
            for directory_path in dirpath2files.keys():
                os_makedirs(f'{target_directory}/onedrive/{drive_name}-deslushed/{directory_path}', exist_ok=True)
        processed_filenames = []
        for directory_path, directory_files in dirpath2files.items():
            for filename_name, filename_id in directory_files.items():
                filename_path = f'{directory_path}/{filename_name}'
                filename_main, filename_ext = filename_name.rsplit('.', 1)
                if filename_path not in slushed2filename.keys():
                    #print(f"ORIGINAL: symlinking {target_directory}/onedrive/{drive_name}-deslushed/{filename_path}/{filename_id}.{filename_ext}")
                    if os_path_exists(f'{target_directory}/onedrive/{drive_name}-deslushed/{filename_path}') is False:
                        os_makedirs(f'{target_directory}/onedrive/{drive_name}-deslushed/{filename_path}')
                    os_symlink(os_path_abspath(f'{target_directory}/objects/{filename_id}'), f'{target_directory}/onedrive/{drive_name}-deslushed/{filename_path}/{filename_id}.{filename_ext}', target_is_directory=False)
                    processed_filenames.append(filename_path)
                else:
                    original_filename = slushed2filename[filename_path]
                    if original_filename in filename2dirs:
                        original_filename_main, original_filename_ext = original_filename.rsplit('.', 1)
                        for original_directory_path in filename2dirs[original_filename]:
                            #print(f'DESLUSHED: symlinking {target_directory}/onedrive/{drive_name}-deslushed/{original_directory_path}/{original_filename}/{filename_id}.{original_filename_ext}')
                            if os_path_exists(f'{target_directory}/onedrive/{drive_name}-deslushed/{original_directory_path}/{original_filename}') is False:
                                os_makedirs(f'{target_directory}/onedrive/{drive_name}-deslushed/{original_directory_path}/{original_filename}')
                            os_symlink(os_path_abspath(f'{target_directory}/objects/{filename_id}'), f'{target_directory}/onedrive/{drive_name}-deslushed/{original_directory_path}/{original_filename}/{filename_id}.{original_filename_ext}', target_is_directory=False)
                            processed_filenames.append(f'{original_directory_path}/{original_filename}')
        condensed_dir2count = {}
        deslushed_dir2filename = {}
        for path in glob_iglob(f'{target_directory}/onedrive/{drive_name}-deslushed/**', recursive=True):
            onedrive_filename = path.removeprefix(f'{target_directory}/onedrive/{drive_name}-deslushed')
            if onedrive_filename in processed_filenames:
                if os_path_isdir(path) is True:
                    entries = os_listdir(path)
                    entries_symlinks = []
                    for entry in entries:
                        if os_path_islink(f'{path}/{entry}') is True:
                            entries_symlinks.append(entry)
                    if len(entries_symlinks) == 1:
                        if os_path_islink(f'{path}/{entries_symlinks[0]}') is True:
                            deslushed_dir2filename[path] = entries_symlinks[0]
                    elif len(entries_symlinks) > 1:
                        condensed_dir2count[path] = len(entries_symlinks)
        for directory, filename in deslushed_dir2filename.items():
            directory = directory.rstrip('/')
            os_rename(directory, f'{directory}.deslushed_{os_getpid()}')
            os_rename(f'{directory}.deslushed_{os_getpid()}/{filename}', directory)
            os_rmdir(f'{directory}.deslushed_{os_getpid()}')
        result_files_total = sum([len(files) for files in dirpath2files.values()])
        result_files_deslushed = len(deslushed_dir2filename.keys())
        result_files_condensed = len(condensed_dir2count.keys())
        result_files_candidates = sum(condensed_dir2count.values())
        print(f"Analyzed {result_files_total} files")
        print(f"Restored {result_files_deslushed} files and gathered candidates for {result_files_condensed} files (with {result_files_candidates} candidates in total)")


async def main():
    parser = argparse_ArgumentParser(prog='onedrive-deslusher.py')
    parser.add_argument('command')
    parser.add_argument('--user-id',    required=True,    help="M365 user-id (user@domain.onmicrosoft.com)")
    parser.add_argument('--datetime',   default=None,     help="Datetime, after which onedrive file renames should be considered for deslushing (ISO 8601 format: 'yyyy-mm-ddThh:mm:ssZ')")
    parser.add_argument('--drive-name', default=None,     help="OneDrive drive name ('Documents' for english, 'Dokumente' for german, ...")
    parser.add_argument('--directory',  default='./data', help="directory path for storing all data ('./data' or somewhere else)")
    parser.add_argument('--client-id',  default=None,     help="M365 client-id/application-id (format is 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', you must register one in M365)")
    args = parser.parse_args()
    print(f"Using '{args.directory}' for data storage")
    commands = [args.command]
    if args.command == 'run':
        if args.client_id is None or args.datetime is None:
            print(f"Error: --client-id and --datetime are required for command 'run' (which runs all commands in order)")
            return
        commands = ['get-drives', 'download-objects', 'download-activities', 'deslush']
    client = None
    for command in commands:
        if command in ['get-drives', 'download-objects']:
            if client is None and args.client_id is None:
                print(f"Error: --client-id is required for command '{command}'")
                return
            client = msgraph_GraphServiceClient(credentials=azure_identity_InteractiveBrowserCredential(client_id=args.client_id), scopes=['Files.Read.All'])
        match command:
            case 'get-drives':
                await command_get_drives(client, args.user_id, args.drive_name, args.directory)
            case 'download-objects':
                await command_download_files(client, args.user_id, args.drive_name, args.directory)
            case 'download-activities':
                if args.client_id is None:
                    print(f"Error: --client-id is required for command '{command}'")
                    return
                subdomain = re_compile(r'^[A-Za-z0-9_.]+@(?P<subdomain>[A-Za-z0-9-]+)\.onmicrosoft.com$').match(args.user_id).groupdict().get('subdomain')
                app = msal_PublicClientApplication(args.client_id, authority='https://login.microsoftonline.com/organizations')
                session = app.acquire_token_interactive([f'https://{subdomain}-my.sharepoint.com/.default'])
                await command_download_activities(session, subdomain, args.drive_name, args.directory)
            case 'deslush':
                if args.datetime is None:
                    print(f"Error: --datetime is required for command '{command}'")
                    return
                await command_deslush(args.directory, args.datetime)
            case default:
                parser.print_help()

asyncio_run(main())

