# Local video preview runtime

The desktop download detail view first uses PySide6/Qt Multimedia for local video
preview playback. This is bundled with the desktop Python dependency set and does
not require users to install a separate player.

If Qt Multimedia is unavailable or cannot play the file, the preview falls back to
`mpv`/`libmpv`. The Python package `mpv` is only a binding; it does not bundle the
native `libmpv` runtime.

On Windows, place the mpv runtime files in one of these directories before launching
the desktop app:

- `runtime/mpv/`
- `vendor/mpv/`
- `mpv/`

At minimum the directory must contain the native `libmpv` DLL and its required
dependencies. If the runtime is missing, the preview pane displays an error instead
of crashing the download detail dialog. The app also shows a direct libmpv download
URL that is intended to be reachable from China:

https://sourceforge.net/projects/mpv-player-windows/files/libmpv/

New YouTube downloads still prefer H.264 MP4 for compatibility. The mpv backend is
kept as a fallback so existing AV1/VP9 files can be previewed when Qt Multimedia
cannot handle them but a capable `libmpv` runtime is available.
