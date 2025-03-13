__version__ = "4.0.0.3"

"""
Changelog for version 4.0.0.3 (2025-03-13):

- added platform to docker building
- fixed anime titling
- fixed aither dvdrip naming

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.0.2...4.0.0.3

## Version 4 release notes:
## Breaking change
* When using trackers argument,  or , you must now use a comma separated list.

## Linking support in qBitTorrent
### This is not fully tested. 
It seems to be working fine on this windows box, but you absolutely should test with the  argument to make sure it works on your system before putting it into production.
* You can specify to use symbolic or hard links
* 
* Add one or many (local) paths which you want to contain the links, and UA will map the correct drive/volume for hardlinks.

## Reminder
* UA has mkbrr support 
* You can specify an argument  or set the config 
* UA loads binary files for the supported mkbrr OS. If you find mkbrr slower than the original torf implementation when hashing torrents, the mkbrr devs are likely to be appreciative of any reports.
"""

__version__ = "4.0.0.2"

"""
Changelog for version 4.0.0.2 (2025-03-13):

- two site files manually imported tmdbsimple.
- fixed R4E by adding the want tmdb data from the main tmdb api call, which negates the need to make a needless api call when uploading to R4E, and will shave around 2 seconds from the time it takes to upload.
- other site file will be fixed when I get around to dealing with that mess.

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.0.1...4.0.0.2

## Version 4 release notes:
## Breaking change
* When using trackers argument,  or , you must now use a comma separated list.

## Linking support in qBitTorrent
### This is not fully tested. 
It seems to be working fine on this windows box, but you absolutely should test with the  argument to make sure it works on your system before putting it into production.
* You can specify to use symbolic or hard links
* 
* Add one or many (local) paths which you want to contain the links, and UA will map the correct drive/volume for hardlinks.

## Reminder
* UA has mkbrr support 
* You can specify an argument  or set the config 
* UA loads binary files for the supported mkbrr OS. If you find mkbrr slower than the original torf implementation when hashing torrents, the mkbrr devs are likely to be appreciative of any reports.
"""

__version__ = "4.0.0.1"

"""
Changelog for version 4.0.0.1 (2025-03-13):

- fix broken trackers handling
- fix client inject when not using linking.

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.0...4.0.0.1

## Version 4 release notes:
## Breaking change
* When using trackers argument,  or , you must now use a comma separated list.

## Linking support in qBitTorrent
### This is not fully tested. 
It seems to be working fine on this windows box, but you absolutely should test with the  argument to make sure it works on your system before putting it into production.
* You can specify to use symbolic or hard links
* 
* Add one or many (local) paths which you want to contain the links, and UA will map the correct drive/volume for hardlinks.

## Reminder
* UA has mkbrr support 
* You can specify an argument  or set the config 
* UA loads binary files for the supported mkbrr OS. If you find mkbrr slower than the original torf implementation when hashing torrents, the mkbrr devs are likely to be appreciative of any reports.
"""

__version__ = "4.0.0"

"""
Changelog for version 4.0.0 (2025-03-13):

Pushing this as v4 given some significant code changes.

## Breaking change
* When using trackers argument,  or , you must now use a comma separated list.

## Linking support in qBitTorrent
### This is not fully tested. 
It seems to be working fine on this windows box, but you absolutely should test with the  argument to make sure it works on your system before putting it into production.
* You can specify to use symbolic or hard links
* 
* Add one or many (local) paths which you want to contain the links, and UA will map the correct drive/volume for hardlinks.

## Reminder
* UA has mkbrr support 
* You can specify an argument  or set the config 
* UA loads binary files for the supported mkbrr OS. If you find mkbrr slower than the original torf implementation when hashing torrents, the mkbrr devs are likely to be appreciative of any reports.

## What's Changed
* move cleanup to file by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/384
* async metadata calls by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/382
* add initial linking support by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/380
* Refactor args parsing by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/383


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/3.6.5...4.0.0
"""

__version__ = "3.6.5"

"""
Changelog for version 3.6.5 (2025-03-12):

## What's Changed
* bunch of id related issues fixed
* if using , take that moment to validate and export the torrent file
* some prettier printing with torf torrent hashing
* mkbrr binary files by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/381


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/3.6.4...3.6.5
"""

__version__ = "3.6.4"

"""
Changelog for version 3.6.4 (2025-03-09):

- Added option to use mkbrr https://github.com/autobrr/mkbrr (). About 4 times faster than torf for a file in cache . Can be set via config
- fixed empty HDB file/folder searching giving bad feedback print

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/3.6.3.1...3.6.4
"""

__version__ = "3.6.3.1"

"""
Changelog for version 3.6.3.1 (2025-03-09):

- Fix BTN ID grabbing

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/3.6.3...3.6.3.1
"""

__version__ = "3.6.3"

"""
Changelog for version 3.6.3 (2025-03-09):

## Config changes
* As part of the effort to fix unresponsive terminals on unix systems, a new config option has been added , and an existing config option , now has a default setting even if commented out/not preset.
* Non-unix users (or users without terminal issue) should uncomment and modify these settings to taste
* https://github.com/Audionut/Upload-Assistant/blob/de7689ff36f76d7ba9b92afe1175b703a59cda65/data/example-config.py#L53

## What's Changed
* Create YUS.py by @fiftieth3322 in https://github.com/Audionut/Upload-Assistant/pull/373
* remote_path as list by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/365
* Correcting PROPER number namings in title by @Zips-sipZ in https://github.com/Audionut/Upload-Assistant/pull/378
* Save extracted description images to disk (can be useful for rehosting to save the capture/optimization step)
* Updates/fixes to ID handling across the board
* Catch session interruptions in AR to ensure session is closed
* Work around a bug that sets empty description to None, breaking repeated processing with same meta
* Remote paths now accept list
* More effort to stop unix terminals shitting the bed

## New Contributors
* @fiftieth3322 made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/373

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/3.6.2...3.6.3
"""

__version__ = "3.6.2"

"""
Changelog for version 3.6.2 (2025-03-04):

## Update Notification
This release adds some new config options relating to update notifications: https://github.com/Audionut/Upload-Assistant/blob/a8b9ada38323c2f05b0f808d1d19d1d79c2a9acf/data/example-config.py#L9

## What's Changed
* Add proper2 and proper3 support by @Kha-kis in https://github.com/Audionut/Upload-Assistant/pull/371
* added update notification
* HDB image rehosting updates
* updated srrdb handling
* other minor fixes


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/3.6.1...3.6.2
"""

__version__ = "3.6.1"

"""
Changelog for version 3.6.1 (2025-03-01):

- fix manual package screens uploading
- switch to subprocess for setting stty sane
- print version to console
- other minor fixes

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/3.6.0...3.6.1
"""

__version__ = "3.6.0"

"""
Changelog for version 3.6.0 (2025-02-28):

## What's Changed
* cleanup tasks by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/364


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/3.5.3.3...3.6.0
"""

__version__ = "3.5.3.1"
