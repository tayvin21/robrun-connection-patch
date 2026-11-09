# Bundled dependencies

- **CPython 3.14.10, Windows x64 embedded runtime**: [official download](https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip). License: `runtime/LICENSE.txt`. The `_pth` search-path configuration additionally includes the adjacent patch source directory. Vendor executables and libraries are unmodified.
- **Wintun 0.14.1, amd64**: [official download](https://www.wintun.net/builds/wintun-0.14.1.zip). License: `WINTUN-LICENSE.txt`. Used only via its public API. The vendor-signed DLL is unmodified.

Archive SHA-256 values and packaging steps are in `build_release.py`. These dependencies are bundled only in release ZIPs. No game binaries or decompiled game source are distributed.
