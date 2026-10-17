"""Build a self-contained Maya distribution using only the standard library."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import hashlib


def build(destination=None):
    root = Path(__file__).resolve().parent
    destination = Path(destination) if destination else root / 'dist'
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / 'AbnormalMaya-0.1.0.zip'
    files = [root / 'install.py', root / 'AbnormalMaya.mod', root / 'README.md',
             root / 'tests' / 'test_core.py', root / 'tests' / 'maya_smoke.py']
    files += [p for p in (root / 'AbnormalMaya').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    with ZipFile(archive, 'w', ZIP_DEFLATED) as output:
        for source in sorted(files):
            output.write(source, 'AbnormalMaya-0.1.0/' + source.relative_to(root).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest + '  ' + archive.name + '\n')
    with ZipFile(archive) as check:
        assert check.testzip() is None, 'Archive integrity check failed'
        assert not any('__pycache__' in name or name.endswith('.pyc') for name in check.namelist())
    print('{} ({} files, SHA-256 {})'.format(archive, len(files), digest))
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='Output directory (default maya/dist)')
    build(parser.parse_args().output)
