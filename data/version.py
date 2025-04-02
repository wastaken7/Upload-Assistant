__version__ = "4.1.3"

"""
Changelog for version 4.1.3 (2025-04-02):

- All torrent creation issues should now be fixed
- Site upload issues are gracefully handled
- tvmaze episode title fallback
- Fix web/hdtv dupe handling

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.2...4.1.3
"""

__version__ = "4.1.2"

"""
Changelog for version 4.1.2 (2025-03-30):

## What's Changed
* Added support for DarkPeers and Rastastugan by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/431
* fixed HDB missing call for torf regeneration
* fixed cutoff screens handling when taking images
* fixed existing image timeout error causing UA to hard crash
* tweaked  pathway to ensure no duplicate api calls
* fixed a duplicate import in PTP that could cause some python versions to hard error
* removed JPTV

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.1...4.1.2
"""

__version__ = "4.1.1"

"""
Changelog for version 4.1.1 (2025-03-30):

## What's Changed
* add argument --not-anime by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/430
* fixed linking on linux when volumes have the same mount
* fixed torf torrent regeneration in MTV
* added null language check for tmdb logo (mostly useful for movies)
* fixed 
* fixed ssrdb release matching print
* fixed tvdb season matching under some conditions (wasn't serious)

Check v4.1.0 release notes if not already https://github.com/Audionut/Upload-Assistant/releases/tag/4.1.0

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.0.2...4.1.1
"""

__version__ = "4.1.0.2"

"""
Changelog for version 4.1.0.2 (2025-03-29):

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.0.1...4.1.0.2

4..1.0 release notes:

## New config options
See example-config.py
-  and  - add tv series logo to top of descriptions with size control
-  - from the last release, adds tv series overview to description. Now includes season name and details if applicable, see below
-  (qBitTorrent v5+ only) - don't automatically try and find a matching torrent from just the path
-  and  for tvdb data support

## Notes
- UA will now try and automatically find a torrent from qBitTorrent (v5+ only) that matches any site based argument. If it finds a matching torrent, for instance from PTP, it will automatically set . In other words, you no longer need to set a site argument ( or  or --whatever (or  and/or ) as UA will now do this automatically if the path matches a torrent in client. Use the applicable config option to disable this default behavior.

- TVDB requires token to be initially inputted, after which time it will be auto generated as needed.
- Automatic Absolute Order to Aired Order season/episode numbering with TVDB.
- BHD now supports torrent id instead of just hash.
- Some mkbrr updates, including support for  and rehashing for sites as needed.
- TMDB searching should be improved.


See examples below for new logo and episode data handling.
<img src=https://github.com/user-attachments/assets/b2dc4a64-236d-4b77-af32-abe9b1b4fb44 width=400> <img src=https://github.com/user-attachments/assets/19011997-977b-4e19-b45b-51db598aba17 width=346>


## What's Changed
* BHD torrent id parsing by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/417
* Better title/year parsing for tmdb searching by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/416
* feat: pull logo from tmdb by @markhc in https://github.com/Audionut/Upload-Assistant/pull/425
* fix: logo displayed as None by @markhc in https://github.com/Audionut/Upload-Assistant/pull/427
* Update region.py by @ikitub3 in https://github.com/Audionut/Upload-Assistant/pull/429
* proper mkbrr handling by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/397
* TVDB support by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/423
* qBitTorrent auto torrent grabing and rTorrent infohash support by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/428

## New Contributors
* @markhc made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/425
* @ikitub3 made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/429

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.6...4.1.0
"""

__version__ = "4.1.0.1"

"""
Changelog for version 4.1.0.1 (2025-03-29):

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.0...4.1.0.1

From 4.1.0

## New config options
See example-config.py
-  and  - add tv series logo to top of descriptions with size control
-  - from the last release, adds tv series overview to description. Now includes season name and details if applicable, see below
-  (qBitTorrent v5+ only) - don't automatically try and find a matching torrent from just the path
-  and  for tvdb data support

## Notes
- UA will now try and automatically find a torrent from qBitTorrent (v5+ only) that matches any site based argument. If it finds a matching torrent, for instance from PTP, it will automatically set . In other words, you no longer need to set a site argument ( or  or --whatever (or  and/or ) as UA will now do this automatically if the path matches a torrent in client. Use the applicable config option to disable this default behavior.

- TVDB requires token to be initially inputted, after which time it will be auto generated as needed.
- Automatic Absolute Order to Aired Order season/episode numbering with TVDB.
- BHD now supports torrent id instead of just hash.
- Some mkbrr updates, including support for  and rehashing for sites as needed.
- TMDB searching should be improved.


See examples below for new logo and episode data handling.
<img src=https://github.com/user-attachments/assets/b2dc4a64-236d-4b77-af32-abe9b1b4fb44 width=400> <img src=https://github.com/user-attachments/assets/19011997-977b-4e19-b45b-51db598aba17 width=346>


## What's Changed
* BHD torrent id parsing by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/417
* Better title/year parsing for tmdb searching by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/416
* feat: pull logo from tmdb by @markhc in https://github.com/Audionut/Upload-Assistant/pull/425
* fix: logo displayed as None by @markhc in https://github.com/Audionut/Upload-Assistant/pull/427
* Update region.py by @ikitub3 in https://github.com/Audionut/Upload-Assistant/pull/429
* proper mkbrr handling by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/397
* TVDB support by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/423
* qBitTorrent auto torrent grabing and rTorrent infohash support by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/428

## New Contributors
* @markhc made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/425
* @ikitub3 made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/429

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.6...4.1.0
"""

__version__ = "4.1.0"

"""
Changelog for version 4.1.0 (2025-03-29):

## New config options
See example-config.py
-  and  - add tv series logo to top of descriptions with size control
-  - from the last release, adds tv series overview to description. Now includes season name and details if applicable, see below
-  (qBitTorrent v5+ only) - don't automatically try and find a matching torrent from just the path
-  and  for tvdb data support

## Notes
- UA will now try and automatically find a torrent from qBitTorrent (v5+ only) that matches any site based argument. If it finds a matching torrent, for instance from PTP, it will automatically set . In other words, you no longer need to set a site argument ( or  or --whatever (or  and/or ) as UA will now do this automatically if the path matches a torrent in client. Use the applicable config option to disable this default behavior.

- TVDB requires token to be initially inputted, after which time it will be auto generated as needed.
- Automatic Absolute Order to Aired Order season/episode numbering with TVDB.
- BHD now supports torrent id instead of just hash.
- Some mkbrr updates, including support for  and rehashing for sites as needed.
- TMDB searching should be improved.


See examples below for new logo and episode data handling.
<img src=https://github.com/user-attachments/assets/b2dc4a64-236d-4b77-af32-abe9b1b4fb44 width=400> <img src=https://github.com/user-attachments/assets/19011997-977b-4e19-b45b-51db598aba17 width=346>


## What's Changed
* BHD torrent id parsing by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/417
* Better title/year parsing for tmdb searching by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/416
* feat: pull logo from tmdb by @markhc in https://github.com/Audionut/Upload-Assistant/pull/425
* fix: logo displayed as None by @markhc in https://github.com/Audionut/Upload-Assistant/pull/427
* Update region.py by @ikitub3 in https://github.com/Audionut/Upload-Assistant/pull/429
* proper mkbrr handling by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/397
* TVDB support by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/423
* qBitTorrent auto torrent grabing and rTorrent infohash support by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/428

## New Contributors
* @markhc made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/425
* @ikitub3 made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/429

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.6...4.1.0
"""

__version__ = "4.0.6"

"""
Changelog for version 4.0.6 (2025-03-25):

## What's Changed
* update to improve 540 detection by @swannie-eire in https://github.com/Audionut/Upload-Assistant/pull/413
* Update YUS.py by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/414
* BHD - file/folder searching by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/415
* Allow some hardcoded user overrides by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/411
* option episode overview in description by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/418
* Catch HUNO BluRay naming requirement by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/419
* group tag regex by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/420
* OTW - stop pre-filtering image hosts
* revert automatic episode title

BHD auto searching does not currently return description/image links


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.5...4.0.6
"""

__version__ = "4.0.5"

"""
Changelog for version 4.0.5 (2025-03-21):

## What's Changed
* Refactor TOCA.py by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/410
* fixed an imdb search returning bad results
* don't run episode title checks on season packs or episode == 0
* cleaned PTP mediainfo in packed content (scrubbed by PTP upload parser anyway)
* fixed some sites duplicating episode title
* docker should only pull needed mkbrr binaries, not all of them
* removed private details from some console prints
* fixed handling in ptp mediainfo check
* fixed  arg work with no value
* removed rehosting from OTW, they seem fine with ptpimg now.

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.4...4.0.5
"""

__version__ = "4.0.4"

"""
Changelog for version 4.0.4 (2025-03-19):

## What's Changed
* get episode title from tmdb by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/403
* supporting 540p by @swannie-eire in https://github.com/Audionut/Upload-Assistant/pull/404
* LT - fix no distributor api endpoint by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/406
* reset terminal fix
* ULCX content checks
* PTP - set EN sub flag when trumpable for HC's English subs
* PTP - fixed an issue where description images were not being parsed correctly
* Caught an IMDB issue when no IMDB is returned by metadata functions
* Changed the banned groups/claims checking to daily

## Episode title data change
Instead of relying solely on guessit to catch episode titles, UA now pulls episode title information from TMDB. There is some pre-filtering to catch placeholder title information like 'Episode 2', but you should monitor your TV uploads. Setting  with an empty space will clear the episode title.

Conversely (reminder of already existing functionality), setting met with some title  will force that episode title.


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.3.1...4.0.4
"""

__version__ = "4.0.3.1"

"""
Changelog for version 4.0.3.1 (2025-03-17):

- Fix erroneous AKA in title when AKA empty

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.3...4.0.3.1
"""

__version__ = "4.0.3"

"""
Changelog for version 4.0.3 (2025-03-17):

## What's Changed
* Update naming logic for SP Anime Uploads by @tubaboy26 in https://github.com/Audionut/Upload-Assistant/pull/399
* Fix ITT torrent comment by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/400
* Fix --cleanup without path
* Fix tracker casing
* Fix AKA

## New Contributors
* @tubaboy26 made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/399

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.2...4.0.3
"""

__version__ = "4.0.2"

"""
Changelog for version 4.0.2 (2025-03-15):

## What's Changed
* Update CBR.py by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/392
* Update ITT.py by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/393
* Added support for TocaShare by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/394
* Force auto torrent management to false when using linking

## New Contributors
* @wastaken7 made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/392

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.1...4.0.2
"""

__version__ = "4.0.1"

"""
Changelog for version 4.0.1 (2025-03-14):

- fixed a tracker handling error when answering no to title confirmation
- fixed imdb from srrdb
- strip matching distributor from title and add to meta object
- other little fixes

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.0.0.3...4.0.1
"""

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
