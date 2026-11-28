# Qt 6.12.0 component notices

This directory records the attribution review of the Windows PySide6 6.12.0 package (wheels `PySide6_Essentials`, `PySide6_Addons` and `shiboken6`) on 2026-11-15. The Hub executable bundles the Qt Core, GUI, Network, SVG and Widgets libraries and the image, icon, platform, style and TLS plugins listed in `compilation-report.xml` of the build. The Qt PDF image plugin is excluded.

Versions and license identifiers come from the `qt_attribution.json` files of the Qt source tags `v6.12.0` ([qtbase](https://github.com/qt/qtbase/tree/v6.12.0/src/3rdparty), [qtimageformats](https://github.com/qt/qtimageformats/tree/v6.12.0/src/3rdparty), [qtsvg](https://github.com/qt/qtsvg/tree/v6.12.0)). License texts were copied from the same tags. The evidence column states what was observed in the Windows binaries; "source tag only" means the binary does not expose a version string, so presence and version follow Qt's source attribution and were not confirmed in the binary.

| Component | Version at the Qt tag | Evidence in the binaries | License | Local text |
| --- | --- | --- | --- | --- |
| libjpeg-turbo (`qjpeg.dll`) | 3.2.0 | Binary reports `libjpeg-turbo version 3.2.0`. | IJG and BSD-3-Clause (plus Zlib terms in the libjpeg-turbo license) | [LICENSE.md](jpeg-3.2.0/LICENSE.md), [README.ijg](jpeg-3.2.0/README.ijg), [ijg-license.txt](jpeg-3.2.0/ijg-license.txt) |
| libtiff (`qtiff.dll`) | 4.7.2 | Binary contains libtiff source strings, including `LIBTIFF_STRILE_ARRAY_MAX_RESIZE_COUNT` and a reference to libtiff 4.5.1 in a tag message. The exact version is source tag only. | `libtiff` | [COPYRIGHT](imageformats/libtiff-COPYRIGHT.txt) |
| libwebp (`qwebp.dll`) | 1.6.0 | Plugin and VP8/VP8L/VP8X decoder tags present. Exact version is source tag only. | BSD-3-Clause | [COPYING](imageformats/libwebp-COPYING.txt), [PATENTS](imageformats/libwebp-PATENTS.txt) |
| XSVG arc handling in `qt6svg.dll` (`qsvghandler.cpp`) | n/a | Qt SVG 6.12.0 present. Attribution from the source tag's `REUSE.toml`. | `HPND-sell-variant` | [HPND-sell-variant.txt](svg/HPND-sell-variant.txt) |
| libpng (`Qt6Gui.dll`) | 1.6.58 | Binary contains `1.6.58`. | `Libpng AND libpng-2.0` | [LICENSE](core-gui/libpng-LICENSE.txt) |
| PCRE2 and SLJIT (`Qt6Core.dll`) | 10.48 | Binary contains `10.48` and PCRE2 messages. | PCRE2 BSD-3-Clause with the binary-like packages exception; SLJIT BSD-2-Clause | [LICENCE.md](core-gui/pcre2-LICENCE.md), [SLJIT](core-gui/pcre2-LICENSE-SLJIT.txt) |
| FreeType 2 (`Qt6Gui.dll`) | 2.14.3 | Binary contains the FreeType font database classes. Version is source tag only. | `FTL OR GPL-2.0-only`, plus Zlib, BDF (MIT) and PCF (MIT) parts | [LICENSE](core-gui/freetype-LICENSE.txt), [ZLIB](core-gui/freetype-ZLIB-LICENSE.txt), [BDF](core-gui/freetype-BDF-LICENSE.txt), [PCF](core-gui/freetype-PCF-LICENSE.txt) |
| HarfBuzz (`Qt6Gui.dll`) | 14.5.0 | Binary contains HarfBuzz strings. Version is source tag only. | MIT | [COPYING](core-gui/harfbuzz-COPYING.txt) |
| double-conversion | 3.4.0 | Source tag only. | BSD-3-Clause | [LICENSE](core-gui/double-conversion-LICENSE.txt) |
| MD4C | 0.5.3 | Source tag only. | MIT | [LICENSE.md](core-gui/md4c-LICENSE.md) |
| TinyCBOR | 7.0 | Source tag only. | MIT | [LICENSE](core-gui/tinycbor-LICENSE.txt) |
| Emoji Segmenter | 0.4.0 | Source tag only. | Apache-2.0 | [Apache-2.0.txt](core-gui/Apache-2.0.txt) |
| sRGB ICC profile | n/a | Source tag only. | `LicenseRef-ICC-License` | [LICENSE](core-gui/icc-LICENSE.txt) |
| Easing equations (Robert Penner) | n/a | Source tag only. | BSD-3-Clause | [LICENSE](core-gui/easing-LICENSE.txt) |
| SHA-384 and SHA-512 (RFC 6234) | n/a | Source tag only. | BSD-3-Clause | [LICENSE](core-gui/rfc6234-LICENSE.txt) |
| BLAKE2 reference implementation | revision `ed1974e` | Source tag only. | `CC0-1.0 OR Apache-2.0` | [COPYING](core-gui/blake2-COPYING.txt) |
| SHA-3 (Keccak 3.2 and brg_endian) | 3.2 and 1.0.0 | Source tag only. | CC0-1.0 and BSD-2-Clause | [CC0](core-gui/sha3-CC0_LICENSE.txt), [brg_endian](core-gui/sha3-BRG_ENDIAN_LICENSE.txt) |
| D3D12 Memory Allocator | 3.1.0 | Source tag only. | MIT | [LICENSE](core-gui/d3d12ma-LICENSE.txt) |

Components in the Qt tag that this review treats as not bundled in the Windows package: libpsl and the Public Suffix List (no reference in `Qt6Network.dll`), SQLite, Wayland protocols, forkfd, Android and WebAssembly support code, and the Qt PDF image plugin with its Chromium, PDFium and Abseil code. SipHash, MD4, MD5 and SHA-1 are listed in Qt's attributions as CC0 or public domain and have no license file at the tag.

## Open items

- The binaries do not expose versions for FreeType, HarfBuzz, libtiff, libwebp and the smaller components. Their rows follow Qt's source attribution and could be wrong if the wheel build used different sources.
- The OpenSSL, zlib and Windows runtime notices are tracked in `THIRD_PARTY_NOTICES.md`, not here.
- The LGPLv3 distribution route (replacing or relinking the bundled Qt libraries in the onefile executable) is not resolved by this inventory.
