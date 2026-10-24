# Releasing

GitHub Actions (`.github/workflows/build.yml`) runs the tests and builds
Linux x86_64, Linux ARM64, Windows x64 and Windows ARM64 on every push and pull
request. The builds are attached to each run as artifacts.

To publish a release:

1. Set `__version__` in `mebuds/__init__.py` and commit it.
2. Tag that commit with the same version and push the tag:

   ```
   git tag v0.1.0
   git push origin v0.1.0
   ```

The workflow builds all four versions and creates a GitHub release with them
and generated release notes. It stops without publishing if the tag doesn't
match `__version__`.
