# Third-party notices

AI Profile Hub source is licensed under the MIT license in `LICENSE`. The standalone package includes components with their own terms. Keep the package's `LICENSE`, this notice and `licenses/` together.

## Standalone runtime

The Windows inventory below was checked against the Python 3.13.17, PySide6 6.10.1 and Nuitka 2.8.9 build on 2026-11-14. Exact native dependencies can vary by platform, interpreter and compiler.

| Component | Observed version | License and source | Package notice |
| --- | --- | --- | --- |
| CPython and its standard library | 3.13.17 | [PSF-2.0 and historical terms](https://github.com/python/cpython/blob/v3.13.17/LICENSE) | `licenses/PYTHON-LICENSE.txt` from the interpreter used to build |
| PySide6 bindings and shiboken6 runtime | 6.10.1 | Wheel metadata declares `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. Qt also offers commercial terms. [Qt for Python source](https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.10.1) | LGPLv3 and GPLv3 texts plus wheel-provided notices under `licenses/` |
| Qt Core, GUI, Network, Widgets, SVG and PDF, plus platform, style, image, icon and TLS plugins | 6.10.1 | Qt's LGPLv3 option applies to the reviewed module sources. Embedded components retain distinct terms. See the [Qt 6.10.1 source release](https://download.qt.io/official_releases/qt/6.10/6.10.1/submodules/) and [Qt third-party attributions](https://doc.qt.io/qt-6.10/licenses-used-in-qt.html). | LGPLv3 and GPLv3 texts in `licenses/`. Verify exact embedded notices against the matching Qt build before distributing. |
| Nuitka runtime code compiled into the executable | 2.8.9 | `Apache-2.0`. [Runtime source](https://github.com/Nuitka/Nuitka/blob/2.8.9/nuitka/build/static_src/CompiledFunctionType.c) | `licenses/NUITKA-LICENSE.txt` from the installed distribution |
| PySide deployment icon embedded by the deployment tool | 6.10.1 | From the PySide6 Essentials wheel. Asset-specific license terms remain unverified. | Verify the asset terms or replace the icon before distributing. |

## Windows native components

These versions apply to the reviewed CPython 3.13.17 Windows build. The matching supplemental texts are included for that interpreter version. Check the actual components and obtain matching notices if using a different interpreter or distribution. [CPython Windows dependency pins](https://github.com/python/cpython/blob/v3.13.17/PCbuild/get_externals.bat).

| Component | Observed version | License and source | Package notice |
| --- | --- | --- | --- |
| OpenSSL | 3.5.9 | [Apache-2.0](https://github.com/openssl/openssl/blob/openssl-3.5.9/LICENSE.txt) | `licenses/windows/OpenSSL-3.5.9.txt` |
| libffi | 3.4.4 | [MIT](https://github.com/libffi/libffi/blob/v3.4.4/LICENSE) | libffi notice in the Windows Python license |
| bzip2 | 1.0.8 | [bzip2-1.0.6 license text retained in release 1.0.8](https://gitlab.com/bzip2/bzip2/-/blob/bzip2-1.0.8/LICENSE) | bzip2 notice in the Windows Python license |
| liblzma | 5.2.5 | [Public domain declaration for liblzma](https://github.com/python/cpython-source-deps/blob/xz-5.2.5/COPYING) | `licenses/windows/XZ-5.2.5.txt` |
| zlib | 1.3.1 | [Zlib](https://github.com/python/cpython-source-deps/blob/zlib-1.3.1/LICENSE) | `licenses/windows/zlib-1.3.1.txt` |
| libmpdec | 2.5.1 | [BSD-2-Clause](https://github.com/python/cpython/blob/v3.13.17/Modules/_decimal/libmpdec/mpdecimal.h) | `licenses/windows/libmpdec-2.5.1.txt` |
| SQLite | 3.50.4 | [Public domain dedication](https://www.sqlite.org/copyright.html) | Source dedication linked here |
| Microsoft Visual C++ runtime | 14.44.35211.0 and 14.51.36247.0 | Proprietary Microsoft terms. [Redistribution guidance](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files) | Check the applicable redistribution terms and DLL list for the toolchain. |

## Qt component attributions

The Windows build with PySide6 6.10.1 includes the Qt component notices under `licenses/qt-6.10.1/`. The inventory is in `docs/licenses/qt-6.10.1/README.md` in the source checkout and `licenses/qt-6.10.1/README.md` in the package. It identifies which components were observed in the binaries and which versions come from the Qt source tag. The JPEG plugin reports libjpeg-turbo 3.0.3, whereas the Qt 6.10.1 source attribution lists 3.1.2. The package includes the 3.0.3 attribution.

## Before distributing a standalone package

The build retains `compilation-report.xml` beside its intermediate files. Compare it and the package contents with the notices for that build. The reviewed wheels did not contain an SBOM or the Qt PDF credits generated from the build configuration. Confirm the unresolved versions, build options and remaining embedded-component notices with a matching wheel inventory or a reproducible Qt build. [Qt SBOM guidance](https://wiki.qt.io/SBOM).

For the LGPLv3 distribution route, review the corresponding library source, the license and copyright notices, and the user's ability to replace and debug the linked LGPL libraries. Dynamic linking alone establishes only part of that review. [LGPLv3 text](https://www.gnu.org/licenses/lgpl-3.0.en.html).

The Windows inventory provides a starting point for release review. The native inventories for macOS and Linux still need to be checked against their actual packages.
