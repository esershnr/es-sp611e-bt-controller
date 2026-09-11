"""Allow `python -m sp611e_cli` and serve as the PyInstaller entry point."""

from sp611e_cli.cli import main

if __name__ == "__main__":
    main()
