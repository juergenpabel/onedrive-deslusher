# tl;dr

M365 OneDrive seems to have (had?) a bug that lead to file corruption. A friend of mine (Wolfgang) was affected and he found [one detailed report from another onedrive user](https://answers.microsoft.com/de-de/msoffice/forum/all/onedrive-dateien-vertauscht/1774c372-9a63-495f-a02f-8745a393b8ab) (in german, but Microsoft will probably gladly auto-translate it for you). Both are using onedrive on MacOS and the effect seems to be exactly the same: files won't open - they appear to just be randomly messed up. This Python script attempts to reconstruct the original file contents (using Microsoft APIs to download everything from M365 servers).

# Context
Now, there are dozens of reports on the web about (different) onedrive issues with some sort of file corruption (especiallly on MacOS) - what sets this one apart is:
- when just going through the directories, everything seems just fine - all expected file(name)s are there
- onedrive server and client(s) were in perfect sync and reported no errors/warnings - not the "usual" onedrive-client is out-of-sync (and got lost, causing local file damage) issue
- upon opening a(lmost any) file, the handling application will complain about file/data corruptions
- Wolfgang had escalated this to Microsoft top-management (in Germany) and even got special assistance from experts in Redmond - but no results

# Analysis
This is where I came in: After Microsoft had analyzed his onedrive instance for a few days, they told him that they had no idea what might have happened or how to recover his files - sorry, Wolfang! So he called me: I took a look at some of those files using a text editor and noticed that they appeared to be just fine - they were just mixed up in terms of file contents and file names: a word file (.docx) would have had the contents of a PDF (.pdf) - or any random combination. Heck, there were even some files that opened just fine - they just had unexpected contents, like a PDF named `something-invoice.pdf` that contained a printer manual (also a PDF). All inspected files contained data that belonged to Wolfgang, so this wasn't a cross-tenant corruption - it's "just" file metadata and file contents that were randomly "shuffled".  

I already had a hunch that this might be due to either a bug in the MacOS onedrive client by itself - or some sort of concurrency issue while using multiple onedrive clients on the server (Wolfgang also uses Windows clients with onedrive for the same onedrive concurrently). My next analysis step was to take a look at some prior versions of those files - but they also all contained the (same) wrong contents. My assumption seemed to be confirmed after I looked into the "details" of some files: they all had been renamed (this information doesn't show up in the version history on onedrive): the `printer-manual.pdf` was renamed to `something-invoice.pdf` and just like that `something.docx` was renamed `something-else.gif` (or whatever). I (manually) confirmed for a few files that the filename listed in the rename operation (from the detail view) did point to the file whose contents belonged to the inspected "source" file - so this whole mess seems to be due to a single "event" (both in terms of root-cause and effects). And indeed: for all (manually) inspected files, the timestamps of the file-rename-events were all within one hour.  

# Concept
Apparently, we had all the needed information to recover ("deslush") his files from onedrive:
- iterate over all files, build a (key/value) map containing the filename and where the (last) rename-operation-record points to (another filename)
- because the filename details (history) list just the pure filename but not the directory (it was almost always from a different directory), a helper map was needed to map out files with the same filename but from different directories
- download all the file contents (onedrive objects) and rebuild the directory tree with all files and their original contents
Now, this doesn't work out perfectly: as in almost any directory tree, there are files with identical filenames (but in different directories). To at least aid with this, my approach is to than create a directory with the name of the currently processed file (like `something-invoice.pdf`) and in that directory to create those files (more precisely: symlinks), that contain the contents of whatever file (whose filename matches) in whatever directory it was from. Of cource, this is done using symlinks - and they point to the corresponding file inside the `objects` directory.  

One you have confirmed that this script did its job accordingly (and maybe even manually cleaned up those files where multiple candidates were listed), it is up to you: **do you want to copy this directory tree back onto onedrive?**

# Implementation: onedrive-deslusher.py

## Application logic
First of: my implementation doesn't write to onedrive servers - it only downloads (all) file contents and reads metadata. No risk of further messing up your onedrive. But it requires downloading all files and thus consumes internet bandwith and local file storage. Make sure you have plenty of both.  

This script downloads all file contents from onedrive and stores them in a dedicated directory using the onedrive object-id as the filename. It than iteraters over all files, extracts the (last) rename-operation record, checks whether this happened after a specified datetime (an when this whole mess happened) in order to not include "regular" file renames from happier days and than creates the corresponding symlinks. That should leave you with a local copy of your onedrive **before** microsoft turned on its data slushing algorithm (okay, okay, I truly believe this is a rare concurrency-related bug - but still, we are talking about software and services that cost quite a bit of money and people and organisations rely on it to work correctly - even on MacOS).

## Setup: M365 application registration
Go to https://admin.microsoft.com and click on **Identity** (left navbar), next expand **Applications** (left navbar) and click on **App-Registrations**. Register a new app (top menu), give it a name (onedrive-deslusher?), next go to the **Redirection-URI** section and select **Public Client** as the type and enter `http://localhost:8400/` as the **Redirection-URI**. Create the app and note the assigned **Application-ID (Client)**, this value needs to be provided to onedrive-deslusher.py (as --client-id).

## Setup: Python environment
```
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Usage
This runs all steps one-after-the-other (browser-interactive M365 confirmation may be required for each step):  
`./onedrive-deslusher.py --client-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx --user-id username@subdomain.onmicrosoft.com --datetime yyyy-mm-ddThh:mm:ssZ run`

This runs all steps individually:
```
./onedrive-deslusher.py --client-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx --user-id username@subdomain.onmicrosoft.com get-drives
./onedrive-deslusher.py --client-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx --user-id username@subdomain.onmicrosoft.com download-objects
./onedrive-deslusher.py --client-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx --user-id username@subdomain.onmicrosoft.com download-activities
./onedrive-deslusher.py --datetime yyyy-mm-ddThh:mm:ssZ deslush
```

Optionally, the following parameters can be used to modify the behaviour:
* `--drive-name <name-of-onedrive-instance>` to select only a specific onedrive instance
* `--directory <path-to-directory>` to use another filesystem directory for storing data (default='./data')

## Results
After completing all steps, you'll find the following sub-directories in the data storage directory (default='./data'):
* `objects`: This is where all files from onedrive(s) are downloaded to, filenames are their onedrive internal object-ids
* `onedrive/<name-of-onedrive-instance>-original`: This should represent your onedrive instance as it currently is ("slushed")
* `onedrive/<name-of-onedrive-instance>-deslushed`: This contains the result of the deslushing.  

Please note that both in the `onedrive/*-original` and the `onedrive/*-deslushed` directories, the directory tree should be as it is in onedrive and contain symlinks (to the object files in `objects`). Everything in `onedrive/*-original` should represent the current state of onedrive. For (symlinked) files in `onedrive/*-deslushed` it will either be the original (correct) filename as the name of the symlink - or, if filename collisions occurred (very likely), there will be a _directory_ with the target _filename_ as its name. Its contents are symlinks to all possible candidate files (those with the same filename, irrespective of their directory path - this is because onedrive only gives the old filename of renamed/moved files, but not their originating directory).
