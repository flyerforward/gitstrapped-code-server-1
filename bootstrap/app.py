import os, json, subprocess, shlex
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from flask import Flask, request, redirect, Response

app = Flask(__name__)

WORKSPACE = os.environ.get("WORKSPACE_DIR", "/workspace")
INCLUDE_FORKS = os.environ.get("INCLUDE_FORKS", "0") == "1"
INCLUDE_ARCHIVED = os.environ.get("INCLUDE_ARCHIVED", "0") == "1"
OWNER_ALLOWLIST = [s.strip() for s in os.environ.get("OWNER_ALLOWLIST", "").split(",") if s.strip()]
DEV_GIT_NAME = os.environ.get("DEV_GIT_NAME", "")
DEV_GIT_EMAIL = os.environ.get("DEV_GIT_EMAIL", "")

def gh_get(path: str, token: str, params: str = ""):
    url = f"https://api.github.com{path}{params}"
    req = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "git-bootstrap"
    })
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def run(cmd, cwd=None, env=None):
    # simple runner that streams output to logs
    print("+", " ".join(shlex.quote(c) for c in cmd))
    subprocess.run(cmd, cwd=cwd, env=env, check=True)

def ensure_git_identity():
    if DEV_GIT_NAME:
        run(["git", "config", "--global", "user.name", DEV_GIT_NAME])
    if DEV_GIT_EMAIL:
        run(["git", "config", "--global", "user.email", DEV_GIT_EMAIL])
    run(["git", "config", "--global", "init.defaultBranch", "main"])
    run(["git", "config", "--global", "pull.ff", "only"])
    run(["git", "config", "--global", "--unset-all", "credential.helper"], env=os.environ.copy() | {"GIT_CONFIG_GLOBAL": os.path.expanduser("~/.gitconfig")})
    run(["git", "config", "--global", "credential.helper", "store --file /root/.git-credentials"])

def clone_or_pull(owner: str, repo: str, token: str):
    dest = os.path.join(WORKSPACE, repo)
    origin = f"https://github.com/{owner}/{repo}.git"
    # Use a one-off http.extraheader (no token in remote URL)
    git_env = os.environ.copy()
    git_env["GIT_HTTP_EXTRAHEADER"] = f"AUTHORIZATION: Bearer {token}"

    if os.path.isdir(os.path.join(dest, ".git")):
        run(["git", "fetch", "--all", "-p"], cwd=dest, env=git_env)
        run(["git", "pull", "--ff-only"], cwd=dest, env=git_env)
    else:
        run(["git", "clone", origin, dest], env=git_env)

@app.route("/bootstrap")
def bootstrap():
    token = request.headers.get("X-Auth-Request-Access-Token")
    user = request.headers.get("X-Auth-Request-User")

    if not token:
        return Response("Missing access token (check oauth2-proxy pass_access_token).", status=401)

    os.makedirs(WORKSPACE, exist_ok=True)
    ensure_git_identity()

    # List repositories the user can access
    # Tip: use pagination if you expect >100 repos; this demo pulls first page
    try:
        repos = gh_get("/user/repos", token, params="?per_page=100&affiliation=owner,collaborator,organization_member")
    except (HTTPError, URLError) as e:
        return Response(f"GitHub API error: {e}", status=502)

    count = 0
    for r in repos:
        owner = r.get("owner", {}).get("login", "")
        name = r.get("name", "")
        if not owner or not name:
            continue

        # Optional owner allowlist
        if OWNER_ALLOWLIST and owner not in OWNER_ALLOWLIST:
            continue

        if not INCLUDE_ARCHIVED and r.get("archived"):
            continue
        if not INCLUDE_FORKS and r.get("fork"):
            continue

        try:
            clone_or_pull(owner, name, token)
            count += 1
        except subprocess.CalledProcessError as e:
            print(f"[WARN] git op failed for {owner}/{name}: {e}")

    # After cloning, head to code-server
    print(f"[bootstrap] user={user} cloned_or_pulled={count}")
    return redirect("/", code=302)

@app.route("/healthz")
def healthz():
    return "ok", 200
