# Qt 6.10.1 component notices

This directory records the Qt attribution review for the Windows PySide6 6.10.1 package on 2026-11-14. It includes upstream notices for the components listed below. The Qt source tag identifies the reference source set. The selected build options and some embedded versions remain unresolved.

| Package component | Evidence and version | License and local attribution |
| --- | --- | --- |
| JPEG plugin `qjpeg.dll` | Binary identifies libjpeg-turbo 3.0.3. The Qt tag's vendored version is 3.1.2. | IJG, BSD-3-Clause and Zlib terms described in [LICENSE.md](jpeg-3.0.3/LICENSE.md), with the [IJG notice](jpeg-3.0.3/README.ijg). [Version 3.0.3 source](https://github.com/libjpeg-turbo/libjpeg-turbo/tree/3.0.3) |
| TIFF plugin `qtiff.dll` | Binary contains libtiff source and diagnostic strings. The exact version is unresolved. Qt's reference version is 4.7.1. | `libtiff`. [Copyright and license text from the Qt tag](imageformats/libtiff-COPYRIGHT.txt). [Qt attribution](https://github.com/qt/qtimageformats/blob/v6.10.1/src/3rdparty/libtiff/qt_attribution.json) |
| WebP plugin `qwebp.dll` | Plugin is present. The exact codec variant and version are unresolved. Qt's reference version is libwebp 1.6.0. | `BSD-3-Clause`. [Copying conditions](imageformats/libwebp-COPYING.txt) and [patent grant](imageformats/libwebp-PATENTS.txt) from the Qt tag. [Qt attribution](https://github.com/qt/qtimageformats/blob/v6.10.1/src/3rdparty/libwebp/qt_attribution.json) |
| SVG library `qt6svg.dll` and SVG plugins | Qt SVG 6.10.1 is present. Qt attributes arc handling in its SVG handler source to XSVG. | `HPND-sell-variant`. [XSVG copyright and license](svg/XSVG-LICENSE.txt). [Qt attribution](https://github.com/qt/qtsvg/blob/v6.10.1/src/svg/qt_attribution.json) |

Qt Core, GUI, Network, Widgets, and the remaining Windows plugins still need an embedded-dependency cross-check against the wheel build. The generic Qt 6.10 documentation currently tracks a later patch release. Use it as an index alongside the 6.10.1 source attributions and matching build metadata. See `THIRD_PARTY_NOTICES.md` at the root of the package for the main Qt license and distribution review.
