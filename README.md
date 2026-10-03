# nUSA Wiki — static edition

A static export of nUSA Wiki, preserving the MediaWiki Vector 2022 reading layout,
articles, categories, citations, uploaded documents, and images. Search and article
previews run in the browser. Editing, accounts, and revision history remain on the
source MediaWiki installation.

## Update and publish

Start the source wiki on its usual local port, then run **Export Wiki.cmd**.
Review the export using a local HTTP server, then run **Publish Wiki.cmd**.
Successful pushes to `main` publish the `docs` directory through GitHub Pages.

Install export/check dependencies with `python -m pip install -r requirements.txt`.
The source wiki database, private research archives, and server configuration are
never copied. This repository has its own Git history and account credentials.

## Publication checks

The security checker allows only the website and the listed export/publish tools.
It rejects computer paths, encoded paths, private network URLs in the website,
credential patterns, unexpected files, unapproved scripts, missing local assets,
image/PDF metadata, and oversized uploads. Git hooks check staged files before
commit and committed files before push. Local inventories and reports are stored
in the ignored `.local` directory.

`AGENTS.md` and `.local` are ignored and must never be published. The only permitted
push destination is the dedicated repository owned by `adsuhi283dm9a8znlkxc`.
Credentials are configured locally; they are never committed.

The automated scanner does not detect arbitrary sensitive text inside an image.
Review new image and document uploads visually before publishing future exports.
