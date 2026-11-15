# Third-party notices

AI Profile Hub source is licensed under [MIT](LICENSE). The source checkout declares its PySide6 dependencies in `requirements.txt` and its development tools in `requirements-dev.txt`. Installation obtains those packages separately. The tracked screenshots are project UI captures, and the source checkout ships no standalone third-party font or icon files.

The [AI Profile Hub application icon](profile_switch/assets/app-icon.svg) is project artwork under the same MIT license. The Windows build renders it into an executable icon.

Standalone builds contain third-party code under the terms below. Keep the package's `LICENSE`, this notice and `licenses/` together.

## Standalone runtime

The Windows x64 inventory below uses the installed interpreter and wheels, the Windows package files and the Nuitka compilation report. The current deployment excludes the unused Qt PDF plugin and library. Exact native dependencies vary by platform, interpreter and compiler.

| Component | Observed version | License and source | Package notice |
| --- | --- | --- | --- |
| CPython and its standard library | 3.13.17 | [PSF-2.0 and historical terms](https://github.com/python/cpython/blob/v3.13.17/LICENSE) | `licenses/PYTHON-LICENSE.txt` from the interpreter used to build |
| PySide6 bindings and Shiboken runtime | 6.10.1 | The four pinned wheels declare `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. Qt also offers commercial terms. [Qt for Python source](https://github.com/pyside/pyside-setup/tree/v6.10.1) | LGPLv3 and GPLv3 texts plus wheel-provided notices under `licenses/`. Review both the shared libraries and the PySide6 and Shiboken Python modules compiled into the executable. |
| Qt Core, GUI, Network, Widgets and SVG, plus platform, style, image, icon and TLS plugins | 6.10.1 | `LGPL-3.0-only` is an option in the reviewed Qt sources. Embedded components retain their own terms. [Qt 6.10.1 source archives](https://download.qt.io/official_releases/qt/6.10/6.10.1/submodules/) | LGPLv3 and GPLv3 texts in `licenses/`. See the Qt component attributions below for coverage and open items. |
| Nuitka runtime code compiled into the executable | 2.8.9 | `Apache-2.0`. Copyright 2025, Kay Hayen. [Runtime source](https://github.com/Nuitka/Nuitka/blob/2.8.9/nuitka/build/static_src/CompiledFunctionType.c) | `licenses/NUITKA-LICENSE.txt` from the installed distribution |

## Windows native components

These versions apply to the reviewed Windows build. The CPython binaries listed here match the installed Windows interpreter files. The CPython build pins supply the versions for libffi, bzip2 and liblzma. [CPython Windows dependency pins](https://github.com/python/cpython/blob/v3.13.17/PCbuild/get_externals.bat).

| Component | Observed version | License and source | Package notice |
| --- | --- | --- | --- |
| OpenSSL (`libcrypto-3.dll`) | 3.5.9 | [Apache-2.0](https://github.com/openssl/openssl/blob/openssl-3.5.9/LICENSE.txt) | `licenses/windows/OpenSSL-3.5.9.txt` |
| libffi (`libffi-8.dll`) | 3.4.4 | [MIT](https://github.com/libffi/libffi/blob/v3.4.4/LICENSE) | libffi notice in the Windows Python license |
| bzip2 (`_bz2.pyd`) | 1.0.8 | [bzip2-1.0.6](https://spdx.org/licenses/bzip2-1.0.6.html) | bzip2 1.0.8 notice in the Windows Python license |
| liblzma (`_lzma.pyd`) | 5.2.5 | [Public domain declaration for liblzma](https://github.com/python/cpython-source-deps/blob/xz-5.2.5/COPYING) | `licenses/windows/XZ-5.2.5.txt` |
| zlib (`python313.dll`) | 1.3.1 | [Zlib](https://github.com/python/cpython-source-deps/blob/zlib-1.3.1/LICENSE) | `licenses/windows/zlib-1.3.1.txt` |
| libmpdec (`_decimal.pyd`) | 4.0.0 | [BSD-2-Clause](https://github.com/python/cpython-source-deps/blob/mpdecimal-4.0.0/COPYRIGHT.txt) | `licenses/windows/libmpdec-4.0.0.txt` |
| SQLite (`sqlite3.dll`) | 3.50.4 | [Public domain dedication](https://www.sqlite.org/copyright.html) | Source dedication linked here |
| Microsoft Visual C++ runtime | 14.44.35211.0 and 14.51.36247.0 | Proprietary Microsoft terms. [Visual Studio 2022 REDIST list](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution) and [Visual Studio 2026 REDIST list](https://learn.microsoft.com/en-us/visualstudio/releases/2026/redistribution). | The checked DLL copies match their inputs. Confirm applicable terms for the copies from the Shiboken wheel, CPython and Visual Studio Build Tools. |

## Qt component attributions

The Windows build with PySide6 6.10.1 includes the Qt component notices under `licenses/qt-6.10.1/`. The inventory is in `docs/licenses/qt-6.10.1/README.md` in the source checkout and `licenses/qt-6.10.1/README.md` in the package. It identifies which components were observed in the binaries and which versions come from the Qt source tag. The JPEG plugin reports libjpeg-turbo 3.0.3, whereas the Qt 6.10.1 source attribution lists 3.1.2. The package includes the 3.0.3 attribution.

## Before distributing a standalone package

The build retains `compilation-report.xml` beside its intermediate files. Compare it and the package contents with the notices for that build. Confirm the unresolved versions, build options and remaining embedded-component notices with a matching wheel inventory or a reproducible Qt build. [Qt SBOM guidance](https://wiki.qt.io/SBOM).

For the LGPLv3 distribution route, identify the corresponding source and build inputs for the bundled libraries. Include the required notices and license texts. Verify that the application can use an interface-compatible modified library or provide the source and application code needed to recombine or relink it under section 4. Review the compiled PySide6 and Shiboken Python modules in that assessment. Distribution terms must permit library modification and reverse engineering for debugging those modifications. [LGPLv3 section 4](https://doc.qt.io/qt-6/lgpl.html).

The Windows runtime DLLs include `msvcp140.dll`, `msvcp140_1.dll`, `msvcp140_2.dll` and `msvcp140_codecvt_ids.dll` from Shiboken 6.10.1, three `msvcp140*.dll` files from the Visual Studio 2026 Build Tools redist directory, and `vcruntime140.dll` and `vcruntime140_1.dll` from CPython. Microsoft's REDIST lists condition redistribution on the applicable license terms. [Microsoft license directory](https://visualstudio.microsoft.com/license-terms/).

Repeat the inventory and match the included notices whenever the target platform, interpreter or toolchain changes. macOS and Linux package inventories remain unverified.
