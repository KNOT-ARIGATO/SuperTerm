# Third-party software

SuperTerm.exe bundles the following open-source components. Their licences
apply to those components; the source code of each is available from the
project links below.

| Component | Licence | Source |
|---|---|---|
| Python | PSF License | https://www.python.org |
| Qt / PySide6 | LGPL-3.0 | https://www.qt.io · https://pypi.org/project/PySide6/ |
| pyte (terminal emulation) | LGPL-3.0 | https://github.com/selectel/pyte |
| wcwidth | MIT | https://github.com/jquast/wcwidth |
| pyserial | BSD-3-Clause | https://github.com/pyserial/pyserial |
| paramiko | LGPL-2.1 | https://github.com/paramiko/paramiko |
| certifi (Mozilla CA bundle) | MPL-2.0 | https://github.com/certifi/python-certifi |
| PyInstaller bootloader | GPL-2.0 with bootloader exception | https://pyinstaller.org |

The LGPL components are used unmodified as separate libraries. To rebuild
SuperTerm with a different version of them, install that version and run
`build.ps1` (see README).

SuperTerm does not contain code from Tera Term; its terminal behaviour is
modelled after Tera Term's defaults.
