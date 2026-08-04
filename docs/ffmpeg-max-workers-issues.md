Some users, particularly on seedboxes, may have an outdated/limited ffmpeg installed that will not function correctly with UA.

One method to check is below:

```bash
`which ffmpeg` -v quiet -hide_banner -version | grep -q -- --enable-libzimg && echo "FFmpeg compiled with libzimg" || echo "FFmpeg not compiled with libzimg"
```

Since UA version 5.2.0, you can now provide a static binary for UA to use. Create a folder named `ffmpeg` within the UA bin directory: https://github.com/wastaken7/Upload-Assistant/tree/development/bin

And place the ffmpeg binary `ffmpeg` within this folder.

The following repos have been suggested as suitable ffmpeg binaries:

~~https://github.com/BtbN/FFmpeg-Builds/releases/tag/latest~~ // Some issues have been reported with these builds.

https://github.com/eugeneware/ffmpeg-static

For Windows, the author uses:
https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2025-08-31-13-00
The `ffmpeg-n7.1.1-57-g1b48158a23` type.

There were issues in builds after this date, they may have been resolved since last checked.

ppkhoa says:

> Another way to do this is adding to the start of PATH environment variable the extracted `ffmpeg<version>/bin` path from the release bundles linked above and UA will use that instead.
>
> Example, in my own environment, added this line in `~/.profile`
>
> ```
> export PATH="/home/ppkhoa/ffmpeg-master-latest-linux64-gpl/bin:$PATH"
> ```

Continued issue may be resolved by setting `use_libplacebo` to `False` in config https://github.com/wastaken7/Upload-Assistant/blob/development/data/example_config.py#L82
