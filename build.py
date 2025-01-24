import argparse
import os
import platform
import subprocess
import sys
import tarfile
import zipfile
from importlib.util import find_spec

if not find_spec("PyInstaller"):
    print(
        "[ERROR]: Please install PyInstaller module first.",
        "If you have the module installed,",
        "Please check if you forgetting to activate the virtualenv.",
        sep="\n",
    )
    sys.exit(1)

try:
    import QMDown
    from QMDown import __main__
except Exception:
    print(
        "[ERROR]: Please install dependencies required by QMDown.",
        "If you have the dependencies installed,",
        "Please check if you forgetting to activate the virtualenv.",
        sep="\n",
    )
    sys.exit(1)


def build(filename: str, is_test: bool):
    os.environ["build"] = "T" if is_test else "R"

    print(f"QMDown version: {QMDown.__version__}")
    filename = filename or "QMDown"

    popen = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--collect-data",
            "qqmusic_api",
            "--onefile",
            "--strip",
            "--optimize=2",
            "--name",
            filename,
            __main__.__file__,
        ]
    )

    print("PyInstaller process started, PID: " + str(popen.pid))
    print("Please wait for a while...")
    popen.wait()

    if popen.returncode != 0:
        print(
            f"[ERROR]: PyInstaller build with code {popen.returncode}.",
            "Please check the output log,",
            "this may inculde errors or warnings.",
            sep="\n",
        )
        sys.exit(popen.returncode)
    else:
        print("[SUCCESS]: PyInstaller build success.")
        filepath = os.path.join(os.getcwd(), "dist", os.listdir(os.path.join(os.getcwd(), "dist"))[0])
        print(f"FilePath: {filepath}")
        return filepath


def compress(filename: str, filepath: str):
    system = platform.system().lower()
    arch = platform.architecture()[0].replace("bit", "")
    filename = f"{filename or 'QMDown'}_{QMDown.__version__}_{system}_{arch}"
    if system == "windows":
        path = os.path.join(
            os.getcwd(),
            "dist",
            filename + ".zip",
        )

        with zipfile.ZipFile(
            path,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as zipf:
            zipf.write(filepath, os.path.basename(filepath))
    else:
        path = os.path.join(
            os.getcwd(),
            "dist",
            filename + ".tar.gz",
        )
        with tarfile.open(
            path,
            "w:gz",
            format=tarfile.GNU_FORMAT,
        ) as tarf:
            tarf.add(filepath, os.path.basename(filepath))

    github_env = os.getenv("GITHUB_ENV", None)

    if github_env:
        with open(github_env, "a") as f:
            f.write(f"dist_name={path}\n")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--release", action="store_true", help="Build release executable.")
    group.add_argument("--test", action="store_true", help="Build test executable.")
    group.add_argument("--no-compress", action="store_true", help="Build test executable.")
    group.add_argument("-f", "--filename", type=str, help="Specify the fileName of the executable.")

    args = parser.parse_args()
    path = build(args.filename, args.test)

    if not args.no_compress:
        print(f"Compressing {path}")
        compress(args.filename, path)
        print("Compression completed")


if __name__ == "__main__":
    main()
