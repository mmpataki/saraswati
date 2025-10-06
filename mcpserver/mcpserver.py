"""MCP server exposing Saraswati notes management tools."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
import yaml
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("Notes API")


def _bool_env(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


API_BASE_URL = os.getenv("NOTES_API_BASE_URL", "http://localhost:8001/knowledge/api")
API_USERNAME = os.getenv("NOTES_API_USERNAME", "")
API_PASSWORD = os.getenv("NOTES_API_PASSWORD", "")
VERIFY_TLS = _bool_env("NOTES_API_VERIFY_TLS", False)
REQUEST_TIMEOUT = float(os.getenv("NOTES_API_TIMEOUT", "15"))


def _build_url(path: str) -> str:
    base = API_BASE_URL.rstrip("/")
    endpoint = path.lstrip("/")
    return f"{base}/{endpoint}"


def _request(method: str, path: str, *, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}

    # Use HTTP Basic Auth when username/password are provided
    auth = None
    if API_USERNAME and API_PASSWORD:
        auth = (API_USERNAME, API_PASSWORD)

    try:
        response = requests.request(
            method,
            _build_url(path),
            headers=headers,
            json=json,
            timeout=REQUEST_TIMEOUT,
            verify=VERIFY_TLS,
            auth=auth,
        )

        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        payload = {
            "error": "API request failed",
            "status_code": exc.response.status_code if exc.response else None,
            "message": exc.response.text if exc.response is not None else str(exc),
            "endpoint": path,
        }
        return payload
    except requests.RequestException as exc:
        return {
            "error": "Unable to reach notes API",
            "endpoint": path,
            "message": str(exc),
        }


def _dump_yaml(data: Dict[str, Any]) -> str:
    return yaml.dump(data, sort_keys=False, allow_unicode=True)


def _parse_tags(tags: Optional[str]) -> List[str]:
    if not tags:
        return []
    return [item.strip() for item in tags.split(",") if item.strip()]


@mcp.tool()
def comment_on_review(review_id: str, message: str) -> str:
    """
    Add a comment to an existing review.
    Inputs:
        review_id: ID of the review to comment on
        message: Comment text
    Returns YAML with the created event or an error.
    """
    if not review_id:
        return _dump_yaml({"error": "review_id is required"})
    if not message or not message.strip():
        return _dump_yaml({"error": "message is required"})

    payload = {"message": message}
    result = _request("post", f"/reviews/{review_id}/comment", json=payload)
    if "error" in result:
        return _dump_yaml({"error": "Failed to post comment", "details": result})
    return _dump_yaml({"success": True, "event": result})


@mcp.tool()
def create_review(version_id: str, title: Optional[str] = None, description: Optional[str] = None, reviewers: Optional[str] = None, summary: Optional[str] = None) -> str:
    """
    Create a review for a draft version by submitting it for review.
    Inputs:
        version_id: Draft version id to submit
        title: Optional title for the review
        description: Optional description
        reviewers: Optional comma-separated reviewer ids
        summary: Optional summary/review_comment
    Returns YAML with the created review or an error.
    """
    if not version_id:
        return _dump_yaml({"error": "version_id is required"})

    payload: Dict[str, Any] = {}
    if title and title.strip():
        payload["title"] = title.strip()
    if description and description.strip():
        payload["description"] = description.strip()
    if reviewers:
        ids = [r.strip() for r in reviewers.split(",") if r.strip()]
        if ids:
            payload["reviewer_ids"] = ids
    if summary and summary.strip():
        payload["summary"] = summary.strip()

    result = _request("post", f"/notes/versions/{version_id}/submit", json=payload)
    if "error" in result:
        return _dump_yaml({"error": "Failed to create review", "details": result})
    return _dump_yaml({"success": True, "submission": result})


@mcp.tool()
def delete_note_via_review(note_id: str, reason: Optional[str] = None, reviewers: Optional[str] = None) -> str:
    """
    Request deletion of a note by creating a deletion review.
    Inputs:
        note_id: ID of the note to delete
        reason: Optional reason for deletion
        reviewers: Optional comma-separated reviewer ids
    Returns YAML with the created review or an error.
    """
    if not note_id:
        return _dump_yaml({"error": "note_id is required"})
    payload: Dict[str, Any] = {}
    if reason and reason.strip():
        payload["reason"] = reason.strip()
    if reviewers:
        ids = [r.strip() for r in reviewers.split(",") if r.strip()]
        if ids:
            payload["reviewer_ids"] = ids

    result = _request("delete", f"/notes/{note_id}", json=payload)
    if "error" in result:
        return _dump_yaml({"error": "Failed to create deletion review", "details": result})
    return _dump_yaml({"success": True, "review": result})


@mcp.tool()
def get_review(review_id: str) -> str:
    """
    Retrieve a review by id.
    Inputs:
        review_id: Review id
    Returns YAML with the review detail or an error.
    """
    if not review_id:
        return _dump_yaml({"error": "review_id is required"})
    result = _request("get", f"/reviews/{review_id}")
    if "error" in result:
        return _dump_yaml({"error": "Failed to fetch review", "details": result})
    return _dump_yaml({"review": result})


@mcp.tool()
def cancel_review(review_id: str, comment: Optional[str] = None) -> str:
    """
    Cancel (close) a review.
    Inputs:
        review_id: Review id to cancel
        comment: Optional message to include with the close event
    Returns YAML with the closed review or an error.
    """
    if not review_id:
        return _dump_yaml({"error": "review_id is required"})
    payload: Dict[str, Any] = {}
    if comment and comment.strip():
        payload["comment"] = comment.strip()
    result = _request("post", f"/reviews/{review_id}/close", json=payload)
    if "error" in result:
        return _dump_yaml({"error": "Failed to cancel review", "details": result})
    return _dump_yaml({"success": True, "review": result})


@mcp.tool()
def create_note(title: str, content: str, tags: str = "") -> str:
    """
    Create a new note
    Inputs:
        title: Note title
        content: Markdown content
        tags: Comma-separated tags
    Returns:
        Result of the submission or error message.
    """

    # First create the note
    create_payload = {
        "title": title,
        "content": content,
        "tags": _parse_tags(tags),
    }
    create_result = _request("post", "/notes", json=create_payload)
    
    if "error" in create_result:
        return _dump_yaml({"error": "Failed to create note", "details": create_result})
    
    # Extract version_id from the result
    version_id = create_result.get("version_id")
    if not version_id:
        return _dump_yaml({"error": "No version_id in create response", "create_result": create_result})
    
    # Submit for review
    submit_payload: Dict[str, Any] = {}
    
    submit_result = _request("post", f"/notes/versions/{version_id}/submit", json=submit_payload)
    
    if "error" in submit_result:
        return _dump_yaml({
            "warning": "Note created but submission failed",
            "note": create_result,
            "submit_error": submit_result
        })
    
    return _dump_yaml({
        "success": True,
        "message": "Note created and submitted for review",
        "note": submit_result
    })


# @mcp.tool()
def update_note_version(
    version_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """Update an existing draft version. Provide fields to patch; omit values to leave unchanged."""

    payload: Dict[str, Any] = {}
    if title is not None and title.strip():
        payload["title"] = title
    if content is not None and content.strip():
        payload["content"] = content
    if tags is not None:
        payload["tags"] = _parse_tags(tags)

    if not payload:
        return _dump_yaml({"error": "No fields provided for update", "version_id": version_id})

    result = _request("patch", f"/notes/versions/{version_id}", json=payload)
    return _dump_yaml(result)


def _vote(note_id: str, action: str) -> Dict[str, Any]:
    return _request("post", f"/notes/{note_id}/vote", json={"action": action})


@mcp.tool()
def upvote_note(note_id: str) -> str:
    """Add an upvote to the specified note."""

    result = _vote(note_id, "upvote")
    return _dump_yaml(result)


@mcp.tool()
def downvote_note(note_id: str) -> str:
    """Add a downvote to the specified note."""

    result = _vote(note_id, "downvote")
    return _dump_yaml(result)


@mcp.tool()
def search_notes(
    query: Optional[str] = None,
    page_size: int = 10,
    page: int = 1,
    vector: Optional[str] = None,
    author: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """Search for notes. Provide a keyword query"""

    payload: Dict[str, Any] = {"page": max(page, 1), "page_size": max(page_size, 1)}
    if query is not None:
        payload["query"] = query if query.strip() else "*"
    if vector:
        try:
            payload["vector"] = [float(value.strip()) for value in vector.split(",") if value.strip()]
        except ValueError:
            return _dump_yaml({"error": "Vector must be comma-separated floats", "input": vector})
    if author and author.strip():
        payload["author"] = author.strip()
    if tags:
        tag_values = [value.strip() for value in tags.split(",") if value.strip()]
        if tag_values:
            payload["tags"] = tag_values

    if "query" not in payload and "vector" not in payload and "author" not in payload and "tags" not in payload:
        return _dump_yaml({"error": "Provide a query, vector, author, or tags"})
    if "query" not in payload:
        payload["query"] = "*"

    result = _request("post", "/notes/search", json=payload)
    return _dump_yaml({
        "page": result.get("page"),
        "page_size": result.get("page_size"),
        "total": result.get("total"),
        "total_pages": result.get("total_pages"),
        "items": result.get("items", []),
    })


if __name__ == "__main__":
    x = create_note('xoxo', 'hello world', 'a,b,c')
    print(x)
