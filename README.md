[![Create and publish a Docker image](https://github.com/Audionut/Upload-Assistant/actions/workflows/docker-image.yml/badge.svg?branch=master)](https://github.com/Audionut/Upload-Assistant/actions/workflows/docker-image.yml)

Discord support https://discord.gg/QHHAZu7e2A

# L4G's Upload Assistant

A simple tool to take the work out of uploading.

## What It Can Do:
  - Generates and Parses MediaInfo/BDInfo.
  - Generates and Uploads screenshots.
  - Uses srrdb to fix scene filenames
  - Can grab descriptions from PTP/BLU/Aither/LST/OE (with config option automatically on filename match, or using arg)
  - Can strip existing screenshots from descriptions to skip screenshot generation and uploading
  - Obtains TMDb/IMDb/MAL identifiers.
  - Converts absolute to season episode numbering for Anime
  - Generates custom .torrents without useless top level folders/nfos.
  - Can re-use existing torrents instead of hashing new
  - Generates proper name for your upload using Mediainfo/BDInfo and TMDb/IMDb conforming to site rules
  - Checks for existing releases already on site
  - Uploads to ACM/Aither/AL/ANT/BHD/BHDTV/BLU/CBR/FNP/FL/HDB/HDT/HHD/HP/HUNO/JPTV/LCD/LST/LT/MTV/NBL/OE/OTW/PSS/PTP/PTER/PTT/RF/R4E(limited)/RTF/SHRI/SN/SPD/STC/STT/TLC/THR/TL/TVC/TTG/ULCX/UTP/YOINK
  - Adds to your client with fast resume, seeding instantly (rtorrent/qbittorrent/deluge/watch folder)
  - ALL WITH MINIMAL INPUT!
  - Currently works with .mkv/.mp4/Blu-ray/DVD/HD-DVDs

Built with updated BDInfoCLI from https://github.com/rokibhasansagar/BDInfoCLI-ng

## Coming Soon:
  - Features

  

## **Setup:**
   - **REQUIRES AT LEAST PYTHON 3.12 AND PIP3**
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
  
  `python3 upload.py /downloads/path/to/content --args`
  
  Args are OPTIONAL, for a list of acceptable args, pass `--help`
## **Docker Usage:**
  Visit our wonderful [docker usage wiki page](https://github.com/Audionut/Upload-Assistant/wiki/Docker)
