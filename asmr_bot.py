# for /u/asmr_bot 

import praw
import time
import datetime
import sqlite3
import re
import random
import shelve
import string
import requests
import traceback
import queue
import theonefoster_bot

import schedule

import asmr_bot_data as d # d for data

# PRAW details, other imported data
app_user_agent = d.appUserAgent
app_id = d.appID
app_secret = d.appSecret
app_URI = d.appURI
app_refresh_token = d.appRefreshToken
watch_channel_id = d.watch_channel_id
watch_msg_title = d.watch_msg_title
watch_msg_body = d.watch_msg_body
BADTITLEPHRASES = d.BadTitlePhrases
BANNEDCHANNELS = d.BANNEDCHANNELS

# gdata details
gApiKey = d.gApiKey
gBrowserKey  = d.gBrowserKey

# global variables
MODLIST = {'theonefoster', 'nvadergir', 'zimm3rmann', 'youngnreckless', 'mahi-mahi', 'asmr_bot', 'sidecarfour', 'harrietpotter'}
VIEWEDMODQUEUE = set()
modqueue_is_full = True #if bot is restarted it will wait for empty modqueue before full queue notifications begin
unactioned_modqueue = queue.Queue(0)

# Messages
METAEXPLAIN = d.METAEXPLAIN
SBEXPLAIN = d.SBEXPLAIN
SBEXPLAIN_MSG = d.SBEXPLAIN_MSG
MUSEXPLAIN = d.MUSEXPLAIN
TITLEEXPLAIN = d.TITLEEXPLAIN
BANNEDCHANNELCOMMENT = d.BANNEDCHANNELCOMMENT
TWOTAGSCOMMENT = d.TWOTAGSCOMMENT
BANNEDCHANNELCOMMENT = d.BANNEDCHANNELCOMMENT
BADTITLECOMMENT = d.BADTITLECOMMENT
UNLISTEDCOMMENT = d.UNLISTEDCOMMENT
SPAMCOMMENT = d.SPAMCOMMENT
REPOSTCOMMENT = d.REPOSTCOMMENT
del(d)

#changed = True
vidIDregex = re.compile('(youtu\.be\/|youtube\.com\/(watch\?(.*&)?v=|(embed|v)\/))([^\?&\"\'>]+)')
toplist = shelve.open("topPosts",'c')
data = shelve.open("data", "c")

if "userSubmissions" not in data.keys():
    data["userSubmissions"] = {}

if "recentVideosSet" not in data.keys():
    data["recentVideosSet"] = set()
    data["recentVideosDict"] = {}

# Open sql databases
print("Opening databases..")
warnings_db = sqlite3.connect('warnings.db') # for warnings database (bad if corrupted)
warnings_cursor = warnings_db.cursor()
warnings_cursor.execute("CREATE TABLE IF NOT EXISTS warnings(NAME TEXT, WARNINGS INTEGER)")
warnings_db.commit()

sql = sqlite3.connect('sql.db') # for everything else (doesn't matter too much if corrupted)
cur = sql.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS doneComments(ID TEXT)") 
cur.execute("CREATE TABLE IF NOT EXISTS donesubmissions(ID TEXT)")
sql.commit()

def getYoutubeVideoData(location, part, input_type, input_val, return_val):

    # read like "from LOCATION, get the PART where INPUT_TYPE is INPUT_VAL and return RETURN_VAL"
    # where location is channels/videos, part is statistics/snippet/status, type is id or fromUsername, val is the search value, return value is the data you want
     
    input_val = input_val.replace(" ", "") # remove spaces (http doesn't like spaces, and it works fine without them eg usernames don't have spaces but people think they do: "CGP Grey" is really "cgpgrey")

    try:
        URL = ("https://www.googleapis.com/youtube/v3/" + location + "?part=" + part + "&" + input_type + "=" + input_val + "&key=" + gBrowserKey)
        response = requests.get(URL).json()
        items = response[u'items']
        snippet = items[0][part]
        rtn = snippet[return_val]
        return rtn
    except Exception as e:
        #traceback.print_exc()
        return -1

def daysSinceYoutubeChannelCreation(channelName):
    creationDate = getYoutubeVideoData("channels", "snippet", "forUsername", channelName, "publishedAt")
    if (creationDate != -1):
        try:
            year = creationDate[0:4]
            month = creationDate[5:7]
            day = creationDate[8:10]

            channelDate = datetime.date(year=int(year),month=int(month),day=int(day))
            return datetime.datetime.today().toordinal() - channelDate.toordinal()
        except Exception as e:
            return -1
    else:
        return -1

def daysSinceYoutubeChannelCreationFromID(channelID):
    creationDate = getYoutubeVideoData("channels", "snippet", "id", channelID, "publishedAt")
    if (creationDate != -1):
        try:
            year = creationDate[0:4]
            month = creationDate[5:7]
            day = creationDate[8:10]

            channelDate = datetime.date(year=int(year),month=int(month),day=int(day))
            return datetime.datetime.today().toordinal() - channelDate.toordinal()
        except Exception as e:
            return -1
    else:
        return -1

def videoIsUnlisted(ID):
    return getYoutubeVideoData("videos", "status", "id", ID, "privacyStatus") == "unlisted"

def redditUserActiveEnoughForFlair(username): #TODO
    user = r.get_redditor(username)

def checkModQueue():
    global modqueue_is_full
    global unactioned_modqueue

    modqueue = list(r.get_mod_queue(subreddit=subreddit.display_name, fetch=True))

    for item in modqueue:
        if item.fullname not in VIEWEDMODQUEUE:
            print("New modqueue item!")
            VIEWEDMODQUEUE.add(item.fullname)

            hour = str((time.struct_time(time.strptime(time.ctime())).tm_hour + 6)%24)
            min = str(time.struct_time(time.strptime(time.ctime())).tm_min)
            scheduletime = hour+":"+min
            
            unactioned_modqueue.put(item)

            schedule.every().day.at(scheduletime).do(checkOldModQueueItem)

            #useless_report = False
            #p = ""

            #for report in item.user_reports:
            #    if (report[0] is None or report[0] == "Spam" or "own content" in report[0] or "self promotion" in report[0] or "self-promotion" in report[0]): #report is None if no reason given
            #        useless_report = True
            #        p = report[0]
            #if useless_report:
            #    item.clicked = True
            #    #item.ignore_reports()
            #    print("Item approved - ignored \"own content\"/spam/blank report. (Reason: '" + p + "')")
            if userIsShadowbanned(item.author.name):
                print("Replying to shadowbanned user " + item.author.name)
             
                if item.fullname.startswith("t3"):  # submission
                    item.remove(False)
                    item.add_comment(SBEXPLAIN).distinguish(sticky=True)
                elif item.fullname.startswith("t1"): # comment
                    item.remove(False)
                    r.send_message(recipient=item.author, subject="Shadowban notification", message=SBEXPLAIN_MSG)
                item.clicked = True
            elif len(modqueue) >= 4 and modqueue_is_full == False:
                print("Full modqueue detected! Messaging mods..")
                r.send_message("/r/asmr", "Modqueue items require attention!", "The modqueue has multiple unactioned items in it - please review them asap! \n\n https://www.reddit.com/r/asmr/about/modqueue/")
                modqueue_is_full = True
            elif len(modqueue) <=2:
                modqueue_is_full = False

def checkOldModQueueItem():
    submission = unactioned_modqueue.get()
    modqueue = list(r.get_mod_queue(subreddit=subreddit.display_name, fetch=True))
    for item in modqueue:
        if item.id == submission.id:
            print("Modqueue item unactioned for 6 hours - messaging mods")
            r.send_message("/r/asmr", "Unactioned Modqueue Item", "Attention - a modqueue item hasn't been actioned for 6 hours. Please review it asap! \n\n https://www.reddit.com/r/asmr/about/modqueue/")
    return schedule.CancelJob

def checkComments():
    comments = subreddit.get_comments(limit=15) # sends request

    for comment in comments:
        cur.execute("SELECT * FROM doneComments WHERE ID=?", [comment.id])
        if not cur.fetchone():
            cur.execute("INSERT INTO doneComments VALUES(?)", [comment.id])
            try:
                commentAuthor = comment.author.name.lower()
                commentBody = comment.body.lower()

                if (commentAuthor in MODLIST and commentAuthor != "asmr_bot"):
                    if ('!bot-meta' in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (bad meta post)")
                        if commentAuthor == "theonefoster":
                            my_comment = tof.get_info(thing_id = comment.fullname)
                            my_comment.delete()
                        else:
                            comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.remove(False)
                        submission.add_comment(METAEXPLAIN).distinguish(sticky=True)
                    elif ('!bot-mus' in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (music)")
                        if commentAuthor == "theonefoster":
                            my_comment = tof.get_info(thing_id = comment.fullname)
                            my_comment.delete()
                        else:
                            comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.remove(False)
                        TLcomment = submission.add_comment(MUSEXPLAIN).distinguish(sticky=True)
                    elif ('!bot-title' in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (bad title)")
                        if commentAuthor == "theonefoster":
                            my_comment = tof.get_info(thing_id = comment.fullname)
                            my_comment.delete()
                        else:
                            comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.remove(False)
                        TLcomment = submission.add_comment(TITLEEXPLAIN).distinguish(sticky=True)
                    elif ("!bot-warning" in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (add warning)")
                        if commentAuthor == "theonefoster":
                            my_comment = tof.get_info(thing_id = comment.fullname)
                            my_comment.delete()
                        else:
                            comment.remove(False)
                        parent = r.get_info(thing_id=comment.parent_id)
                        addWarning(parent)
                    elif("!bot-purge" in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (kill thread)")
                        try:
                            parent = r.get_info(thing_id=comment.parent_id)
                            if parent.fullname.startswith("t1"):# TODO - this isn't necessary I think
                                parent = getCommentFromSubmission(parent)
                                purgeThread(parent)
                            else:
                                if commentAuthor == "theonefoster":
                                    my_comment = tof.get_info(thing_id = comment.fullname)
                                    my_comment.delete()
                                else:
                                    comment.remove(False)
                                r.send_message(commentAuthor, "Failed command", "The !bot-purge command can only be used in reply to a top-level comment. This is due to reddit API restrictions.") #todo: wat
                        except Exception as e:
                            print("Exception when purging comment tree. Parent was " + parent.id)
                            traceback.print_exc()
                            r.send_message(commentAuthor, "Failed command", "Your purge command failed for an unknown reason. Your comment was removed.")
                        finally:
                            comment.remove(False)

            except AttributeError: # if comment has no author (is deleted) (comment.author.name returns AttributeError), do nothing
                print("Attribute Error! Comment was probably deleted.")
                traceback.print_exc()
    
def checkSubmissions():
    submissions = subreddit.get_new(limit=15, fetch=True)

    for submission in submissions:
        cur.execute("SELECT * FROM doneSubmissions WHERE ID=?", [submission.id])
        if not cur.fetchone(): 
            cur.execute("INSERT INTO doneSubmissions VALUES(?)", [submission.id])
            
            # for each new submission..
            
            if(titleHasTwoTags(submission.title)):
                submission.remove(False)
                submission.add_comment(TWOTAGSCOMMENT).distinguish(sticky=True)
                print("Removed submission " + submission.id + " for having two flair tags.")
            elif isBadTitle(submission.title):
                submission.remove(False)
                submission.add_comment(BADTITLECOMMENT).distinguish(sticky=True)
                r.send_message("theonefoster", "Bad Title - Submission removed", submission.permalink + "\n\nTitle was: \"**" + submission.title + "**\"")
                print("Removed submission " + submission.id + " for having a bad title.")
            elif ("youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
                try:
                    result = vidIDregex.split(submission.url)
                    isYoutubeLink = (len(result) >= 4)

                    if isYoutubeLink:   
                        vidID = result[5]
                        channelID = getYoutubeVideoData("videos", "snippet", "id", vidID, "channelId")

                        if channelID == watch_channel_id:
                            r.send_message("theonefoster", watch_msg_title, submission.permalink + "\n\nA submission has been made by /u/" + submission.author.name + watch_msg_body)

                        recent_videos = data["recentVideosSet"].copy()
                        
                        removed = False

                        if channelID in BANNEDCHANNELS:
                            submission.remove(False) # checks for banned youtube channels
                            submission.add_comment(BANNEDCHANNELCOMMENT).distinguish(sticky=True)
                            print("Removing submission " + submission.short_link + " (banned youtube channel)..")
                            removed = True
                        elif videoIsUnlisted(vidID):
                            submission.remove(False)
                            submission.add_comment(UNLISTEDCOMMENT).distinguish(sticky=True)
                            print("Removing submission " + submission.short_link + " (unlisted video)..")
                            removed = True
                        elif vidID in recent_videos:
                            dict_temp = data["recentVideosDict"]
                            old_post = dict_temp[vidID]
                            try:
                                old_post = r.get_info(thing_id=old_post.fullname)
                                if old_post is None or old_post.author is None or old_popst.banned_by is not None: #if post isn't live, ie is removed or deleted
                                    removed = False
                                else: 
                                    removed = True
                            except:
                                removed = True
                            if removed:
                                submission.remove(False)
                                comment = REPOSTCOMMENT.format(old_link=old_post.permalink)
                                submission.add_comment(comment).distinguish(sticky=True)
                                removed = True
                                print("Removing submission " + submission.short_link + " (reposted video)..")
                        if not removed: #successful submission (youtube links only)
                            recent_videos.add(vidID)
                            data["recentVideosSet"] = recent_videos
    
                            dict_temp = data["recentVideosDict"]
                            dict_temp[vidID] = submission
                            data["recentVideosDict"] = dict_temp

                            if submission.author.name not in data["userSubmissions"].keys():
                                d = data["userSubmissions"]
                                d[submission.author.name] = [submission]
                                data["userSubmissions"] = d
                            else:
                                count = 1 # there's already one in submission, don't forget to count that!
                                for sub in data["userSubmissions"][submission.author.name]:
                                    if (not submissionIsDeleted(sub.id)) and sub.banned_by is None: #if submission isn't deleted or removed
                                        subresult = vidIDregex.split(sub.url)
                                        subVidID = subresult[5]
                                        subChannelID = getYoutubeVideoData("videos", "snippet", "id", subVidID, "channelId")
                                        if subChannelID == channelID:
                                            count+=1
                                if count >= 3: #more than 2 submissions to same channel in past day
                                    submission.remove(False)
                                    submission.add_comment(SPAMCOMMENT).distinguish(sticky=True)
                                    print("Removed submission " + submission.id + " and banned user /u/" + submission.author.name + " for too many links to same youtube channel")
                                    submissionlinks = submission.permalink + "\n\n"
                                    sublist = data["userSubmissions"][submission.author.name]
                                    for s in sublist:
                                        submissionlinks += s.permalink + "\n\n"
                                        temp_sub = r.get_info(thing_id=s.fullname)
                                        temp_sub.remove(True)
                                    data["userSubmissions"][submission.author.name] = []
                                    note = "too many links to same youtube channel - 1-day ban"
                                    msg = "Warning ban for spamming links to a youtube channel"
                                    subreddit.add_ban(submission.author, duration=1, note=note, ban_message=msg)
                                    r.send_message("/r/" + subreddit.display_name, "Ban Notification", "I have banned /u/" + submission.author.name + " for spammy behaviour (submitting three links to the same youtube channel in a 24-hour period). The ban will last **1 day only**. \n\nLinks to the offending submissions:\n\n" + submissionlinks)
                                else:
                                    d = data["userSubmissions"]
                                    l = d[submission.author.name] 
                                    l.append(submission)
                                    d[submission.author.name] = l
                                    data["userSubmissions"] = d
                            data.sync()
                        
                except Exception as e:
                    print("exception on removal of submission " + submission.short_link + " - " + str(e))
                    traceback.print_exc()

def titleHasTwoTags(title):
    twoTagsRegex = re.compile('.*\[(intentional|unintentional|media|article|discussion|question|meta)\].*\[(intentional|unintentional|media|article|discussion|question|meta)\].*', re.I)
    return (re.search(twoTagsRegex, title) != None) # search the title for two tags; if two are found return true, else return false

def updateTopSubmissions(): # updates recommendation database. Doesn't usually need to be run unless the data gets corrupt or the top submissions drastically change.
    submissions = subreddit.get_top_from_all(limit = 750)
    addedcount = 0
    totalcount = 0

    for submission in submissions:
        totalcount += 1
        print("Got submission " + submission.id + "(" + str(totalcount) + ")")
        if (".youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
            try:
                result = vidIDregex.split(submission.url)
                vidID = result[5]
                channelName = getYoutubeVideoData("videos", "snippet", "id", vidID, "channelTitle")
                vidTitle = getYoutubeVideoData("videos", "snippet", "id", vidID, "title")
                if (channelName != -1) and (vidTitle != -1):
                    toplist[str(addedcount)] = {"URL" : submission.url, "Channel": channelName, "Title": vidTitle, "Reddit Link": submission.permalink}
                    addedcount += 1
                else:
                    print("Youtube Exception. Bad link?")
            except Exception as e:
                print("Other exception - " + str(e))
                traceback.print_exc()

    toplist.sync()
    print("total videos: " + str(addedcount)) # 471

def recommendTopSubmission():
    # updateTopSubmissions() # uncomment this line and run to update database. Or just call the function somewhere.
    rand = random.randint(0, len(toplist)-1)
    rtn = "How about [" + toplist[str(rand)]["Title"] + "](" + (toplist[str(rand)]["URL"]) + ") by " + toplist[str(rand)]["Channel"] + "? \n\n[(Reddit link)](" + toplist[str(rand)]["Reddit Link"] + ") \n\nIf you don't like this video, reply with ""!recommend"" and I'll find you another one."

    return ''.join(char for char in rtn if char in string.printable) # removes stupid unicode characters

def replyToMessages():
    messages = r.get_unread(limit=100)

    for message in messages:
        if not message.was_comment:
            user = message.author.name
            print("Message dectected from " + user)

            if ("!recommend" in message.body.lower()): # recommendation
                print("Recommending popular video")
                messageToSend = recommendTopSubmission()
                message.reply(messageToSend)
            elif(message.subject == "flair request" or message.subject == "re: flair request"): # set flair

                gotFromID = False
                channelName = message.body
                des = getYoutubeVideoData("channels", "snippet", "forUsername", channelName, "description") # des as in description #tested
            
                if des == -1:
                    des = getYoutubeVideoData("channels", "snippet", "id", message.body, "description")
                    channelName = getYoutubeVideoData("channels", "snippet", "id", message.body, "title")
                    gotFromID = True

                if des != -1:
                    if "hey /r/asmr mods!" in des.lower():
                        if gotFromID:
                            subs = int(getYoutubeVideoData("channels", "statistics", "id", message.body, "subscriberCount"))
                        else:
                            subs = int(getYoutubeVideoData("channels", "statistics", "forUsername", channelName, "subscriberCount"))

                        if subs >= 1000:
                            if gotFromID:
                                age = daysSinceYoutubeChannelCreationFromID(message.body)
                            else:
                                age = daysSinceYoutubeChannelCreation(channelName)

                            if age > 182:

                                if gotFromID:
                                    videoCount = int(getYoutubeVideoData("channels", "statistics", "id", message.body, "videoCount"))
                                else:
                                    videoCount = int(getYoutubeVideoData("channels", "statistics", "forUsername", channelName, "videoCount"))

                                if videoCount >= 12:
                                    r.set_flair(subreddit="asmr", item=user, flair_text=channelName, flair_css_class="purpleflair")
                                    message.reply("Verification has been sucessful! Your flair should be applied within a few minutes, but it can sometimes take up to an hour depending on how slow reddit is being today. Please remember to remove the message from your channel description as soon as possible, otherwise somebody could steal your flair. Enjoy!")
                                    print("Verified and set flair for " + user)
                                else:
                                    message.reply("Unfortunately your channel needs to have at least 12 published videos to be eligible for subreddit flair, but you've only published " + str(videoCount) + " so far. Thanks for applying though, and feel free to check back once you've published 12 videos.")
                                    print("flair verification for " + channelName + " failed - not enough published videos.")
                            else:
                                message.reply("Unfortunately your channel needs to be at least 6 months (182 days) old to be eligible for subreddit flair. Thanks for applying, and feel free to check back when your channel is old enough!")
                                print("flair verification for " + channelName + " failed - channel too new.")
                        else:
                            message.reply("Unfortunately you need to have 1000 youtube subscribers to qualify for flair. You only have " + str(subs) + " at the moment, but come back once you reach 1000!")
                            print("flair verification for " + channelName + " failed - not enough subs.")
                    else:
                        message.reply("I couldn't see the verification message in your channel description. Please make sure you include the exact phrase '**Hey \\/r/asmr mods!**' (without the quotes) in your youtube channel description so I can verify that you really own that channel. You should remove the verification message as soon as you've been verified.")
                        print("flair verification for " + channelName + " failed - no verification message.")
                else:
                    message.reply("""
Sorry, I couldn't find that channel. You can use either the channel name (eg 'asmrtess') or the channel ID (the messy part in the youtube link - go to your page and get just the ID from the URL in the format youtube.com/channel/<ID>, eg "UCb3fNzphmiwDgHO2Yg319uw"). Sending ONLY the username OR the ID will work. 
                
Please make sure that the username/ID is exactly correct as it appears on youtube, and that you're not sending anything but the username or channel ID - for example spaces either side of the username/ID or extra text apart from the username/ID (sending the full "youtube.com" link won't work). See [the wiki page](/r/asmr/wiki/flair_requests) for full instructions. If you're still having problems, please [message the human mods](https://www.reddit.com/message/compose?to=%2Fr%2Fasmr)""")
                    print("flair verification failed - channel not found. Message was: " + message.body)
            elif(message.subject == "delete flair"): # delete flair
                if message.body == "delete flair":
                    r.delete_flair(subreddit="asmr", user=user)
                    message.reply("Your flair has been deleted. To apply for flair again, use [this link.](https://www.reddit.com/message/compose?to=asmr_bot&subject=flair%20request&message=enter your channel name here)")
                    print("Flair deleted for " + user)
            elif("post reply" not in message.subject) and ("comment reply" not in message.subject) and ("username mention" not in message.subject) and ("you've been banned from" not in message.subject):
                print("Command not recognised. Message was " + message.body)
                message.reply("Sorry, I don't recognise that command. If you're trying to request a flair, read [the instructions here](https://www.reddit.com/r/asmr/wiki/flair_requests). For other commands you can send me, read the [asmr_bot wiki page](https://www.reddit.com/r/asmr/wiki/asmr_bot). If you have any questions or feedback, please message /u/theonefoster.")
        message.mark_as_read()

def userIsActive(username):# TODO
    return True

def userIsShadowbanned(username):
    try:
        user = r.get_redditor(user_name=username, fetch=True)
        return False
    except praw.errors.HTTPException:
        return True
    except Exception as e:
        print("Unknown exception when checking shadowban for user " + username + " - exception code: \"" + str(e) + "\"")
        traceback.print_exc()
        return False

def submissionIsDeleted(id):
    try:
        submission = r.get_submission(submission_id = id)
        return (submission.author == None)
        return False
    except praw.errors.InvalidSubmission:
        return True

def addWarning(post): # post is a reddit 'thing' (comment or submission)
    user = post.author.name
    ordinal = "?"
    # curWar.execute("DELETE FROM warnings WHERE name=?", [user])
    # sqlWar.commit()
    # print "deleted."
    # time.sleep(10000)

    warnings_cursor.execute("SELECT * FROM warnings WHERE name=?", [user])
    result = warnings_cursor.fetchone()
    
    if not result:
        post.remove(False)
        warnings_cursor.execute("INSERT INTO warnings VALUES(?,?)", [user, 1])
        note = "Auto-ban: first warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). This is your first warning, which is accompanied by a 7-day ban. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
        subreddit.add_ban(post.author, duration=7, note=note, ban_message=msg)
        ordinal = "First"
    elif result[1] >= 2: 
        post.remove(False)
        warnings_cursor.execute("DELETE FROM warnings WHERE name=?", [user])
        warnings_cursor.execute("INSERT INTO warnings VALUES(?,?)",  [user, 3])
        note = "Auto-ban: Permanent - " + post.permalink
        msg = "You have been automatically banned because of your post [here](" + post.permalink + "). This is your third warning, meaning you are now permanently banned."
        subreddit.add_ban(post.author, note=note, ban_message=msg)
        ordinal = "Third"
    elif result[1] == 1:
        post.remove(False)
        warnings_cursor.execute("DELETE FROM warnings WHERE name=?", [user])
        warnings_cursor.execute("INSERT INTO warnings VALUES(?,?)",  [user, 2])
        note = "Auto-ban: Final warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). **This is your final warning**. You will be banned for the next 30 days; if you receive another warning, you will be permanently banned. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
        subreddit.add_ban(post.author, duration=30, note=note, ban_message=msg)
        ordinal = "Second"
    warnings_db.commit()
    print(ordinal + " warning added for " + user)

def isBadTitle(title):
    title = title.lower()
    if ("[intentional]" in title or "[unintentional]" in title):
        for phrase in BADTITLEPHRASES:
            if phrase in title:
                return True
    return False

def purgeThread(comment): # yay recursion woop woop
    for c in comment.replies:
        purgeThread(c)
    comment.remove(False)

def getCommentFromSubmission(comment):
    s = comment.submission
    i = comment.id
    for c in s.comments:
        if c.id == i:
            return c
    return None

def login():
    print("logging in..")
    r = praw.Reddit(app_user_agent, disable_update_check=True)
    r.set_oauth_app_info(app_id,app_secret, app_URI)
    r.refresh_access_information(app_refresh_token)
    print("logged in as " + str(r.user.name))
    return r

def removeSticky():
    sticky = subreddit.get_sticky()
    try:
        if "Free-For-All Friday" in sticky.title or "Tech Tuesday" in sticky.title:
            sticky.unsticky()
        else:
            sticky = subreddit.get_sticky(bottom=True)
            if "Free-For-All Friday" in sticky.title or "Tech Tuesday" in sticky.title:
                sticky.unsticky()
    except praw.errors.HTTPException as e: # if there's no sticky it'll throw a 404 Not Found
        pass

def clearUserSubmissions():
    # data["userSubmissions"] is a dict containing usernames as keys and lists as values
    # Each user's dict value is a list of submission objects, representing 
    # every submission they've made in the last 24 hours

    submissions = data["userSubmissions"]
    users = list(submissions.keys())
    for user in users: 
        submissionsbyuser = submissions[user] 
        temp = submissionsbyuser.copy()
        for s in temp:
            if s.created_utc < (time.time()-86400): #if the submission was over 24 hours ago
                submissionsbyuser.remove(s) # remove it from the list
        if len(submissionsbyuser) == 0: # and if there are no submissions by that user in the past 24 hours
            del submissions[user] # remove the user's key from the dict
            
        else:
            if submissions[user] != submissionsbyuser:
                submissions[user] = submissionsbyuser # update submissions log
    data["userSubmissions"] = submissions
    data.sync()

def clearVideoSubmissions():
    submissions_dict = data["recentVideosDict"]
    submissions_set = data["recentVideosSet"]

    temp_dict = submissions_dict.copy()
    
    for key in temp_dict.keys():
        if submissions_dict[key].created_utc < (time.time() - 7948800): #if submission was more than 3 months ago
            del submissions_dict[key]
            submissions_set.remove(key)

    data["recentVideosDict"] = submissions_dict
    data["recentVideosSet"] = submissions_set
    data.sync()

def asmrbot():

    schedule.run_pending()
    #updateTopSubmissions()
    checkComments()
    checkSubmissions()
    #clearUserSubmissions()
    #clearVideoSubmissions()
    replyToMessages()
    checkModQueue()

# ----------------------------------------------------
# END OF FUNCTIONS
# ----------------------------------------------------

r = login()
tof = theonefoster_bot.login()
subreddit = r.get_subreddit("asmr")

schedule.every().saturday.at("18:00").do(removeSticky)
schedule.every().wednesday.at("18:00").do(removeSticky)
schedule.every().hour.do(clearUserSubmissions)
schedule.every().day.at("02:00").do(clearVideoSubmissions)

while True:
    try:
        asmrbot()
        sql.commit()
        r.handler.clear_cache()
        time.sleep(5)
    except praw.errors.HTTPException:
        try:
            r = login()
        except Exception as f:
            print("Login failed: " + str(f))
            print ("Sleeping....")
            time.sleep(30)
    except Exception as e:
        print(str(e))
        traceback.print_exc()
        try:
            r = login()
        except Exception as f:
            print(str(f))
            print("Sleeping..")
            time.sleep(30) # usually rate limits or 503. Sleeping reduces reddit load.
