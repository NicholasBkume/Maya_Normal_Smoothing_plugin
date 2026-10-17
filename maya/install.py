"""Run with exec(open('/path/to/maya/install.py').read()) inside Maya.

Copy this entire maya directory somewhere permanent first. The installer adds
one .mod file to Maya's user modules folder, and opens the panel immediately.
It never copies over existing installation files without an explicit match.
"""
from pathlib import Path
import sys


def install(root):
    from maya import cmds
    root = Path(root).resolve()
    package = root / 'AbnormalMaya'
    if not (package / 'scripts' / 'abnormal_maya' / '__init__.py').is_file():
        raise ValueError('Choose the maya distribution directory containing AbnormalMaya')
    modules = Path(cmds.internalVar(userAppDir=True)) / 'modules'
    modules.mkdir(parents=True, exist_ok=True)
    destination = modules / 'AbnormalMaya.mod'
    content = '+ AbnormalMaya 0.1.0 {}\n'.format(package.as_posix())
    if destination.exists() and destination.read_text(encoding='utf-8') != content:
        raise RuntimeError('An AbnormalMaya.mod already exists at {}. Review it before replacing it.'.format(destination))
    destination.write_text(content, encoding='utf-8')
    scripts = str(package / 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import abnormal_maya
    abnormal_maya.show()
    print('Abnormal Maya installed. Launch with: import abnormal_maya; abnormal_maya.show()')


# exec(open(...).read()) does not reliably set __file__; call install explicitly.
# Example:
# exec(compile(open('/path/to/maya/install.py').read(), '/path/to/maya/install.py', 'exec'))
# install('/path/to/maya')


def onMayaDroppedPythonFile(*args):
    install(Path(__file__).resolve().parent)
