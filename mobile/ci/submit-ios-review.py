#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import jwt
import requests

BASE_URL = "https://api.appstoreconnect.apple.com/v1"


class AppStoreError(RuntimeError):
    pass


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AppStoreError(f"Missing required environment variable: {name}")
    return value


KEY_ID = required("ASC_KEY_ID")
ISSUER_ID = required("ASC_ISSUER_ID")
PRIVATE_KEY_B64 = required("ASC_PRIVATE_KEY_BASE64")
BUNDLE_ID = required("IOS_BUNDLE_ID")
VERSION_NAME = required("IOS_VERSION_NAME")
BUILD_NUMBER = required("IOS_BUILD_NUMBER")
PRIVATE_KEY = base64.b64decode(PRIVATE_KEY_B64).decode("utf-8")


def token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": ISSUER_ID,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=19)).timestamp()),
        "aud": "appstoreconnect-v1",
    }
    return jwt.encode(
        payload,
        PRIVATE_KEY,
        algorithm="ES256",
        headers={"kid": KEY_ID, "typ": "JWT"},
    )


def request(method: str, path: str, *, body=None):
    headers = {
        "Authorization": f"Bearer {token()}",
        "Content-Type": "application/json",
    }
    response = requests.request(
        method,
        f"{BASE_URL}{path}",
        headers=headers,
        data=json.dumps(body) if body is not None else None,
        timeout=90,
    )
    if not response.ok:
        raise AppStoreError(
            f"Apple API {response.status_code} {method} {path}: {response.text[:1200]}"
        )
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


def one(items, message: str):
    if not items:
        raise AppStoreError(message)
    return items[0]


def find_app():
    data = request("GET", f"/apps?filter[bundleId]={quote(BUNDLE_ID)}&limit=1")
    return one(data.get("data", []), f"No App Store Connect app found for {BUNDLE_ID}")


def find_version(app_id: str):
    data = request(
        "GET",
        f"/apps/{app_id}/appStoreVersions?filter[platform]=IOS&filter[versionString]={quote(VERSION_NAME)}&limit=10",
    )
    return one(
        data.get("data", []),
        f"No iOS App Store version {VERSION_NAME} exists for {BUNDLE_ID}",
    )


def list_builds(app_id: str):
    return request(
        "GET",
        f"/builds?filter[app]={app_id}&filter[version]={quote(BUILD_NUMBER)}&sort=-uploadedDate&limit=10",
    ).get("data", [])


def wait_for_build(app_id: str, timeout: int = 2100, interval: int = 20):
    deadline = time.time() + timeout
    last_state = "NOT_FOUND"
    while time.time() < deadline:
        for build in list_builds(app_id):
            state = build.get("attributes", {}).get("processingState") or "UNKNOWN"
            last_state = state
            if state == "VALID":
                print(f"Apple build {BUILD_NUMBER} is VALID: {build['id']}")
                return build
            if state in {"FAILED", "INVALID"}:
                raise AppStoreError(f"Apple build processing failed: {build}")
        print(f"Waiting for Apple build {BUILD_NUMBER}; state={last_state}")
        time.sleep(interval)
    raise AppStoreError(
        f"Timed out waiting for build {BUILD_NUMBER}; last state={last_state}"
    )


def set_export_compliance(build_id: str):
    body = {
        "data": {
            "type": "builds",
            "id": build_id,
            "attributes": {"usesNonExemptEncryption": False},
        }
    }
    request("PATCH", f"/builds/{build_id}", body=body)


def attach_build(version_id: str, build_id: str):
    body = {"data": {"type": "builds", "id": build_id}}
    request("PATCH", f"/appStoreVersions/{version_id}/relationships/build", body=body)
    print(f"Attached build {BUILD_NUMBER} to App Store version {VERSION_NAME}")


def list_submissions(app_id: str, state: str):
    return request(
        "GET",
        f"/apps/{app_id}/reviewSubmissions?filter[state]={state}&limit=200",
    ).get("data", [])


def list_submission_items(submission_id: str):
    return request(
        "GET",
        f"/reviewSubmissions/{submission_id}/items?fields[reviewSubmissionItems]=state,appStoreVersion&include=appStoreVersion&limit=200",
    ).get("data", [])


def item_targets_version(item, version_id: str) -> bool:
    relationship = (
        item.get("relationships", {})
        .get("appStoreVersion", {})
        .get("data")
    )
    return bool(relationship) and str(relationship.get("id")) == str(version_id)


def matching_item(submission_id: str, version_id: str):
    return next(
        (
            item
            for item in list_submission_items(submission_id)
            if item_targets_version(item, version_id)
        ),
        None,
    )


def submit_version(app_id: str, version_id: str):
    for state in ("WAITING_FOR_REVIEW", "IN_REVIEW"):
        for submission in list_submissions(app_id, state):
            if matching_item(submission["id"], version_id):
                print(
                    f"Review already active: submission={submission['id']} state={state}"
                )
                return submission

    submission = None
    item = None
    for ready in list_submissions(app_id, "READY_FOR_REVIEW"):
        ready_item = matching_item(ready["id"], version_id)
        if ready_item:
            submission = ready
            item = ready_item
            print(f"Reusing READY_FOR_REVIEW submission {ready['id']}")
            break

    if submission is None:
        submission_body = {
            "data": {
                "type": "reviewSubmissions",
                "attributes": {},
                "relationships": {
                    "app": {"data": {"type": "apps", "id": app_id}}
                },
            }
        }
        submission = request("POST", "/reviewSubmissions", body=submission_body)["data"]
        item_body = {
            "data": {
                "type": "reviewSubmissionItems",
                "relationships": {
                    "reviewSubmission": {
                        "data": {
                            "type": "reviewSubmissions",
                            "id": submission["id"],
                        }
                    },
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": version_id}
                    },
                },
            }
        }
        item = request("POST", "/reviewSubmissionItems", body=item_body)["data"]
        print(
            f"Created review submission {submission['id']} with item {item['id']}"
        )

    submit_body = {
        "data": {
            "type": "reviewSubmissions",
            "id": submission["id"],
            "attributes": {"submitted": True},
        }
    }
    final = request(
        "PATCH",
        f"/reviewSubmissions/{submission['id']}",
        body=submit_body,
    )["data"]
    state = final.get("attributes", {}).get("state", "UNKNOWN")
    print(f"Review submitted: submission={final['id']} state={state}")
    return final


def main() -> int:
    app = find_app()
    version = find_version(app["id"])
    version_state = version.get("attributes", {}).get("appStoreState") or version.get(
        "attributes", {}
    ).get("appVersionState")
    print(
        f"Preparing App Store review for {BUNDLE_ID} {VERSION_NAME} ({BUILD_NUMBER}); version_state={version_state}"
    )

    build = wait_for_build(app["id"])
    set_export_compliance(build["id"])
    attach_build(version["id"], build["id"])
    submit_version(app["id"], version["id"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"App Store review submission failed: {exc}", file=sys.stderr)
        raise
