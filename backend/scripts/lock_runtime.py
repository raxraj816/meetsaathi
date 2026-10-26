"""Hash-lock the dependency versions from a tested runtime image using official PyPI release digests.

Usage: python backend/scripts/lock_runtime.py --image meetsaathi-backend:continuation
No wheels are executed/downloaded by this script. pip verifies each selected wheel against the lock at install.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import subprocess

import httpx


async def generate(image: str, output: pathlib.Path) -> None:
    code = "import importlib.metadata as m,json;print(json.dumps(sorted((d.metadata['Name'],d.version) for d in m.distributions() if d.metadata['Name'].lower() not in ('meetsaathi-backend','pip','setuptools','wheel'))))"
    versions = json.loads(subprocess.check_output(["docker", "run", "--rm", image, "python", "-c", code], text=True))
    limit = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=60) as client:
        async def pinned(name, version):
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name) or not re.fullmatch(r"[a-zA-Z0-9_.+!-]+", version):
                raise ValueError("Invalid distribution identity")
            async with limit:
                response = await client.get(f"https://pypi.org/pypi/{name}/{version}/json")
                response.raise_for_status()
            hashes = sorted({f["digests"]["sha256"] for f in response.json()["urls"]})
            if not hashes or any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes):
                raise ValueError("Missing release hashes")
            return name.lower().replace("_", "-") + "==" + version + " \\\n" + " \\\n".join("    --hash=sha256:" + h for h in hashes)
        pins = await asyncio.gather(*(pinned(n, v) for n, v in versions))
    header = "# Runtime dependencies from the tested Python 3.12 Linux ARM64 image.\n# All release-file SHA256 digests come from https://pypi.org/pypi/<name>/<version>/json.\n# Regenerate with backend/scripts/lock_runtime.py after testing intentional dependency updates.\n"
    output.write_text(header + "\n".join(sorted(pins)) + "\n")
    print(f"Locked {len(pins)} distributions with SHA256 hashes in {output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / "requirements.lock")
    args = parser.parse_args()
    asyncio.run(generate(args.image, args.output))


if __name__ == "__main__":
    main()
