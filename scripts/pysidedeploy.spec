[app]
title = AI Profile Hub
project_dir = .
input_file = main.py
exec_directory = dist
project_file =
icon =

[python]
python_path =
packages = Nuitka==2.8.9,ordered-set==4.1.0,zstandard==0.25.0

[qt]
qml_files =
excluded_qml_plugins =
modules = Core,Gui,Network,Widgets
plugins = platforms,styles

[nuitka]
macos.permissions = NSAppleEventsUsageDescription:Open profile terminals using Terminal
mode = standalone
extra_args = --quiet --noinclude-qt-translations --noinclude-dlls=*qpdf.* --noinclude-dlls=*[Qq]t6[Pp]df.* --noinclude-dlls=*/QtPdf.framework/* --include-package=profile_switch --assume-yes-for-downloads --include-data-files=LICENSE=LICENSE --include-data-files=THIRD_PARTY_NOTICES.md=THIRD_PARTY_NOTICES.md --include-data-files=profile_switch/assets/app-icon.svg=profile_switch/assets/app-icon.svg
