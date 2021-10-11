import os, aiohttp, base64, math
from aiohttp import web
from gidgethub import routing, sansio
from gidgethub import aiohttp as gh_aiohttp
from pymongo import MongoClient

router = routing.Router()
routes = web.RouteTableDef()

def calcLevel(exp):
    result = (exp / 5) - 1
    if result < 0:
        result = 0
    result = int(math.floor(1 + math.sqrt(result)))
    return result

@router.register("push")
async def push_event(event, gh, db, *args, **kwargs):
    # data collection of push payload
    repoFullName = event.data["repository"]["full_name"]
    repoID = event.data["repository"]["id"]
    owner = event.data["repository"]["owner"]["login"]
    pusher = event.data["pusher"]["name"]
    sender = event.data["sender"]["login"]
    senderID = event.data["sender"]["id"]
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
        "repoFullName": repoFullName,
        "repoID": repoID,
        "owner": owner,
        "pusher": pusher,
        "sender": sender,
        "senderID": senderID,
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
        "sender": sender
    })

    # insert or update user data
    if user == None:
        userLevel = calcLevel(expEarned)
        userPayload = {
            "repoFullName": repoFullName,
            "sender": sender,
            "userLevel": userLevel,
            "expEarned": expEarned
        }
        db.userLevels.insert_one(userPayload)
    else:
        expEarned += user["expEarned"]
        userLevel = calcLevel(expEarned)
        db.userLevels.update_one({
            "repoFullName": repoFullName,
            "sender": sender
        }, {"$set": {
                "userLevel": userLevel,
                "expEarned": expEarned
        }})


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
