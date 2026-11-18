#!/bin/bash
# Download the two pinned Hy4 flash instruction payloads into W02 memory-backed storage.
# FP8 first (smaller), then BF16. Resumable; writes a marker per arm once every file has its listed size.
set -u
D=/dev/shm/hy4
J=/mnt/w03data/Incoming/DataArray/Scratch/hy4-exact-arms-20261118
mkdir -p "$D" "$J/meta"

one() {  # url dest size
  local url=$1 dest=$2 size=$3
  [ -f "$dest" ] && [ "$(stat -c %s "$dest")" = "$size" ] && return 0
  curl -sSL --fail --retry 30 --retry-delay 5 --retry-all-errors -C - -o "$dest" "$url" || echo "FAILED $dest" >> "$J/meta/download.errors"
}
export -f one
export J

arm() {  # name repo revision
  local name=$1 repo=$2 rev=$3
  mkdir -p "$D/$name"
  curl -sSL --fail --max-time 60 "https://huggingface.co/api/models/$repo/tree/$rev?recursive=true" -o "$J/meta/$name.tree.json" || return 1
  python3 - "$J/meta/$name.tree.json" "$repo" "$rev" "$D/$name" > "$J/meta/$name.urls" <<'EOF'
import json, sys
tree, repo, rev, dest = sys.argv[1:]
files = [e for e in json.load(open(tree)) if e['type'] == 'file' and '/' not in e['path']
         and e['path'].rsplit('.', 1)[-1] in ('safetensors', 'json', 'jinja')]
for e in sorted(files, key=lambda e: e['size']):
    print("https://huggingface.co/%s/resolve/%s/%s %s/%s %d" % (repo, rev, e['path'], dest, e['path'], e['size']))
EOF
  date -u +%FT%TZ > "$J/meta/$name.download.started"
  xargs -P 4 -L 1 bash -c 'one "$0" "$1" "$2"' < "$J/meta/$name.urls"
  local bad=0
  while read -r url dest size; do
    [ -f "$dest" ] && [ "$(stat -c %s "$dest")" = "$size" ] || { bad=$((bad+1)); echo "SIZE $dest" >> "$J/meta/download.errors"; }
  done < "$J/meta/$name.urls"
  date -u +%FT%TZ > "$J/meta/$name.download.finished"
  echo "files=$(wc -l < "$J/meta/$name.urls") bad=$bad bytes=$(du -sb "$D/$name" | cut -f1)" > "$J/meta/$name.DOWNLOADED"
}

arm fp8 tencent/Hy4-flash-FP8 003107fa248f5892064ab1c43af0a7003dd68c9b
arm bf16 tencent/Hy4-flash d88c9dfd96ba4f2e6b92adba0b8e8f1c8696f959
