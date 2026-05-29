This file covers release behavior for this repository.

Do not cut a release unless I explicitly ask for a build, package, or release task.
If I ask for a Windows build, default to a local portable `.exe` unless I explicitly ask for an installer.
Before asking where release output should go, search for the previous successful build directory and reuse it if possible.

### Artifact Checksums
- When publishing binaries, generate a matching `.sha256` sidecar for each shipped artifact.
- Use direct shell redirection, for example: `sha256sum build.exe > build.exe.sha256`.
- Do not manually inspect checksum files unless verification is explicitly requested.

### Packaging Discipline
- Prefer the existing naming pattern, output directory, and packaging method used by prior successful releases.
- Do not introduce new packaging methods unless the repo already defines them.
- Do not restructure build outputs during a release task.
- Follow the exact packaging flow used in prior successful builds.

### Completion
- When the release task is complete, report the exact artifact names, exact output paths, and whether checksum files were generated.
- If external dependencies are still required, state that clearly at the end of the release task.
