#!/bin/bash
# Verify one downloaded arm against the publisher checksums: the Hugging Face LFS object ids fetched with the
# file list, and the publisher manifest that the Cantos Hy4 package retained. Usage: verify.sh fp8|bf16 MANIFEST_NAME
ARM=$1
MANIFEST=$2
J=/mnt/w03data/Incoming/DataArray/Scratch/hy4-exact-arms-20261118
D=/dev/shm/hy4/$ARM
rm -f $J/meta/$ARM.VERIFIED $J/meta/$ARM.VERIFY-FAILED
cd $D || exit 2
ls *.safetensors *.json *.jinja | xargs -P 28 -n 1 sha256sum | sort -k2 > $J/meta/$ARM.sha256.observed.txt
python3 - "$ARM" "$MANIFEST" <<'EOF' > $J/meta/$ARM.verify.json
import hashlib, json, sys
arm, manifest_name = sys.argv[1:]
J = '/mnt/w03data/Incoming/DataArray/Scratch/hy4-exact-arms-20261118'
observed = {name: digest for digest, name in (line.split() for line in open(f'{J}/meta/{arm}.sha256.observed.txt'))}
tree = {e['path']: e for e in json.load(open(f'{J}/meta/{arm}.tree.json')) if e['type'] == 'file'}
manifest = json.load(open(f'{J}/cantos-hy4-flash/model-manifests/{manifest_name}.json'))
lfs_checked = lfs_bad = 0
for name, digest in observed.items():
    oid = (tree[name].get('lfs') or {}).get('oid')
    if oid:
        lfs_checked += 1
        lfs_bad += oid != digest
manifest_bad = [f['path'] for f in manifest['files'] if observed.get(f['path']) != f['sha256']]
local = {'schema': 'hy4-local-weights-manifest/1', 'model_id': manifest['model_id'], 'revision': manifest['revision'],
         'files': [{'path': n, 'sha256': observed[n]} for n in sorted(observed)]}
blob = json.dumps(local, indent=2, sort_keys=True).encode()
open(f'{J}/meta/{arm}.weights-manifest.json', 'wb').write(blob)
print(json.dumps({'arm': arm, 'files_hashed': len(observed), 'lfs_objects_checked': lfs_checked, 'lfs_mismatches': lfs_bad,
                  'cantos_manifest_files': len(manifest['files']), 'cantos_manifest_mismatches': manifest_bad,
                  'model_id': manifest['model_id'], 'revision': manifest['revision'],
                  'weights_manifest_sha256': hashlib.sha256(blob).hexdigest(),
                  'ok': lfs_bad == 0 and not manifest_bad and lfs_checked >= len(manifest['files'])}))
EOF
grep -q '"ok": true' $J/meta/$ARM.verify.json && cp $J/meta/$ARM.verify.json $J/meta/$ARM.VERIFIED || cp $J/meta/$ARM.verify.json $J/meta/$ARM.VERIFY-FAILED
