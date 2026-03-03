import asyncio
import logging
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# Map import names that differ from pip package names
_PIP_NAME_MAP: dict[str, str] = {
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "skimage": "scikit-image",
    "Crypto": "pycryptodome",
    "serial": "pyserial",
    "usaddress": "usaddress",
    "attr": "attrs",
    "dateutil": "python-dateutil",
    "gi": "PyGObject",
    "lxml": "lxml",
    "wx": "wxPython",
    "google": "google-api-python-client",
    "googleapiclient": "google-api-python-client",
    "Bio": "biopython",
    "cv": "opencv-python",
    "fitz": "PyMuPDF",
    "magic": "python-magic",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "jose": "python-jose",
    "jwt": "PyJWT",
    "Levenshtein": "python-Levenshtein",
    "rapidfuzz": "rapidfuzz",
    "geopy": "geopy",
    "shapely": "shapely",
    "geopandas": "geopandas",
    "fiona": "fiona",
    "rasterio": "rasterio",
    "netCDF4": "netCDF4",
    "xarray": "xarray",
    "dask": "dask",
    "tables": "tables",
    "h5py": "h5py",
    "astropy": "astropy",
    "healpy": "healpy",
    "statsmodels": "statsmodels",
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
    "catboost": "catboost",
    "tf": "tensorflow",
    "tensorflow": "tensorflow",
    "torch": "torch",
    "transformers": "transformers",
    "langchain": "langchain",
    "openai": "openai",
    "anthropic": "anthropic",
    "tiktoken": "tiktoken",
    "faiss": "faiss-cpu",
    "chromadb": "chromadb",
    "pinecone": "pinecone-client",
    "weaviate": "weaviate-client",
    "redis": "redis",
    "pymongo": "pymongo",
    "psycopg2": "psycopg2-binary",
    "MySQLdb": "mysqlclient",
    "pymysql": "pymysql",
    "sqlmodel": "sqlmodel",
    "pydantic": "pydantic",
    "fastapi": "fastapi",
    "flask": "flask",
    "starlette": "starlette",
    "httpx": "httpx",
    "aiohttp": "aiohttp",
    "websockets": "websockets",
    "paramiko": "paramiko",
    "fabric": "fabric",
}

# Maximum number of install-then-retry cycles
_MAX_INSTALL_RETRIES = 3


def _extract_missing_modules(stderr: str) -> list[str]:
    """Return pip package names for any ModuleNotFoundError / ImportError in stderr."""
    pattern = re.compile(
        r"(?:ModuleNotFoundError|ImportError):\s*No module named ['\"]?([^'\";\s]+)['\"]?",
        re.IGNORECASE,
    )
    seen: list[str] = []
    for match in pattern.finditer(stderr):
        raw = match.group(1).strip().split(".")[0]  # top-level package only
        pip_name = _PIP_NAME_MAP.get(raw, raw)
        if pip_name not in seen:
            seen.append(pip_name)
    return seen


# Standard library modules that should never be pip-installed
_STDLIB_MODULES = {
    "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit", "base64",
    "binascii", "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb",
    "chunk", "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "csv", "ctypes", "curses",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis", "distutils",
    "doctest", "email", "encodings", "enum", "errno", "faulthandler", "fcntl",
    "filecmp", "fileinput", "fnmatch", "fractions", "ftplib", "functools",
    "gc", "getopt", "getpass", "gettext", "glob", "grp", "gzip", "hashlib",
    "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr", "imp",
    "importlib", "inspect", "io", "ipaddress", "itertools", "json", "keyword",
    "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox", "mailcap",
    "marshal", "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
    "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os",
    "ossaudiodev", "pathlib", "pdb", "pickle", "pickletools", "pipes",
    "pkgutil", "platform", "plistlib", "poplib", "posix", "posixpath",
    "pprint", "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
    "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site", "smtpd",
    "smtplib", "sndhdr", "socket", "socketserver", "sqlite3", "ssl", "stat",
    "statistics", "string", "stringprep", "struct", "subprocess", "sunau",
    "symtable", "sys", "sysconfig", "syslog", "tabnanny", "tarfile", "telnetlib",
    "tempfile", "termios", "test", "textwrap", "threading", "time", "timeit",
    "tkinter", "token", "tokenize", "trace", "traceback", "tracemalloc",
    "tty", "turtle", "turtledemo", "types", "typing", "unicodedata",
    "unittest", "urllib", "uu", "uuid", "venv", "warnings", "wave",
    "weakref", "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib",
    "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
    "_thread", "__future__",
}


_ALLOWED_PACKAGES = set(_PIP_NAME_MAP.values()) | {
    "numpy", "pandas", "matplotlib", "scipy", "seaborn", "plotly",
    "requests", "beautifulsoup4", "lxml", "openpyxl", "xlsxwriter",
    "pillow", "scikit-learn", "sympy", "networkx",
}


def _validate_packages(packages: list[str]) -> tuple[list[str], list[str]]:
    """Filter packages to only those in the allowlist."""
    normalized_allowlist = {a.lower().replace("-", "_") for a in _ALLOWED_PACKAGES} | {a.lower() for a in _ALLOWED_PACKAGES}
    allowed = []
    blocked = []
    for p in packages:
        if p.lower().replace("-", "_") in normalized_allowlist or p.lower() in normalized_allowlist:
            allowed.append(p)
        else:
            blocked.append(p)
    return allowed, blocked


def _prescan_imports(code: str) -> list[str]:
    """Pre-scan code for imports and # pip: hints. Return pip packages to install."""
    packages: list[str] = []
    seen: set[str] = set()

    # Extract `# pip: package-name` comments
    for match in re.finditer(r"#\s*pip:\s*(\S+)", code):
        pkg = match.group(1).strip()
        if pkg not in seen:
            seen.add(pkg)
            packages.append(pkg)

    # Extract import statements
    for match in re.finditer(
        r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)", code, re.MULTILINE
    ):
        mod = match.group(1)
        if mod in _STDLIB_MODULES:
            continue
        pip_name = _PIP_NAME_MAP.get(mod, mod)
        if pip_name not in seen:
            seen.add(pip_name)
            packages.append(pip_name)

    return packages


def _is_installed(package: str) -> bool:
    """Check if a package is already importable."""
    import importlib.util
    reverse_map = {v: k for k, v in _PIP_NAME_MAP.items()}
    import_name = reverse_map.get(package, package).replace("-", "_")
    return importlib.util.find_spec(import_name) is not None


async def _install_packages(
    packages: list[str],
    log_callback: Callable[[str, str], Awaitable[None]] | None,
) -> bool:
    """pip-install packages in the current venv. Returns True on success."""
    if log_callback:
        await log_callback("info", f"Auto-installing missing packages: {', '.join(packages)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", *packages,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err_bytes = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode == 0:
            if log_callback:
                await log_callback("info", f"Installed: {', '.join(packages)}")
            return True
        err = err_bytes.decode("utf-8", errors="replace")
        if log_callback:
            await log_callback("error", f"pip install failed: {err[:300]}")
        return False
    except Exception as e:
        if log_callback:
            await log_callback("error", f"pip install error: {e}")
        return False

# Base directory for storing artifacts
ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts"


def extract_code_blocks(markdown: str) -> list[dict]:
    """Extract fenced code blocks from markdown output.

    Returns list of {language, code} dicts.
    Matches ```python and ```py blocks.
    """
    pattern = r"```(?:python|py)\s*\n(.*?)```"
    matches = re.findall(pattern, markdown, re.DOTALL)
    return [{"language": "python", "code": match.strip()} for match in matches]


def _prepare_code(code: str, work_dir: str) -> str:
    """Prepare Python code for safe execution.

    - Sets matplotlib to non-interactive Agg backend
    - Replaces plt.show() with plt.savefig()
    """
    lines = []
    # Inject matplotlib backend switch at the very top
    lines.append("import matplotlib; matplotlib.use('Agg')")
    lines.append("")

    plot_counter = 0
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped == "plt.show()" or stripped == "plt.show( )":
            # Replace with savefig
            indent = line[: len(line) - len(line.lstrip())]
            save_path = os.path.join(work_dir, f"output_plot_{plot_counter}.png")
            lines.append(
                f"{indent}plt.savefig(r'{save_path}', dpi=150, bbox_inches='tight')"
            )
            lines.append(f"{indent}plt.close()")
            plot_counter += 1
        elif "plt.show()" in stripped:
            # Handle inline plt.show() in more complex lines
            indent = line[: len(line) - len(line.lstrip())]
            save_path = os.path.join(work_dir, f"output_plot_{plot_counter}.png")
            lines.append(
                f"{indent}plt.savefig(r'{save_path}', dpi=150, bbox_inches='tight')"
            )
            lines.append(f"{indent}plt.close()")
            plot_counter += 1
        else:
            lines.append(line)

    return "\n".join(lines)


ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".svg", ".gif",
    ".csv", ".json", ".html", ".txt",
    ".pdf", ".xlsx", ".md",
    # Scientific data formats
    ".fits", ".hdf5", ".h5", ".nc", ".npy", ".npz",
    ".parquet", ".feather", ".pkl",
}


def _detect_mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _detect_artifact_type(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type in ("text/markdown", "text/x-markdown"):
        return "markdown"
    return "file"


# Sensitive environment variables to strip from subprocess environments
_SENSITIVE_ENV_VARS = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "DATABASE_URL"}


def _clean_env() -> dict[str, str]:
    """Build a clean environment that strips sensitive variables."""
    return {k: v for k, v in os.environ.items() if k not in _SENSITIVE_ENV_VARS}


async def _run_script(
    script_path: Path,
    work_dir: Path,
    timeout: int,
    log_callback: Callable[[str, str], Awaitable[None]] | None,
) -> tuple[str, str, int]:
    """Execute script_path in a subprocess. Returns (stdout, stderr, exit_code)."""
    try:
        clean_env = _clean_env()
        # On Linux, apply resource limits to sandbox the subprocess
        preexec = None
        if sys.platform == "linux":
            import resource

            def _set_limits():
                # Limit CPU time to timeout + 10s grace
                resource.setrlimit(resource.RLIMIT_CPU, (timeout + 10, timeout + 10))
                # Limit virtual memory to 2GB
                resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
                # Limit number of child processes to 64
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))

            preexec = _set_limits
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=clean_env,
            **({"preexec_fn": preexec} if preexec else {}),
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            if log_callback:
                await log_callback("error", f"Code execution timed out after {timeout}s")
            return "", f"Execution timed out after {timeout} seconds", -1

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = process.returncode or 0

        if log_callback:
            if stdout.strip():
                for line in stdout.strip().split("\n")[:50]:
                    await log_callback("info", line)
            if stderr.strip():
                for line in stderr.strip().split("\n")[:20]:
                    await log_callback("error", line)
            if exit_code == 0:
                await log_callback("info", "Code execution completed successfully")
            else:
                await log_callback("error", f"Code exited with code {exit_code}")

        return stdout, stderr, exit_code

    except Exception as e:
        if log_callback:
            await log_callback("error", f"Execution error: {e}")
        return "", str(e), -1


async def run_code(
    task_id: str,
    action_id: str,
    code: str,
    log_callback: Callable[[str, str], Awaitable[None]] | None = None,
    timeout: int = 60,
) -> dict:
    """Execute Python code in a subprocess and capture outputs.

    Args:
        task_id: The task this execution belongs to
        action_id: The action this execution belongs to
        code: Python source code to execute
        log_callback: Optional async callback for streaming log lines
        timeout: Execution timeout in seconds

    Returns:
        {stdout, stderr, exit_code, files: [{path, filename, mime_type, size, type}]}
    """
    # Create work directory for this execution
    work_dir = ARTIFACTS_DIR / action_id / task_id
    # Validate path is within ARTIFACTS_DIR to prevent traversal
    if not str(work_dir.resolve()).startswith(str(ARTIFACTS_DIR.resolve())):
        raise ValueError(f"Invalid work directory: path traversal detected")
    work_dir.mkdir(parents=True, exist_ok=True)

    # Clean up old generated files from previous runs
    for f in work_dir.iterdir():
        if f.suffix in ALLOWED_EXTENSIONS:
            f.unlink()

    # Prepare and write the script
    prepared_code = _prepare_code(code, str(work_dir))
    script_path = work_dir / "script.py"
    script_path.write_text(prepared_code, encoding="utf-8")

    if log_callback:
        await log_callback("info", "Starting code execution...")

    # Pre-scan code for imports and install missing packages before first run
    prescanned = _prescan_imports(code)
    to_install = [p for p in prescanned if not _is_installed(p)]
    if to_install:
        to_install, blocked = _validate_packages(to_install)
        if blocked and log_callback:
            await log_callback("warn", f"Blocked packages not in allowlist: {', '.join(blocked)}")
        if to_install:
            if log_callback:
                await log_callback("info", f"Pre-installing {len(to_install)} package(s): {', '.join(to_install)}")
            await _install_packages(to_install, log_callback)

    stdout, stderr, exit_code = await _run_script(script_path, work_dir, timeout, log_callback)

    # Auto-install missing modules and retry (up to _MAX_INSTALL_RETRIES rounds
    # to handle cascading dependencies, e.g., importing A which needs B)
    already_installed: set[str] = set()
    for _attempt in range(_MAX_INSTALL_RETRIES):
        if exit_code == 0:
            break
        missing = _extract_missing_modules(stderr)
        # Filter out packages we already tried
        new_missing = [p for p in missing if p not in already_installed]
        if not new_missing:
            break
        # Validate packages against allowlist
        new_missing, blocked = _validate_packages(new_missing)
        if blocked and log_callback:
            await log_callback("warn", f"Blocked packages not in allowlist: {', '.join(blocked)}")
        if not new_missing:
            break
        already_installed.update(new_missing)
        installed = await _install_packages(new_missing, log_callback)
        if installed:
            if log_callback:
                await log_callback("info", f"Retrying after installing: {', '.join(new_missing)}")
            stdout, stderr, exit_code = await _run_script(
                script_path, work_dir, timeout, log_callback
            )

    # Scan for generated files
    files = []
    for f in work_dir.iterdir():
        if f.name == "script.py":
            continue
        if f.suffix in ALLOWED_EXTENSIONS and f.is_file():
            mime_type = _detect_mime_type(str(f))
            files.append({
                "path": str(f),
                "filename": f.name,
                "mime_type": mime_type,
                "size": f.stat().st_size,
                "type": _detect_artifact_type(mime_type),
            })

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "files": files,
    }
