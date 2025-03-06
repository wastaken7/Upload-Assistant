[![Create and publish a Docker image](https://github.com/Audionut/Upload-Assistant/actions/workflows/docker-image.yml/badge.svg?branch=master)](https://github.com/Audionut/Upload-Assistant/actions/workflows/docker-image.yml)

Discord support https://discord.gg/QHHAZu7e2A

# Audionut's Upload Assistant

A simple tool to take the work out of uploading.

This project is a fork of the original work of L4G https://github.com/L4GSP1KE/Upload-Assistant
Immense thanks to him for establishing this project. Without his (and supporters) time and effort, this fork would not be a thing.
What started as simply pushing some pull requests to keep the main repo inline, as L4G seemed busy with IRL, has since snowballed into full time development, bugs and all.

Many other forks exist, most are simply a rebranding of this fork without any credit whatsoever.
Better just to be on this fork and bug me about my bugs, rather than bugging someone who can ctrl+c/ctrl+v, but likely can't fix the bugs.

## What It Can Do:
  - Generates and Parses MediaInfo/BDInfo.
  - Generates and Uploads screenshots.
  - Uses srrdb to fix scene filenames.
  - Can grab descriptions from PTP/BLU/Aither/LST/OE (with config option automatically on filename match, or using arg).
  - Can strip existing screenshots from descriptions to skip screenshot generation and uploading.
  - Obtains TMDb/IMDb/MAL identifiers.
  - Converts absolute to season episode numbering for Anime.
  - Generates custom .torrents without useless top level folders/nfos.
  - Can re-use existing torrents instead of hashing new.
  - Generates proper name for your upload using Mediainfo/BDInfo and TMDb/IMDb conforming to site rules.
  - Checks for existing releases already on site.
  - Uploads to ACM/Aither/AL/ANT/AR/BHD/BHDTV/BLU/CBR/FRIKI/FNP/FL/HDB/HDT/HHD/HP/HUNO/ITT/JPTV/LCD/LST/LT/MTV/NBL/OE/OTW/PSS/PTP/PTER/PTT/RF/R4E(limited)/RTF/SHRI/SN/SP/SPD/STC/STT/TLC/THR/TL/TVC/TTG/ULCX/UTP/YOINK/YUS
  - Adds to your client with fast resume, seeding instantly (rtorrent/qbittorrent/deluge/watch folder).
  - ALL WITH MINIMAL INPUT!
  - Currently works with .mkv/.mp4/Blu-ray/DVD/HD-DVDs.

Built with updated BDInfoCLI from https://github.com/rokibhasansagar/BDInfoCLI-ng

## **Setup:**
   - **REQUIRES AT LEAST PYTHON 3.9 AND PIP3**
   - Needs [mono](https://www.mono-project.com/) on linux systems for BDInfo
   - Also needs MediaInfo and ffmpeg installed on your system
      - On Windows systems, ffmpeg must be added to PATH (https://windowsloop.com/install-ffmpeg-windows-10/)
      - On linux systems, get it from your favorite package manager
   - Clone the repo to your system `git clone https://github.com/Audionut/Upload-Assistant.git` - or download a zip of the source
   - Copy and Rename `data/example-config.py` to `data/config.py`
   - Edit `config.py` to use your information (more detailed information in the [wiki](https://github.com/Audionut/Upload-Assistant/wiki))
      - tmdb_api (v3) key can be obtained from https://developers.themoviedb.org/3/getting-started/introduction
      - image host api keys can be obtained from their respective sites
   - Install necessary python modules `pip3 install --user -U -r requirements.txt`
     
   
   **Additional Resources are found in the [wiki](https://github.com/Audionut/Upload-Assistant/wiki)**
   
   Feel free to contact me if you need help, I'm not that hard to find.

## **Updating:**
  - To update first navigate into the Upload-Assistant directory: `cd Upload-Assistant`
  - Run a `git pull` to grab latest updates
  - Run `python3 -m pip install --user -U -r requirements.txt` to ensure dependencies are up to date
  - Or download a fresh zip and overwrite existing files

## **CLI Usage:**
  
  `python3 upload.py "/downloads/path/to/content" --args`
  
  Args are OPTIONAL and ALWAYS follow path, for a list of acceptable args, pass `--help`.
  Path should be in quotes.

## **Docker Usage:**
  Visit our wonderful [docker usage wiki page](https://github.com/Audionut/Upload-Assistant/wiki/Docker)
