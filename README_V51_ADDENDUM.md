# V51 Addendum

V51 adds Windows deployment support and application data initialization. Run `install_windows.bat` on a Windows machine with Python installed to install requirements and build a windowed executable. `launch_windows.bat` launches a built executable when available or falls back to Python.

The app stores durable application data under the platform user-data directory rather than beside the executable where possible. Use the V51 Installation & Diagnostics tab to initialize directories and verify dependencies/write access.
