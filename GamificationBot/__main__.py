"""
Project name: Gamification Bot
Written by: Phillip Tat
Date written: 8/23/21
For: UCF Senior Design Project
Purpose: Count pushes, commits, issues opened, and issues closed. Calculate experience earned and calculate level. Store data in our database.
"""
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
    # check whether commit is distinct
    non_distinct_commit = 0

    for comm in event.data["commits"]:
        if comm["distinct"]:
            commits.append({
                "id": comm["id"],
                "timestamp": comm["timestamp"]
            })
        # keep count of number of commits that are not distinct
        else:
            non_distinct_commit += 1

    # remove non_distinct_commits from num_commits
    num_commits = num_commits - non_distinct_commit
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
    # insert payload into gamBotPushes collection
    db.gamBotPushes.insert_one(payload)

    # find user in gamBotLevels collection
    user = db.gamBotLevels.find_one({
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
            "user_level": user_level,
            "exp_earned": exp_earned
        }
        db.gamBotLevels.insert_one(user_payload)
    else:
        num_commits += user["num_commits"]
        exp_earned += user["exp_earned"]
        user_level = calc_level(exp_earned)
        db.gamBotLevels.update_one({
            "repo_full_name": repo_full_name,
            "username": username
        }, {"$set": {
                "num_commits": num_commits,
                "user_level": user_level,
                "exp_earned": exp_earned
        }})

    compare_url = event.data["repository"]["compare_url"]
    compare_url = compare_url[:-15]
    basehead = event.data["compare"]
    basehead = base[:-27]
    compare_url += basehead
    print(compare_url)
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
    issue_number = event.data["issue"]["number"]
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
        "issue_number": issue_number,
        "event_type": event_type,
        "issue_id": issue_id,
        "issue_url": issue_url,
        "issue_created_at": issue_created_at,
        "issue_closed_at": issue_closed_at,
        "exp_earned": exp_earned
    }
    # insert payload into gamBotIssues collection
    db.gamBotIssues.insert_one(payload)

    user = db.gamBotLevels.find_one({
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
        db.gamBotLevels.insert_one(user_payload)
    else:
        issues_closed = user["issues_closed"] + 1
        exp_earned += user["exp_earned"]
        user_level = calc_level(exp_earned)
        db.gamBotLevels.update_one({
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
    # connect to githubDB
    db = client.githubDB

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
