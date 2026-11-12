# datapatchbay brand assets

The logo is the name set as a patchbay label strip, with one jack under each letter. The jacks under **d a t** are the data sources and carry red plugs. They fan out through split leads into every jack under **patchbay**. The jack under the last *a* of *data* stays open.

Everything here is generated. To change the logo, edit `build.py` and run:

```sh
python3 assets/build.py   # needs fontTools, Pillow and Google Chrome
```

## Files

| File | Use |
| --- | --- |
| `logo/datapatchbay-logo-light.svg` / `.png` | Logo on light backgrounds |
| `logo/datapatchbay-logo-dark.svg` / `.png` | Logo on dark backgrounds |
| `logo/datapatchbay-logo-mono-ink.svg` | One colour (ink), for print and stamps |
| `logo/datapatchbay-logo-mono-white.svg` | One colour (white), for dark print |
| `icon/avatar-512.png` | GitHub org avatar |
| `icon/datapatchbay-icon-dark.svg`, `-light.svg` | Square icon: `dpb` over three jacks |
| `icon/favicon.svg`, `favicon.ico`, `favicon-32.png` | Docs favicon (no lettering, so it reads at 16px) |
| `icon/apple-touch-icon.png` | iOS home screen, 180×180 |
| `social/social-preview.png` | GitHub social preview, 1280×640 |

The lettering is outlined to paths, so the SVGs don't need the font installed.

## README header

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo/datapatchbay-logo-dark.svg">
  <img alt="datapatchbay" src="assets/logo/datapatchbay-logo-light.svg" width="480">
</picture>
```

## Docs `<head>`

```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
```

## Colours

| Name | Hex | Role |
| --- | --- | --- |
| Ink | `#16181D` | Lettering, jacks and cables on light backgrounds. Background of dark tiles. |
| Panel | `#F3F0E8` | Lettering, jacks and cables on dark backgrounds. Background of light tiles. |
| Patch red | `#E4462B` | Source plugs only. Use it for nothing else in the mark. |
| Muted (light bg) | `#8A8578` | "data" on light backgrounds |
| Muted (dark bg) | `#8E8B83` | "data" on dark backgrounds |

## Type

The lettering is [Michroma](https://github.com/googlefonts/Michroma-font), under the SIL Open Font License 1.1. A copy of the font and its licence is in `fonts/`.
