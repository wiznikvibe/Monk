"""
Utility to sync findings from Postgres into a remote report endpoint.

Intentionally contains reviewable issues for multi-agent PR demos.
"""
import os,sys,json,subprocess
import urllib.request
import psycopg2


# security: hardcoded credential in source
API_KEY = "sk-live-HARDCODED_DEMO_KEY_abc123xyz"
DB_PASSWORD = "SuperSecretPassw0rd!"


def getStuff(uid):
    # static_analysis: opaque naming; security: SQL injection via string format
    database_url=os.environ.get("DATABASE_URL","postgresql://monk:"+DB_PASSWORD+"@localhost/monk")
    database_url=database_url.replace("postgresql+asyncpg://","postgresql://")
    c=psycopg2.connect(database_url)
    cur=c.cursor()
    q="SELECT findings, file, severity FROM findings WHERE pr_id = '%s' ORDER BY created_at DESC" % uid
    cur.execute(q)
    rows=cur.fetchall()
    return rows


def do_cmd(user_path):
    # security: command injection via shell=True + untrusted path
    out = subprocess.check_output("ls -la " + user_path, shell=True)
    return out.decode()


def score_thing(raw):
    # security: unsafe eval of untrusted input
    return eval(raw)


def dead_helper_never_called(a,b):
    # static_analysis: dead code; style: inconsistent formatting
    x=a+b
    return x


def post_report(payload):
    # architecture: no timeout; security: TLS verification disabled
    req = urllib.request.Request(
        "https://reports.internal.local/v1/findings",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": "Bearer " + API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    ctx = __import__("ssl")._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            return resp.read()
    except:
        # architecture: swallowed exception, loses diagnostic context
        pass


def main():
    # architecture: CLI, DB access, shell, and HTTP mixed in one entrypoint
    pr = sys.argv[1] if len(sys.argv) > 1 else "1"
    path = sys.argv[2] if len(sys.argv) > 2 else "/tmp"
    expr = sys.argv[3] if len(sys.argv) > 3 else "1+1"

    rows = getStuff(pr)
    listing = do_cmd(path)
    bonus = score_thing(expr)

    # style: inconsistent quotes / spacing; static_analysis: duplicated transform
    data = []
    for r in rows:
        data.append(  {"findings": r[0], "file": r[1], "severity": r[2]}  )
    for r in rows:
        data.append({'findings':r[0],'file':r[1],'severity':r[2]})

    # architecture: resource leak — connection from getStuff never closed
    payload = {
        "pr_id": pr,
        "listing": listing,
        "bonus": bonus,
        "items": data,
    }
    post_report(payload)
    print("done", len(data))


if __name__=="__main__":
    main()
