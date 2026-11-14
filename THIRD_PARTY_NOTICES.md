# Third-party notices

AI Profile Hub is licensed under the MIT license in LICENSE.

The standalone desktop distribution includes Python, PySide6, Shiboken6 and the Qt libraries selected by the deployment tool. PySide6 and Shiboken6 are distributed under LGPLv3/GPLv3 or commercial terms; Qt modules retain their respective licenses. This project uses the open-source distributions and dynamically linked Qt libraries.

- Python license and sources: https://www.python.org/downloads/source/
- Qt for Python licenses and sources: https://code.qt.io/cgit/pyside/pyside-setup.git/
- Qt 6.10.1 sources: https://download.qt.io/archive/qt/6.10/6.10.1/
- Qt license information: https://doc.qt.io/qt-6/licensing.html

The build copies the installed PySide6/Shiboken6 license texts into the package's licenses directory. Included libraries must remain replaceable under their license terms. Nuitka is a build tool licensed under Apache-2.0; it does not replace the licenses of bundled components.

The LGPLv3, GPLv3 and Qt GPL exception texts in docs/licenses are copied verbatim from the Qt 6.10.1 source tree: https://github.com/qt/qtbase/tree/v6.10.1/LICENSES . They are included with every standalone package along with the installed distribution notices.
