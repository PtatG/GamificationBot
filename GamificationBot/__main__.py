import os, aiohttp, base64, math
from aiohttp import web
from gidgethub import routing, sansio
from gidgethub import aiohttp as gh_aiohttp
from pymongo import MongoClient
from datetime import datetime

router = routing.Router()
routes = web.RouteTableDef()

def calc_level(exp):
    result = (exp / 5) - 1
    if result < 0:
        result = 0
    result = int(math.floor(1 + math.sqrt(result)))
    return result
# end of calc_level

@router.register("push")
async def push_event(event, gh, db, *args, **kwargs):
    # data collection of push payload
    repo_owner = event.data["repository"]["owner"]["login"]
    repo_full_name = event.data["repository"]["full_name"]
    repo_name = event.data["repository"]["name"]
    repo_id = event.data["repository"]["id"]
    repo_url = event.data["repository"]["html_url"]
    username = event.data["sender"]["login"]
    user_id = event.data["sender"]["id"]
    event_type = "push"
    push_time = datetime.now().isoformat()
    num_commits = len(event.data["commits"])
    # store the commit data into lists
    commits = []
    for comm in event.data["commits"]:
        commits.append({
            "commit_id": comm["id"],
            "commit_time": comm["timestamp"]
        })

    # calculate experience earned
    exp_earned = 10 + (num_commits * 4)

    # create the data collection payload
    payload = {
        "repo_owner": repo_owner,
        "repo_full_name": repo_full_name,
        "repo_name": repo_name,
        "repo_id": repo_id,
        "repo_url": repo_url,
        "username": username,
        "user_id": user_id,
        "event_type": event_type,
        "push_time": push_time,
        "num_commits": num_commits,
        "commits": commits,
        "exp_earned": exp_earned
    }
    # insert payload into push collection
    db.push.insert_one(payload)

    # find user in user_levels collection
    user = db.user_levels.find_one({
        "repo_full_name": repo_full_name,
        "username": username
    })

    # insert or update user data
    if user == None:
        user_level = calc_level(exp_earned)
        user_payload = {
            "repo_full_name": repo_full_name,
            "username": username,
            "num_commits": num_commits,
            "issues_closed": 0,
            "commits": commits,
            "user_level": user_level,
            "exp_earned": exp_earned
        }
        db.user_levels.insert_one(user_payload)
    else:
        num_commits += user["num_commits"]
        exp_earned += user["exp_earned"]
        user_level = calc_level(exp_earned)
        db.user_levels.update_one({
            "repo_full_name": repo_full_name,
            "username": username
        }, {"$set": {
                "num_commits": num_commits,
                "user_level": user_level,
                "exp_earned": exp_earned
        }})
# end of push_event

@router.register("issues", action = "closed")
async def issue_closed_event(event, gh, db, *args, **kwargs):
    # data collection of issues payload
    repo_owner = event.data["repository"]["owner"]["login"]
    repo_full_name = event.data["repository"]["full_name"]
    repo_name = event.data["repository"]["name"]
    repo_id = event.data["repository"]["id"]
    repo_url = event.data["repository"]["html_url"]
    username = event.data["sender"]["login"]
    user_id = event.data["sender"]["id"]
    event_type = "issue closed"
    issue_id = event.data["issue"]["id"]
    issue_url = event.data["issue"]["html_url"]
    issue_created_at = event.data["issue"]["created_at"]
    issue_closed_at = event.data["issue"]["closed_at"]
    exp_earned = 40

    payload = {
        "repo_owner": repo_owner,
        "repo_full_name": repo_full_name,
        "repo_name": repo_name,
        "repo_id": repo_id,
        "repo_url": repo_url,
        "username": username,
        "user_id": user_id,
        "event_type": event_type,
        "issue_id": issue_id,
        "issue_url": issue_url,
        "issue_created_at": issue_created_at,
        "issue_closed_at": issue_closed_at,
        "exp_earned": exp_earned
    }
    # insert payload into issues_closed collection
    db.issues_closed.insert_one(payload)

    user = db.user_levels.find_one({
        "repo_full_name": repo_full_name,
        "username": username
    })

    if user == None:
        user_level = calc_level(exp_earned)
        user_payload = {
            "repo_full_name": repo_full_name,
            "username": username,
            "num_commits": 0,
            "issues_closed": 1,
            "user_level": user_level,
            "exp_earned": exp_earned
        }
        db.user_levels.insert_one(user_payload)
    else:
        issues_closed = user["issues_closed"] + 1
        exp_earned += user["exp_earned"]
        user_level = calc_level(exp_earned)
        db.user_levels.update_one({
            "repo_full_name": repo_full_name,
            "username": username
        }, {"$set": {
                "issues_closed": issues_closed,
                "user_level": user_level,
                "exp_earned": exp_earned
        }})
# end if issue_closed_event

@routes.post("/")
async def main(request):
    # read the github webhook payload
    body = await request.read()

    # our authentication token and secret
    secret = os.environ.get("GH_SECRET")
    oauth_token = os.environ.get("GH_AUTH")
    # our mongodb uri with username and password
    uri = os.environ.get("MONGODB_URI")
    client = MongoClient(uri)
    # connect to test db
    db = client.test

    # a representation of github webhook event
    event = sansio.Event.from_http(request.headers, body, secret = secret)

    async with aiohttp.ClientSession() as session:
        gh = gh_aiohttp.GitHubAPI(session, "PtatG", oauth_token = oauth_token)
        await router.dispatch(event, gh, db)

    return web.Response(status = 200)

if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    port = os.environ.get("PORT")
    if port is not None:
        port = int(port)

    web.run_app(app, port = port)
