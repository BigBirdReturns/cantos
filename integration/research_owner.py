"""Select the native ResearchCore owner for a research packet by its declared version.

Packets written by Research Desk 1.0.0 keep their original owner, the script embedded in
research-desk/app.html, so every computation identity retained before this helper existed
is unchanged. Packets declaring a later workspace version (1.0.1, 1.0.2) are read through
app/source/research-core.js, the 1.0.2 owner, which replays 1.0.0, 1.0.1 and 1.0.2 journals.
The chosen owner's bytes enter the computation identity; nothing here grants standing.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DESK_APP = ROOT / 'research-desk/app.html'
CORE = ROOT / 'app/source/research-core.js'
DESK_VERSION = '1.0.0'
CORE_VERSIONS = ('1.0.1', '1.0.2')


def declared_version(packet_path):
    """The workspace version the packet declares, read without verifying the journal."""
    with Path(packet_path).open('rb') as stream:
        head = json.loads(stream.read())
    if not isinstance(head, dict) or not isinstance(head.get('workspace'), dict):
        raise ValueError('Research packet needs a workspace object')
    version = head['workspace'].get('version')
    if not isinstance(version, str):
        raise ValueError('Research packet needs a declared workspace version')
    return version


def owner_for(packet_path):
    """Return {'path', 'label', 'version', 'sha256'} for the owner that reads this packet."""
    version = declared_version(packet_path)
    if version == DESK_VERSION:
        path, label = DESK_APP, 'research-desk/app.html'
    elif version in CORE_VERSIONS:
        path, label = CORE, 'app/source/research-core.js'
    else:
        raise ValueError('Unsupported research packet version: ' + version)
    return {'path': path, 'label': label, 'version': version,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
