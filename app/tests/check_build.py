"""Require both shipped entry pages to match a fresh build without editing them."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    scratch = Path('S:/Scratch/Temp')
    if not scratch.is_dir():
        scratch = Path(tempfile.gettempdir())
    with tempfile.TemporaryDirectory(prefix='cantos-build-', dir=scratch) as directory:
        candidate = Path(directory) / 'Cantos.html'
        subprocess.run([sys.executable, '-B', str(ROOT / 'app/source/build.py'),
                        '--out', str(candidate)], check=True, stdout=subprocess.DEVNULL)
        expected = candidate.read_bytes()
        for relative in ('app/Cantos.html', 'index.html'):
            if (ROOT / relative).read_bytes() != expected:
                raise SystemExit(f'{relative} differs from app/source; rebuild before release.')
        if (ROOT / 'app/Cantos.manifest.json').read_bytes() != candidate.with_suffix('.manifest.json').read_bytes():
            raise SystemExit('app/Cantos.manifest.json differs from the current source build.')
    print('PASS: app/Cantos.html and index.html match the current source build.')


if __name__ == '__main__':
    main()
