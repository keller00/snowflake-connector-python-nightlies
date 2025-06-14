from __future__ import annotations

import argparse
import os
import re

import httpx
from setuptools._vendor.packaging.version import Version

PACKAGE_NAME = "snowflake-connector-python-nightly"
HTTPX_CLIENT = httpx.Client(
    base_url="https://pypi.org",
    headers={
        "Accepts": "application/json",
    },
    follow_redirects=True,
)
CSRF_TOKEN_RE = re.compile(r"<input\s+name=\"csrf_token\"\s+type=\"hidden\"\s+value=\"(.+?)\">")


def extract_csrf_token(site: str) -> str:
    match = CSRF_TOKEN_RE.search(site)
    if match is None:
        raise Exception("Couldn't find CSRF token")
    return match.group(1)


def get_releases(package_name: str) -> tuple[Version, ...]:
    resp = HTTPX_CLIENT.get(f'/pypi/{package_name}/json')  # TODO: switch to simple API
    releases = [Version(k) for k in resp.json()['releases'].keys()]
    releases.sort()
    return tuple(releases)


def delete_release(package_name: str, version: str) -> None:
    url = f"/manage/project/{package_name}/release/{version}/"
    resp = HTTPX_CLIENT.post(
        url,
        data={
            "confirm_delete_version": version,
            "csrf_token": extract_csrf_token(HTTPX_CLIENT.get(url).text),
        },
        headers={
            "referer": f"{HTTPX_CLIENT.base_url}{url}",
        }
    )
    resp.raise_for_status()


def load_dotenv_file(path: str) -> None:
    with open(path, 'r') as f:
        for line in f.readlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, value = line.split('=', 1)
            os.environ[key] = value


def delete_n_oldest_releases(
    package_name: str,
    number: int,
    dry_run: bool = True,
) -> None:
    releases = get_releases(package_name)

    if os.path.exists('.env'):
        load_dotenv_file('.env')

    username = os.environ["PYPI_USERNAME"]
    password = os.environ["PYPI_PASSWORD"]
    login_resp = HTTPX_CLIENT.post(
        "/account/login/",
        data={
            "csrf_token": extract_csrf_token(HTTPX_CLIENT.get("/account/login/").text),
            "username": username,
            "password": password,
        },
        headers={"referer": f"{HTTPX_CLIENT.base_url}/account/login/"}
    )
    if login_resp.url.path == "/account/two-factor/":
        t_factor_resp = HTTPX_CLIENT.post(
            login_resp.url,
            data={
                "csrf_token": extract_csrf_token(login_resp.text),
                "method": "totp",
                "totp_value": input("Two-factor code: "),
            },
            headers={"referer": str(login_resp.url)}
        )
        assert t_factor_resp.status_code == 200, f"after logging in we received status code: {t_factor_resp.status_code}"
    assert login_resp.status_code == 200, f"after logging in we received status code: {login_resp.status_code}"
    for version in releases[:number]:
        if dry_run:
            print(f"{version} would be removed, if this wasn't a dry-run")
        else:
            delete_release(PACKAGE_NAME, str(version))
            print(f"{version} was deleted")


def run_cli() -> int:
    arg_parser = argparse.ArgumentParser("delete_old_releases.py")
    arg_parser.add_argument("-d", "--dry-run", action="store_true", help="don't actually delete anything")
    arg_parser.add_argument("number", metavar="N", type=int, help="delete N oldest releases")
    args = arg_parser.parse_args()
    delete_n_oldest_releases(PACKAGE_NAME, **vars(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
