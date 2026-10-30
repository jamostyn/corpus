# Third-party notices

Corpus is licensed under the GNU AGPL v3.0 (see `LICENSE`). The built
app bundles the components below. Licences were read from each
package's installed metadata on 2026-10-28 (macOS build environment);
versions are those the current build uses.

## Why Corpus is AGPL

**PyMuPDF** (PDF reading) is dual-licensed: GNU AGPL v3.0, or a
commercial licence from Artifex. Corpus uses it under the AGPL, which
is why Corpus itself is AGPL and its source is public.

## Bundled in every build

| Component | Version | Licence |
|---|---|---|
| PyMuPDF | 1.28.2 | AGPL-3.0 (or Artifex commercial) |
| PDF.js (Mozilla; `src/vendor/pdfjs/`, licence in `src/vendor/pdfjs/LICENSE`) | 4.4.168 | Apache-2.0 |
| citeproc-js (Frank Bennett; `src/vendor/citeproc/citeproc.js`, licence in its header; last line changed so it loads as a browser script) | 2.4.63 | AGPL-3.0-or-later (or CPAL-1.0) |
| CSL styles: APA 7th, MLA 9th, Chicago author-date, Cite Them Right (Harvard), NLM/Vancouver, IEEE (Citation Style Language project; `src/vendor/citeproc/styles/`, authors in each file) | as of 2026-10-29 | CC BY-SA 3.0 |
| CSL locales en-US, en-GB (Citation Style Language project; `src/vendor/citeproc/locales/`) | as of 2026-10-29 | CC BY-SA 3.0 |
| Python (the interpreter, bundled by PyInstaller) | 3.14 | PSF-2.0 |
| Flask | 3.1.3 | BSD-3-Clause |
| Werkzeug | 3.1.8 | BSD-3-Clause |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| itsdangerous | 2.2.0 | BSD-3-Clause |
| click | 8.4.2 | BSD-3-Clause |
| blinker | 1.9.0 | MIT |
| pywebview | 6.2.1 | BSD-3-Clause |
| bottle (pywebview dependency) | 0.13.4 | MIT |
| proxy_tools (pywebview dependency) | 0.1.0 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| requests | 2.34.2 | Apache-2.0 |
| urllib3 | 2.7.0 | MIT |
| idna | 3.18 | BSD-3-Clause |
| charset-normalizer | 3.4.9 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| PyYAML | 6.0.3 | MIT |
| keyring | 25.7.0 | MIT |
| jaraco.classes / jaraco.functools / jaraco.context | 3.4.0 / 4.6.0 / 6.1.2 | MIT |
| more-itertools | 11.1.0 | MIT |

## macOS build only

| Component | Version | Licence |
|---|---|---|
| pyobjc-core, pyobjc-framework-Cocoa / Quartz / WebKit / Security / UniformTypeIdentifiers | 12.2.1 | MIT |

## Windows build only

pywebview installs **pythonnet** and keyring installs **pywin32-ctypes**
on Windows. They are not installed in the macOS environment these
licences were read from, so their licences are not verified here; check
them in the Windows build environment (`pip show pythonnet
pywin32-ctypes`).

## Build tool (not bundled as a component)

**PyInstaller** 6.22.1 packages the app. It is GPL-2.0-or-later with an
exception that permits distributing apps built with it under any
licence.

The full licence texts are in each package's distribution files
(`pip show -f <package>`), and in the bundled app.
