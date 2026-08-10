## DEFAULT

**Most of these values are REQUIRED if you intend to use these services**

- The Movie Database: `tmdb_api` **REQUIRED**
  - There are fantastic instructions w/ screenshots on how to obtain a tmdb api key at https://developers.themoviedb.org/3/getting-started/introduction

- Image Hosts and their respective API keys: e.g.`imgbb_api`
  - Only one image host is **REQUIRED**, but extras are nice to have.
  - Acceptable values for `img_host_x` are:
    - imgbb
      - Notes: 32MB Cap, easy to signup and get your api key. Kinda slowish
    - imgbox
      - Notes: 10MB Cap. No signup needed. Recommended.
    - lostimg
      - Notes: JSON response API. API Key can be created/found in Settings.

- Default number of screenshots per upload: `screens` **REQUIRED**
  - Recommended value = 6

- Default torrent client: `default_torrent_client` **REQUIRED**
  - The "NAME" of the torrent client you'd like to use by default.
  - Values for this will be set in the Torrent Clients section below.

## Trackers

- Default Trackers: `default_trackers` **REQUIRED**
  - A comma separated list of trackers to upload to
  - See the [supported sites](../README.md#supported-sites) table for the current tracker registry.
  - `MANUAL` = passing `-m` / `--manual`

- API Key: `api_key`
  - Your API key for each respective site
  - Used to upload and check for potential duplicates
  - Most commonly found in your security settings

- Announce Url: `announce_url`
  - Your custom announce url
  - Most commonly found on the site's upload page

- Draft Default: `draft_default`
  - If the site has a draft system, setting `True` will send to drafts by default
  - Setting `False` will go live by default

- Anonymous: `anon` **OPTIONAL**
  - This is the ability to upload anonymous, on a per-tracker basis.
  - You will need to uncomment this line for it to take effect
  - Setting `False` will upload publicly
  - Setting `True` will upload anonymously

## Torrent Clients

**This field is REQUIRED and only ONE is needed, but if you have more, you can switch easily by changing the `default_torrent_client` or calling --client [NAME] while uploading.**

If you wish to add to your client manually use `none`.

If you have only one client, I recommend just editing the sample config for your client.
\*\*After editing, set the `default_torrent_client` setting to your client's name

NOTE: If using Windows paths, change `\` into `\\`. For example `C:\Downloads\TV` should be `C:\\Downloads\\TV` or use r-strings `r'E:\\'`

- Each client has a `remote_path` and `local_path` option:
  - These are used if the path to your data is different than what your client sees. e.g. "D:\Downloads" on the system running the script and "/data/downloads" on the system running your client
  - If this script and your client are running on the same system, set these values to paths that don't exist OR make them the same
    ```python
    "local_path" : r"M:\Seeding",
    "remote_path" : r"M:\Seeding"
    ```
    OR if you have multiple remote path mappings:
    ```python
    "local_path" : [
        r'E:\Path1',
        r'F:\Path2',
        ],
    "remote_path" : [
        '/data/downloads1',
        '/data/downloads2',
        ],
    ```

- Example rtorrent w/ rutorrent config:
  - NOTE: If your password has special characters, url encode it at [https://www.urlencoder.org/](https://www.urlencoder.org/)
  - Your rtorrent_url may vary depending on your setup, here are some that are working. You most likely will use one of/a variation of these:
    - seedhost/swizzin with domains: `https://user:password@server1234.domain.tld:443/username/rutorrent/plugins/httprpc/action.php`
    - usb : `https://user:password@server.domain.tld:443/RPC2`
    - [whatbox](https://whatbox.ca/wiki/Using_XMLRPC_with_Python) : `https://user:(Your password)@server.whatbox.ca:443/xmlrpc`
    - `https://user:password@127.0.0.1/rutorrent/plugins/httprpc/action.php`

  ```python
  "NAME" : {
              "torrent_client" : "rtorrent",
              "rtorrent_url" : "https://user:password@server.host.tld:443/username/rutorrent/plugins/httprpc/action.php",
          },
  ```

- Example qbittorrent config:

  ```python
  "NAME" : {
              "torrent_client" : "qbit",
              "qbit_url" : "http://127.0.0.1",
              "qbit_port" : "8080",
              "qbit_user" : "username",
              "qbit_pass" : "password",
          },
  ```

- Example deluge config:

  ```python
  "NAME" : {
             "torrent_client" : "deluge",
             "deluge_url" : "localhost",
             "deluge_port" : "8080",
             "deluge_user" : "username",
             "deluge_password" : "password",
         },
  ```

- Example watch folder config:

  ```python
  "NAME" : {
             "torrent_client" : "watch",
             "watch_folder" : "/Path/To/Watch/Folder"
         },
  ```
