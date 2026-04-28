This file covers release behavior for this repository.

Do not cut a release unless I explicitly ask for a build, package, or release task.

If I ask for a Windows build, default to a local portable .exe unless I explicitly ask for an installer.

Before asking where release output should go, search for the previous successful build directory and reuse it if possible.

When publishing binaries, include a matching .sha256 sidecar for each shipped artifact using standard sha256sum output format.

For GitHub repos under ~/Projects/, every shipped binary should have a corresponding .sha256 file alongside it on release.

Prefer the existing naming pattern, output directory, and packaging method used by prior successful releases.

When the release task is complete, report the exact artifact names, exact output paths, and whether checksum files were generated.

If external dependencies are still required, state that clearly at the end of the release task.
