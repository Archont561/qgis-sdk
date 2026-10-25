"""Developer workflows: the ``test`` and ``dev`` commands' library half.

Everything here is QGIS-free and runs QGIS in *another* process: the install
is discovered (:mod:`.installs`), a plan says which process to start with
which environment (:mod:`.testrun`, :mod:`.dev`), and the command hands the
plan to its :class:`qgis_sdk_tools.cli.CliRuntime`. Import this package from a bare
interpreter; what needs Qt lives in the probe sources the plans write.
"""

from .installs import (
    QgisInstall,
    QgisSdkQgisNotFoundError,
    find_qgis_install,
    wants_headless,
)

__all__ = [
    "QgisInstall",
    "QgisSdkQgisNotFoundError",
    "find_qgis_install",
    "wants_headless",
]
