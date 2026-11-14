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
modules = Core,Gui,Widgets
plugins = platforms,styles

[nuitka]
macos.permissions = NSAppleEventsUsageDescription:Open profile terminals using Terminal
mode = standalone
extra_args = --quiet --noinclude-qt-translations --include-package=profile_switch --assume-yes-for-downloads --output-filename=ai-profile-hub --include-data-files=LICENSE=LICENSE --include-data-files=THIRD_PARTY_NOTICES.md=THIRD_PARTY_NOTICES.md
