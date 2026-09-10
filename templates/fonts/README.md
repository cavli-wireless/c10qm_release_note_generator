# Optional: embed Roboto for pixel-exact output

The reference document (`CQS290_RELEASE_NOTE_SDK_2.0.0.pdf`) was typeset in
**Roboto**. Chrome only uses Roboto if it's installed on the machine doing the
rendering — on Windows it usually isn't, so the CSS falls back to Segoe UI /
Arial. The layout, colors and type scale still match, but line breaks shift
slightly because the fallback faces are a little wider than Roboto.

To make output identical everywhere, drop these files into this folder:

    Roboto-Regular.woff2   (or .ttf)
    Roboto-Bold.woff2
    Roboto-Italic.woff2

`render_release_note.py` finds them automatically, base64-embeds them as
`@font-face` rules in the generated HTML, and the PDF then renders in Roboto
regardless of what's installed. Nothing else needs changing.

Get them from https://fonts.google.com/specimen/Roboto (Apache 2.0), or on a
machine that already has Roboto installed, copy the .ttf files from the system
font folder.

Weight/style is detected from the filename (`bold`, `italic`, `bolditalic`,
`medium`, `regular`), so keep Google's naming.
