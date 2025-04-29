__version__ = "4.2.1"

"""
Changelog for version 4.2.1 (2025-04-29):

## What's Changed
* Update RAS.py by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/483
* Add support for Portugas by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/482
* OTW - use year in TV title by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/481
* Adding ADN as a provider by @ppkhoa in https://github.com/Audionut/Upload-Assistant/pull/484
* Allow '-s 0' option when uploading to HDB by @GizmoBal in https://github.com/Audionut/Upload-Assistant/pull/485
* CBR: Refactor get_audio function to handle multiple languages by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/488
* Screens handling updates by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/486
* Add comparison images by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/487
* Should be improvements to PTP hardcoded subs handling
* Corrected AR imdb url
* Fixed an issue in a tmdb episode pathway that would fail without tvdb
* Cleaned more private details from debug prints
* Fixed old BHD code to respect only supported BDMV regions
* Update OE against their image hosts rule
* Added passtheima.ge support

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.2.0.1...4.2.1
"""

__version__ = "4.2.0.1"

"""
Changelog for version 4.2.0.1 (2025-04-24):

- OE - only allow with English subs if not English audio
- Fixed the bad copy/paste that missed the ULCX torrent url
- Added the new trackers args auto api to example config
- Fixed overwriting custom descriptions with bad data
- Updated HDR check to find  and correctly check for relevant strings.

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.2.0...4.2.0.1
"""

__version__ = "4.2.0"

"""
Changelog for version 4.2.0 (2025-04-24):

## What's Changed
* store and use any found torrent data by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/452
* Automated bluray region-distributor parsing by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/471
* add image upload retry logic by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/472
* TVC Allow 1080p HEVC by @yoyo292949158 in https://github.com/Audionut/Upload-Assistant/pull/478
* Small fixes to AL title formatting by @b-igu in https://github.com/Audionut/Upload-Assistant/pull/477
* fixed a bug that skipped tvdb episode data handling
* made THR work

## Config additions
* A bunch of new config options starting here: https://github.com/Audionut/Upload-Assistant/blob/b382ece4fde22425dd307d1098198fb3fc9e0289/data/example-config.py#L183

## New Contributors
* @yoyo292949158 made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/478

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.9...4.2.0
"""

__version__ = "4.1.9"

"""
Changelog for version 4.1.9 (2025-04-20):

## What's Changed
* PTP. Do not ask if files with en-GB subs are trumpable. by @GizmoBal in https://github.com/Audionut/Upload-Assistant/pull/459
* Add tag for releases without a group name (PSS) by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/461
* In PTP descriptions, do not replace [code] by [quote]. by @GizmoBal in https://github.com/Audionut/Upload-Assistant/pull/463
* In HDB descriptions, do not replace [code] by [quote]. by @GizmoBal in https://github.com/Audionut/Upload-Assistant/pull/466
* handle cleanup on mac os without termination by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/465
* Refactor CBR.py by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/467
* Description Customization by @zercsy in https://github.com/Audionut/Upload-Assistant/pull/468
* Fixed THR
* Added an option that allows sites to skip upload when content does not contain English
* Fixed cleanup on Mac OS
* Fixed an error causing regenerated torrents to fail being added to client
* Added fallback search for HDB when no IMDB
* Other minor fixes

## New Contributors
* @zercsy made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/468

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.8.1...4.1.9
"""

__version__ = "4.1.8.1"

"""
Changelog for version 4.1.8.1 (2025-04-15):

* Fixed a quote bug

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.8...4.1.8.1
"""

__version__ = "4.1.8"

"""
Changelog for version 4.1.8 (2025-04-14):

## What's Changed
* Correct typo to enable UA to set the 'Internal' tag on HDB. by @GizmoBal in https://github.com/Audionut/Upload-Assistant/pull/456
* Updated AL upload by @b-igu in https://github.com/Audionut/Upload-Assistant/pull/457
* Run cleaning between items in a queue - fixes terminal issue when running a queue
* Fixed an error when imdb returns no results
* Fixes image rehosting was overwriting main image_list

## New Contributors
* @b-igu made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/457

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.7...4.1.8
"""

__version__ = "4.1.7"

"""
Changelog for version 4.1.7 (2025-04-13):

## What's Changed
* Fix missing HHD config in example-config.py by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/455
* Updated mkbrr including fix for BDMV torrent and symlink creation
* Fixed manual source with BHD
* Added nfo file upload support for DP
* Changed logo handling so individual sites can pull language specific logos
* Fixed an error with adding mkbrr regenerated torrents to client
* Refactored Torf torrent creation to be quicker


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.6...4.1.7
"""

__version__ = "4.1.6"

"""
Changelog for version 4.1.6 (2025-04-12):

## What's Changed
* qBittorrent Option: Include Tracker as Tag - New sites SAM and UHD by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/454
* fixed image retaking
* fixed pack images to be saved in unique file now that meta is deleted by default
* updated OE to check all mediainfo when language checking
* updated OTW to include resolution with DVD
* updated DP rule compliance


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.5...4.1.6
"""

__version__ = "4.1.5"

"""
Changelog for version 4.1.5 (2025-04-10):

## What's Changed
* Clean existing meta by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/451
* Added frame overlays to disc based content
* Refactored ss_times


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.4.1...4.1.5
"""

__version__ = "4.1.4.1"

"""
Changelog for version 4.1.4.1 (2025-04-09):

## What's Changed
* Minor fixes in TIK.py by @GizmoBal in https://github.com/Audionut/Upload-Assistant/pull/449
* Fixed year getting inserted into incorrect TV


**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.4...4.1.4.1
"""

__version__ = "4.1.4"

"""
Changelog for version 4.1.4 (2025-04-08):

## What's Changed
* Update SP.py to replace   with . per upload guidelines by @tubaboy26 in https://github.com/Audionut/Upload-Assistant/pull/435
* HUNO - remove region from name by @wastaken7 in https://github.com/Audionut/Upload-Assistant/pull/441
* Correct absolute episode number lookup by @ppkhoa in https://github.com/Audionut/Upload-Assistant/pull/447
* add more args overrides options by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/437
* add rTorrent linking support by @Audionut in https://github.com/Audionut/Upload-Assistant/pull/390
* Accept both relative and absolute path for the description filename. by @GizmoBal in https://github.com/Audionut/Upload-Assistant/pull/448
* Updated dupe checking - mainly to allow uploads when more than 1 of a content is allowed
* Added an argument  which cleans just the tmp directory for the current pathed content
* Hide some not important console prints behind debug
* Fixed HDR tonemapping
* Added config option to overlay some details on screenshots (currently only files)
* Adjust font size of screenshot overlays to match the resolution. by @GizmoBal in https://github.com/Audionut/Upload-Assistant/pull/442
* Fixed manual year
* Other minor fixes

## New Contributors
* @GizmoBal made their first contribution in https://github.com/Audionut/Upload-Assistant/pull/442

**Full Changelog**: https://github.com/Audionut/Upload-Assistant/compare/4.1.3...4.1.4
"""

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
