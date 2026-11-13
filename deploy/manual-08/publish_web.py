"""Publish only the files nginx needs outside the private /home/dev tree."""
import shutil
from pathlib import Path

ROOT = Path('/home/dev/gdds-gw-dms-08-v2')
WEB = Path('/var/lib/gdds08-web')


def main() -> None:
    if ROOT.resolve() != ROOT or WEB.exists() or WEB.is_symlink():
        raise ValueError('new, unredirected web root required')
    sources = (ROOT / 'frontend/dist', ROOT / 'source/deploy/manual-08/public')
    for source in sources:
        if source.resolve() != source or not source.is_dir() or any(path.is_symlink() for path in source.rglob('*')):
            raise ValueError('web source unavailable or redirected')
    WEB.mkdir(mode=0o755)
    (WEB / 'frontend').mkdir(mode=0o755)
    shutil.copytree(sources[0], WEB / 'frontend/dist')
    shutil.copytree(sources[1], WEB / 'a-public')


if __name__ == '__main__':
    main()
