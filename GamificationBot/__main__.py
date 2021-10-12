import os, aiohttp, base64, math
from aiohttp import web
from gidgethub import routing, sansio
from gidgethub import aiohttp as gh_aiohttp
from pymongo import MongoClient
from datetime import datetime

router = routing.Router()
routes = web.RouteTableDef()

def calcLevel(exp):
    result = (exp / 5) - 1
    if result < 0:
        result = 0
    result = int(math.floor(1 + math.sqrt(result)))
    return result
# end of calcLevel

@router.register("push")
async def push_event(event, gh, db, *args, **kwargs):
    # data collection of push payload
    repoOwner = event.data["repository"]["owner"]["login"]
    repoFullName = event.data["repository"]["full_name"]
    repoName = event.data["repository"]["name"]
    repoID = event.data["repository"]["id"]
    repoURL = event.data["repository"]["html_url"]
    username = event.data["sender"]["login"]
    userID = event.data["sender"]["id"]
    eventType = "push"
    pushTime = datetime.now().isoformat()
    numCommits = len(event.data["commits"])
    # store the commit data into lists
    commitID = []
    commitTime = []
    for commit in event.data["commits"]:
        commitID.append(commit["id"])
        commitTime.append(commit["timestamp"])

    # calculate experience earned
    expEarned = 10 + (numCommits * 4)

    # create the data collection payload
    payload = {
        "repoOwner": repoOwner,
        "repoFullName": repoFullName,
        "repoName": repoName,
        "repoID": repoID,
        "repoURL": repoURL,
        "username": username,
        "userID": userID,
        "eventType": eventType,
        "pushTime": pushTime,
        "numCommits": numCommits,
        "commitID": commitID,
        "commitTime": commitTime,
        "expEarned": expEarned
    }
    # insert payload into push collection
    db.push.insert_one(payload)

    # find user in userLevels collection
    user = db.userLevels.find_one({
        "repoFullName": repoFullName,
        "username": username
    })

    # insert or update user data
    if user == None:
        userLevel = calcLevel(expEarned)
        userPayload = {
            "repoFullName": repoFullName,
            "username": username,
            "numCommits": numCommits,
            "issuesClosed": 0,
            "userLevel": userLevel,
            "expEarned": expEarned
        }
        db.userLevels.insert_one(userPayload)
    else:
        numCommits += user["numCommits"]
        expEarned += user["expEarned"]
        userLevel = calcLevel(expEarned)
        db.userLevels.update_one({
            "repoFullName": repoFullName,
            "username": username
        }, {"$set": {
                "numCommits": numCommits,
                "userLevel": userLevel,
                "expEarned": expEarned
        }})
# end of push_event

@router.register("issues", action = "closed")
async def issue_closed_event(event, gh, *args, **kwargs):
    # data collection of issues payload
    repoOwner = event.data["repository"]["owner"]["login"]
    repoFullName = event.data["repository"]["full_name"]
    repoName = event.data["repository"]["name"]
    repoID = event.data["repository"]["id"]
    repoURL = event.data["repository"]["html_url"]
    username = event.data["sender"]["login"]
    userID = event.data["sender"]["id"]
    eventType = "issue closed"
    issueID = event.data["issue"]["id"]
    issueURL = event.data["issue"]["html_url"]
    issueCreatedAt = event.data["issue"]["created_at"]
    issueClosedAt = event.data["issue"]["closed_at"]
    expEarned = 40

    payload = {
        "repoOwner": repoOwner,
        "repoFullName": repoFullName,
        "repoName": repoName,
        "repoID": repoID,
        "repoURL": repoURL,
        "username": username,
        "userID": userID,
        "eventType": eventType,
        "issueID": issueID,
        "issueURL": issueURL,
        "issueCreatedAt": issueCreatedAt,
        "issueClosedAt": issueClosedAt,
        "expEarned": expEarned
    }
    # insert payload into issuesClosed collection
    db.issuesClosed.insert_one(payload)

    user = db.userLevels.find_one({
        "repoFullName": repoFullName,
        "username": username
    })

    if user == None:
        userLevel = calcLevel(expEarned)
        userPayload = {
            "repoFullName": repoFullName,
            "username": username,
            "numCommits": 0,
            "issuesClosed": 1,
            "userLevel": userLevel,
            "expEarned": expEarned
        }
        db.userLevels.insert_one(userPayload)
    else:
        issuesClosed = user["issuesClosed"] + 1
        expEarned += user["expEarned"]
        userLevel = calcLevel(expEarned)
        db.userLevels.update_one({
            "repoFullName": repoFullName,
            "username": username
        }, {"$set": {
                "issuesClosed": issuesClosed,
                "userLevel": userLevel,
                "expEarned": expEarned
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
