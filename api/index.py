"""
Vercel entry point. vercel.json rewrites every request to this function as
/api/index?__path=<original path>; the wrapper puts that path back so Flask
routes the request as if it had arrived directly. Without it the function
can see /api/index for every URL and answer 404.
"""
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app as flask_app  # noqa: E402


def app(environ, start_response):
    query = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    path = next((v for k, v in query if k == "__path"), None)
    if path is not None:
        environ["PATH_INFO"] = "/" + path.lstrip("/")
        environ["QUERY_STRING"] = urlencode([(k, v) for k, v in query if k != "__path"])
    return flask_app(environ, start_response)
