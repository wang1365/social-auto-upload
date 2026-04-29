# mpv video preview runtime

The desktop download detail view uses `mpv`/`libmpv` for local video preview playback.
The Python package `mpv` is only a binding; it does not bundle the native `libmpv`
runtime.

On Windows, place the mpv runtime files in one of these directories before launching
the desktop app:

- `runtime/mpv/`
- `vendor/mpv/`
- `mpv/`

At minimum the directory must contain the native `libmpv` DLL and its required
dependencies. If the runtime is missing, the preview pane displays an error instead
of crashing the download detail dialog.

New YouTube downloads still prefer H.264 MP4 for compatibility. The mpv backend is
used so existing AV1/VP9 files can be previewed when a capable `libmpv` runtime is
available.
