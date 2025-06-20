# onedrive-deslusher
M365 OneDrive seems to have (had?) a bug that lead to file corruption. A friend of mine was affected and he found one detailed report from another onedrive user. Both are using onedrive on MacOS and the effect seems to be the same: Files won't open - they appear to be just randomly messed up. This script attempts to recover those onedrive contents. 

# Background / Context
Now, there are dozens of reports on the web about onedrive issues with file corruptions - what sets this issue one apart is:
- when just going through the directories, everything seems just fine - all expected file(name)s are there
- upon opening a(lmost any) file, the application will complain about file/data corruptions
- my friend had escalated this to Microsoft top management in Germany and even got special assistance from experts in redmond

This is where I came in: After Microsoft had analyzed his onedrive for a few days, they told him that they had no idea what might have happened or how to recover his files. So he called me: I took a look at some of those files using notepad and hex viewers and noticed that they appeared to be just fine - they were just mixed up in terms of file contents and file names: a word file (.docx) would have had the contents of a PDF (.pdf) - or any random combination. Heck, there were even some files that opened just fine - they just had unexpected contents, like a PDF named something-invoice.pdf contained a printer manual. All inspected files contained contents that belonged to my friend, so this isn't about a cross-tenant corruption - it's "just" file metadata and file contents that were randomly "shuffled". 

I already had a hunch that this might be due to either a bug in the MacOS onedrive client by itself - or some sort of concurrency issue while using multiple onedrive clients (my friend also uses Windows clients with onedrive for the same tenant+drive). My next analysis step was to take a look at some history versions of those files - but they also all contained the wrong contents. My assumption seemed to be confirmed after I looked into the "details" of some files: they all had been renamed (this information doesn't show up in the version history on onedrive): the printer-manual.pdf was renamed to something-invoice.pdf and just like that something.docx was renamed something-else.gif (or whatever). I (manually) confirmed for a few files that the filename listed in the rename operation (from the detail view) did point to the file whose contents belonged to the inspected "source" file. 

# Concept: Deslushing onedrive
Apparently, we had all the needed information to recover ("deslush") his files from onedrive:
- iterate over all files, build a (key/value) map containing the filename and where the (last) rename-operation-record points to (another filename)
- because the filename operation lists just the pure filename but not the directory (it was almost always in a different directory), a helper map was needed to map out files with the same filename but in different directories
- download all the file contents (onedrive objects) and rebuild the directory tree with all files and their original contents
Now, this doesn't work out perfectly: as in almost any file, there are files with identical filenames (but in different directories). To at least aid with this, my approach is to than create a directory with the name of the currently processed file (like something-invoice.pdf) and in that directory to create a list of (numbered) files, each containing the contents of whatever file (whose filename matches) in whatever directory. Of cource, this is done using symlinks.

# Implementation: onedrive-deslusher.py
First of: my implementation doesn't write to onedrive servers - it only downloads (all) file contents and reads metadata. No risk of further messing up your onedrive. But it requires downloading all files and thus consumes internet bandwith and local file storage. Make sure you have plenty of both available.

This script downloads all file contents from onedrive and stores them in a dedicated directory using the onedrive object-id as the filename. It than iteraters over all files, extracts the (last) rename-operation record, checks whether this happened after a specified datetime (an when this whole mess happened) in order to not include "regular" file renames from happier days and than creates the corresponding symlinks. That should leave you with a local copy of your onedrive **before** microsoft turned on its data slushing algorithm (okay, okay, I truly believe this is a rare concurrency-related bug - but still, we are talking about software and services that cost quite a bit of money and people and organisations rely on it to work correctly).

This script has been successfuly used to recover about **XX**% of all files and for all the remaining files, my friend at least has directories containing all the respective candidate files (same filenames) in order to manually finish the deslushing (I bet my whole part in this endeavour was more fun...I feel your pain, Wolfgang).
