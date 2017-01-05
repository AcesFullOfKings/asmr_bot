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

import schedule

import asmr_bot_data as d # d for data
import theonefoster_bot # used to delete subreddit reply commands

class my_submission_type():
    sub_permalink = ""
    sub_ID = ""
    channel_ID = ""
    date_created = ""

# PRAW details, other imported data
app_user_agent = d.app_user_agent
app_id = d.app_id
app_secret = d.app_secret
app_URI = d.app_URI
app_refresh_token = d.app_refresh_token
bad_title_phrases = d.bad_title_phrases
#banned_channels = d.BANNED_CHANNELS

# gdata details
g_browser_key = d.g_browser_key

# global variables
mod_list = {'theonefoster', 'nvadergir', 'zimm3rmann', 'youngnreckless', 'mahi-mahi', 'asmr_bot', 'sidecarfour', 'harrietpotter'}
viewed_mod_queue = set()
modqueue_is_full = True #if bot is restarted it will wait for empty modqueue before full queue notifications begin
unactioned_modqueue = queue.Queue(0)
first_run = True #does a lot more processing on first run to catch up with anything missed during downtime
banned_channels = set()

# Messages
meta_explain = d.META_EXPLAIN
sb_explain = d.SB_EXPLAIN
sb_explain_msg = d.SB_EXPLAIN_MSG
mus_explain = d.MUS_EXPLAIN
mod_title_explain = d.MOD_TITLE_EXPLAIN
two_tags_explain = d.TWO_TAGS_COMMENT
banned_channel_explain = d.BANNED_CHANNEL_COMMENT
auto_title_explain = d.AUTO_TITLE_COMMENT
unlisted_explain = d.UNLISTED_COMMENT
spam_explain = d.SPAM_COMMENT
repost_explain = d.REPOST_COMMENT
channel_or_playlist_explain = d.CHANNEL_PLAYLIST_EXPLAIN
flair_errors = d.flair_errors
comment_reply = d.comment_reply
del(d)

vid_id_regex = re.compile('(youtu\.be\/|youtube\.com\/(watch\?(.*&)?v=|(embed|v)\/))([^\?&\"\'>]+)')
attribution_regex = re.compile("\/attribution_link\?.*v%3D([^%&]*)(%26|&|$)")

# open shelves
toplist = shelve.open("topPosts","c")
user_submission_data = shelve.open("user_submission_data", "c") # all submissions from past day by author
recent_video_data = shelve.open("recent_video_data", "c") # videos submitted over past 3 months
seen_objects = shelve.open("seen_objects", "c") # to track which objects have been seen.

if "videos" not in recent_video_data: # initialise dict
    fake = my_submission_type()
    fake.date_created = time.time()
    recent_video_data["videos"] = {"id": fake} # empty dict can cause problems. enter test data and remove later.

if "submissions" not in user_submission_data: #initialise dict
    fake = my_submission_type()
    fake.date_created = time.time()
    user_submission_data["submissions"] = {"un": [fake]} # empty dict can cause problems. enter test data and remove later.

if "submissions" not in seen_objects:
    seen_objects["submissions"] = []

if "comments" not in seen_objects:
    seen_objects["comments"] = []

user_submission_data.sync()
recent_video_data.sync()

# Open sql databases
print("Opening databases..")
warnings_db = sqlite3.connect('warnings.db') # for warnings database (bad if corrupted so not using shelve as it's lost data in the past)
warnings_cursor = warnings_db.cursor()
warnings_cursor.execute("CREATE TABLE IF NOT EXISTS warnings(NAME TEXT, WARNINGS INTEGER)")
warnings_db.commit()

# ----------------------
# BEGIN FUNCTIONS
# ----------------------

def get_youtube_video_data(location, part, input_type, input_val, return_val):

    # read like "from LOCATION, get the PART where INPUT_TYPE is INPUT_VAL and return RETURN_VAL"
    # where location is channels/videos, part is statistics/snippet/status, type is id or fromUsername, val is the search value, return value is the data you want
     
    input_val = input_val.replace(" ", "") # remove spaces (http doesn't like spaces, and it works fine without them: usernames don't have spaces but people think they do: "CGP Grey" is really "cgpgrey")

    try:
        URL = ("https://www.googleapis.com/youtube/v3/" + location + "?part=" + part + "&" + input_type + "=" + input_val + "&key=" + g_browser_key)
        response = requests.get(URL).json()
        items = response[u'items']
        snippet = items[0][part]
        rtn = snippet[return_val]
        return rtn
    except Exception as e:
        #traceback.print_exc()
        return -1

def days_since_youtube_channel_creation(**kwargs):
    if "id" in kwargs:
        creation_date = get_youtube_video_data("channels", "snippet", "id", kwargs["id"], "publishedAt")
    elif "name" in kwargs:
        creation_date = get_youtube_video_data("channels", "snippet", "forUsername", kwargs["name"], "publishedAt")
    else:
        creation_date = -1

    if (creation_date != -1):
        try:
            year = creation_date[0:4]
            month = creation_date[5:7]
            day = creation_date[8:10]

            channel_date = datetime.date(year=int(year),month=int(month),day=int(day))
            return datetime.datetime.today().toordinal() - channel_date.toordinal()
        except Exception as e:
            return -1
    else:
        return -1

def video_is_unlisted(ID):
    return get_youtube_video_data("videos", "status", "id", ID, "privacyStatus") == "unlisted"

def get_vid_id(url):
    if "attribution_link" in url:
        result = attribution_regex.split(url)
        vid_id = result[1]
    elif "youtube." in url or "youtu.be" in url:
        result = vid_id_regex.split(url)
        vid_id = result[5]
    else:
        return -1

    return vid_id

def check_mod_queue():
    global modqueue_is_full
    global unactioned_modqueue
    global seen_objects
    global user_submission_data
    global recent_video_data

    modqueue = list(r.get_mod_queue(subreddit=subreddit.display_name))

    for item in modqueue:
        if item.fullname not in viewed_mod_queue:
            print("New modqueue item!")
            viewed_mod_queue.add(item.fullname)

            hour = str((time.struct_time(time.strptime(time.ctime())).tm_hour + 4)%24)
            min = str(time.struct_time(time.strptime(time.ctime())).tm_min)
            scheduletime = hour+":"+min
            
            unactioned_modqueue.put(item)

            schedule.every().day.at(scheduletime).do(check_old_mod_queue_item)

            if user_is_shadowbanned(item.author.name):
                print("Replying to shadowbanned user " + item.author.name)
            
            if item.fullname.startswith("t3"):  # submission
                    item.remove(False)
                    item.add_comment(sb_explain).distinguish(sticky=True)
                elif item.fullname.startswith("t1"): # comment
                    item.remove(False)
                    r.send_message(recipient=item.author, subject="Shadowban notification", message=sb_explain_msg)
                item.clicked = True
            elif len(modqueue) >= 4 and modqueue_is_full == False:
                print("Full modqueue detected! Messaging mods..")
                r.send_message("/r/" + subreddit.display_name, "Modqueue items require attention!", "The modqueue has multiple unactioned items in it - please review them asap! \n\n https://www.reddit.com/r/asmr/about/modqueue/")
                modqueue_is_full = True
            elif len(modqueue) <=2:
                modqueue_is_full = False

def check_old_mod_queue_item():
    submission = unactioned_modqueue.get()
    modqueue = list(r.get_mod_queue(subreddit=subreddit.display_name, fetch=True))
    for item in modqueue:
        if item.id == submission.id:
            print("Modqueue item unactioned for 4 hours - messaging mods")
            r.send_message("/r/" + subreddit.display_name, "Unactioned Modqueue Item", "Attention - a modqueue item hasn't been actioned for 4 hours. Please review it asap!\n\nhttps://www.reddit.com/r/asmr/about/modqueue/")
    return schedule.CancelJob

def check_comments():
    global first_run
    global seen_objects
    global user_submission_data
    global recent_video_data

    limit = 100 if first_run else 6

    comments = list(subreddit.get_comments(limit=limit)) # sends request

    for comment in comments:
        if comment.id not in seen_objects["comments"]:
            seen_comments = seen_objects["comments"]
            seen_comments.append(comment.id)
            seen_objects["comments"] = seen_comments
            seen_objects.sync()

            try:
                comment_author = comment.author.name.lower()
                comment_body = comment.body.lower()

                if any(comment_body == x for x in ["ayy", "ayyy", "ayyyy", "ayyyyy"]):
                    print("Responding to ayy by /u/" + comment_author)
                    comment.reply("lmao").distinguish()
                    continue

                if (comment_author in mod_list):
                    if ('!bot-meta' in comment_body):
                        print("Comment found! Removing submission in response to " + comment_author + " (bad meta post)")
                        remove_mod_comment(comment)
                        submission_id = comment.parent_id
                        submission = r.get_submission(submission_id=submission_id[3:])
                        submission.remove(False)
                        submission.add_comment(meta_explain).distinguish(sticky=True)
                    elif ('!bot-mus' in comment_body):
                        print("Comment found! Removing submission in response to " + comment_author + " (music)")
                        remove_mod_comment(comment)
                        submission_id = comment.parent_id
                        submission = r.get_submission(submission_id=submission_id[3:])
                        submission.remove(False)
                        submission.add_comment(mus_explain).distinguish(sticky=True)
                    elif ('!bot-title' in comment_body):
                        print("Comment found! Removing submission in response to " + comment_author + " (bad title)")
                        remove_mod_comment(comment)
                        submission_id = comment.parent_id
                        submission = r.get_submission(submission_id=submission_id[3:])
                        submission.remove(False)
                        submission.add_comment(mod_title_explain).distinguish(sticky=True)
                    elif ("!bot-warning" in comment_body):
                        print("Comment found! Removing post in response to " + comment_author + " (add warning)")
                        remove_mod_comment(comment)
                        parent = r.get_info(thing_id=comment.parent_id)
                        add_warning(parent)
                    elif("!bot-purge" in comment_body):
                        print("Comment found! Removing comment tree in response to " + comment_author + " (kill thread)")
                        try:
                            parent = r.get_info(thing_id=comment.parent_id)
                            if parent.fullname.startswith("t1"):# TODO - this isn't necessary I think
                                parent = get_comment_from_submission(parent)
                                purge_thread(parent)
                            else:
                                r.send_message(recipient=comment_author, subject="Failed command", message="The !bot-purge command can only be used in reply to a comment. This is due to reddit API restrictions.") #todo: wat
                            
                            remove_mod_comment(comment)
                        except Exception as e:
                            print("Exception when purging comment tree - "+str(e)+"\nParent was " + parent.id)
                            #traceback.print_exc()
                            r.send_message(recipient=comment_author, subject="Failed command", message="Your purge command failed for an unknown reason. Your comment was removed.")
                        finally:
                            comment.remove(False)
                    elif "!ban" == comment_body[:4]:
                        reason = comment_body[5:]
                        if reason == "":
                            reason = "<No reason given>"
                        parent = r.get_info(thing_id=comment.parent_id)
                        ban_user = parent.author.name
                        msg = "You have been automatically banned for [your post here]({link})."

                        print("Banning user {ban_user} for post {post}: {reason}".format(ban_user=ban_user, post=parent.id, reason=reason))
                        parent.remove(False)
                        remove_mod_comment(comment)
                        
                        note = comment.author.name + ": " + reason
                        subreddit.add_ban(ban_user, note=note, ban_message=msg.format(link=parent.permalink))

                        message = "I have permanently banned {ban_user} for their [post here]({ban_post}?context=9) in response to [your comment here]({comment}?context=9), with the reason: \n\n\>{reason} \n\n Ban list: /r/asmr/about/banned"

                        r.send_message(recipient=comment_author, subject="Ban successful", message=message.format(ban_user=ban_user, ban_post=parent.permalink, comment=comment.permalink, reason=reason))

            except AttributeError as ex: # if comment has no author (is deleted) (comment.author.name returns AttributeError), do nothing
                print("Attribute Error! Comment was probably deleted. Comment was " + str(comment.fullname))
                print(str(ex))
                #traceback.print_exc()

def remove_mod_comment(comment):
    """If comment was made by me, I have the authentication to delete it, which is preferred. Otherwise Remove it since I can't delete other mods' comments
    """
    if comment.author.name == "theonefoster":
        my_comment = tof.get_info(thing_id = comment.fullname)
        my_comment.delete()
    else:
        comment.remove(False)
    
def check_submissions():
    global first_run
    global recent_video_data
    global user_submission_data
    global seen_objects

    limit = 50 if first_run else 8

    submissions = list(subreddit.get_new(limit=limit))

    for submission in submissions:
        if submission.id not in seen_objects["submissions"]: 
            seen_submissions = seen_objects["submissions"]
            seen_submissions.append(submission.id)
            seen_objects["submissions"] = seen_submissions
            seen_objects.sync()
            
            # for each new submission..
            if(title_has_two_tags(submission.title)):
                submission.remove(False)
                submission.add_comment(two_tags_explain).distinguish(sticky=True)
                print("Removed submission " + submission.id + " for having two flair tags.")
            elif is_bad_title(submission.title):
                submission.remove(False)
                submission.add_comment(auto_title_explain).distinguish(sticky=True)
                r.send_message(recipient="theonefoster", subject="Bad Title - Submission removed", message=submission.permalink + "\n\nTitle was: \"**" + submission.title + "**\"")
                print("Removed submission " + submission.id + " for having a bad title.")
            elif ("youtube" in submission.url or "youtu.be" in submission.url):
                try:
                    if is_banned_link(submission.url):
                        submission.remove(False)
                        submission.add_comment(channel_or_playlist_explain).distinguish(sticky=True)
                        print("Removing submission " + submission.id + " (link to channel/playlist)")
                    else:
                        if ("youtube." in submission.url or "youtu.be" in submission.url):
                            is_youtube_link = True
                            vid_id = get_vid_id(submission.url)

                        if is_youtube_link:
                            channel_id = get_youtube_video_data("videos", "snippet", "id", vid_id, "channelId")                  
                            removed = False

                            if channel_id in banned_channels:
                                submission.remove(False) # checks for banned youtube channels
                                submission.add_comment(banned_channel_explain).distinguish(sticky=True)
                                print("Removing submission " + submission.id + " (banned youtube channel)..")
                                removed = True
                            elif video_is_unlisted(vid_id):
                                submission.remove(False)
                                submission.add_comment(unlisted_explain).distinguish(sticky=True)
                                print("Removing submission " + submission.short_link + " (unlisted video)..")
                                removed = True
                            elif vid_id in recent_video_data["videos"]: #submission is repost
                                my_old_post = recent_video_data["videos"][vid_id]
                                try:
                                    old_post = r.get_info(thing_id="t3_" + my_old_post.sub_ID)
                                    if old_post is None or old_post.author is None or old_post.banned_by is not None: #if old post isn't live, i.e. is removed or deleted
                                        remove_post = False # allow repost since old one is gone
                                    else: 
                                        remove_post = True # repost will be removed
                                except:
                                    remove_post = True # assume repost isn't allowed by default; will be removed

                                if remove_post: #flag to show if it should be removed
                                    submission.remove(False)
                                    comment = repost_explain.format(old_link=old_post.permalink)
                                    submission.add_comment(comment).distinguish(sticky=True)
                                    removed = True
                                    print("Removing submission " + submission.id + " (reposted video)..")

                            if not removed: #successful submission (youtube links only)
                                my_sub = my_submission_type()
                                my_sub.sub_permalink = submission.permalink
                                my_sub.sub_ID = submission.id
                                my_sub.channel_ID = channel_id
                                my_sub.date_created = submission.created_utc

                                if "[intentional]" in submission.title.lower() and is_roleplay(submission.title, vid_id):
                                    submission.set_flair("ROLEPLAY", "roleplay")
                                    print("Reflaired submission " + submission.id + " as roleplay.")
                                    
                                recent_videos_copy = recent_video_data["videos"]
                                recent_videos_copy[vid_id] = my_sub # add submission info to temporary dict
                                recent_video_data["videos"] = recent_videos_copy # copy new dict to shelve (can't add to shelve dict directly)

                                # now check if user has submitted three videos of same channel

                                if submission.author.name not in user_submission_data["submissions"]:
                                    subs = user_submission_data["submissions"]
                                    subs[submission.author.name] = [my_sub]
                                    user_submission_data["submissions"] = subs
                                else:
                                    user_submission_list = user_submission_data["submissions"][submission.author.name]
                                    count = 1 # there's already one in submission, don't forget to count that!
                                
                                    for _submission in user_submission_list:
                                        live_submission = r.get_info(thing_id="t3_" + _submission.sub_ID) #update object (might have been removed etc)

                                        if (not submission_is_deleted(live_submission.id)) and live_submission.banned_by is None: #if submission isn't deleted or removed
                                            if _submission.channel_ID == channel_id:
                                                count += 1

                                    if count >= 3: #3 or more submissions to same channel in past day
                                        submission.remove(False)
                                        submission.add_comment(spam_explain).distinguish(sticky=True)
                                        print("Removed submission " + submission.id + " and banned user /u/" + submission.author.name + " for too many links to same youtube channel")
                                    
                                        submission_links = submission.permalink + "\n\n"
                                    
                                        for s in user_submission_list:
                                            submission_links += s.sub_permalink + "\n\n"
                                            sub_to_remove = r.get_info(thing_id="t3_" + s.sub_ID)
                                            sub_to_remove.remove(False)

                                        user_submission_data["submissions"][submission.author.name] = [] #clear the list (user is banned anyway)

                                        note = "too many links to same youtube channel - 1-day ban"
                                        msg = "Warning ban for spamming links to a youtube channel"
                                        subreddit.add_ban(submission.author, duration=1, note=note, ban_message=msg)
                                        r.send_message("/r/" + subreddit.display_name, "Ban Notification", "I have banned /u/" + submission.author.name + " for spammy behaviour (submitting three links to the same youtube channel in a 24-hour period). The ban will last **1 day only**. \n\nLinks to the offending submissions:\n\n" + submission_links)
                                    else:
                                        subs = user_submission_data["submissions"]  #copy dict
                                        l = subs[submission.author.name] # get list of user submissions
                                        l.append(my_sub) #append submission to list
                                        subs[submission.author.name] = l # update dict value
                                        user_submission_data["submissions"] = subs #write dict back to shelve 
                except Exception as ex:
                    print("exception on removal of submission " + submission.short_link + " - " + str(ex))
                    
                    if "ran out of input" in str(ex).lower():
                        break

def check_messages():
    messages = list(r.get_unread()) 

    for message in messages:
        if not message.was_comment:
            user = message.author.name
            print("Message dectected from " + user)

            if ("!recommend" in message.body.lower() or "!recommend" in message.subject.lower()): # recommendation
                print("Recommending popular video")
                message_to_send = recommend_top_submission()
                message.reply(message_to_send)
            elif(message.subject == "flair request" or message.subject == "re: flair request"): # set flair
                
                global flair_errors

                using_id = False
                channel_name = message.body
                description = get_youtube_video_data("channels", "snippet", "forUsername", channel_name, "description")
                
                if description == -1:
                    description = get_youtube_video_data("channels", "snippet", "id", message.body, "description")
                    channel_name = get_youtube_video_data("channels", "snippet", "id", message.body, "title")
                    using_id = True

                if description != -1:
                    if using_id:
                        subs = int(get_youtube_video_data("channels", "statistics", "id", message.body, "subscriberCount"))
                    else:
                        subs = int(get_youtube_video_data("channels", "statistics", "forUsername", channel_name, "subscriberCount"))

                    if subs >= 1000:
                        if using_id:
                            age = days_since_youtube_channel_creation(id=message.body)
                        else:
                            age = days_since_youtube_channel_creation(name=channel_name)

                        if age > 182:

                            if using_id:
                                video_count = int(get_youtube_video_data("channels", "statistics", "id", message.body, "videoCount"))
                            else:
                                video_count = int(get_youtube_video_data("channels", "statistics", "forUsername", channel_name, "videoCount"))

                            if video_count >= 15:
                                if user_is_active(user, channel_name):
                                    if "hey /r/asmr mods!" in description.lower():
                                        try:
                                            global subreddit
                                            subreddit.set_flair(item=user, flair_text=channel_name, flair_css_class="purpleflair")
                                            subreddit.add_contributor(user)
                                            message.reply("Verification has been successful! Your flair should be applied within a few minutes, but it can sometimes take up to an hour depending on how slow reddit is being today. Please remember to remove the verification message from your channel description as soon as possible, otherwise somebody could steal your flair. Enjoy!")

                                            global lounge
                                            lounge.add_contributor(user)
                                            lounge.set_flair(item=user, flair_text=channel_name, flair_css_class="purpleflair")
                                            print("Verified and set flair for " + user)
                                        except:
                                            message.reply(flair_errors.unknown_error)
                                            r.send_message(recipient="theonefoster", subject="Failed flair assignment", message="/u/" + user + " passed flair eligibility but flair assignment failed. Please ensure their flair is set correctly on /r/asmr and /r/asmrCreatorLounge, and that they are an approved submitter on both subreddits. \n\nChannel was: " + channel_name)
                                    else:
                                        message.reply(flair_errors.no_verification)
                                        print("flair verification for " + channel_name + " failed - no verification message.")
                                else:
                                    message.reply(flair_errors.inactive)
                                    print("flair verification for " + channel_name + " failed - not enough subreddit activity.")
                            else:
                                message.reply(flair_errors.not_enough_videos.format(vid_count = str(video_count)))
                                print("flair verification for " + channel_name + " failed - not enough published videos.")
                        else:
                            message.reply(flair_errors.underage)
                            print("flair verification for " + channel_name + " failed - channel too new.")
                    else:
                        message.reply(flair_errors.not_enough_subs.format(current_subs=str(subs)))
                        print("flair verification for " + channel_name + " failed - not enough subs.")
                else:
                    message.reply(flair_errors.channel_not_found)
                    print("flair verification failed - channel not found. Message was: " + message.body)
            elif(message.subject == "delete flair"): # delete flair
                if message.body == "delete flair":
                    r.delete_flair(subreddit="asmr", user=user)
                    message.reply(flair_errors.flair_deleted)
                    print("Flair deleted for " + user)
            elif("post reply" not in message.subject) and ("username mention" not in message.subject) and ("you've been banned from" not in message.subject):
                print("Command not recognised. Message was " + message.body)
                message.reply(flair_errors.command_not_recognised)
        else:
            print("Replying to comment in messages..")
            message.reply(comment_reply).distinguish()
        message.mark_as_read()

def title_has_two_tags(title):
    title = title.lower()
    two_tags_regex = re.compile('.*\[(intentional|unintentional|roleplay|role play|media|article|discussion|question|meta|request)\].*\[(intentional|unintentional|roleplay|role play|media|article|discussion|question|meta|request)\].*', re.I)
    two_tags = (re.search(two_tags_regex, title) is not None) # search the title for two tags; if two are found set true, else set false

    if two_tags:
        if "[intentional]" in title:
            if "[roleplay]" in title or "[role play]" in title:
                return False #if the two tags are [intentional] and [roleplay] then allow it
        return True # two tags in title but not intentional and roleplay
    else:
        return False

def update_top_submissions(): # updates recommendation database. Doesn't usually need to be run unless the data gets corrupt or the top submissions drastically change.
    toplist = shelve.open("topPosts","c")
    submissions = subreddit.get_top_from_all(limit=1000)
    added_count = 0
    total_count = 0
    goal = 700

    for submission in submissions:
        total_count += 1
        print("Got submission " + submission.id + "(" + str(total_count) + ")")
        if (".youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
            try:
                result = vid_id_regex.split(submission.url)
                vid_id = result[5]
                channel_name = get_youtube_video_data("videos", "snippet", "id", vid_id, "channelTitle")
                vid_title = get_youtube_video_data("videos", "snippet", "id", vid_id, "title")
                if (channel_name != -1) and (vid_title != -1):
                    toplist[str(added_count)] = {"URL" : submission.url, "Channel": channel_name, "Title": vid_title, "Reddit Link": submission.permalink}
                    added_count += 1
                    if added_count > goal:
                        break
                else:
                    print("Youtube Exception. Bad link?")
            except Exception as e:
                print("Other exception - " + str(e))
                #traceback.print_exc()
    toplist.sync()
    toplist.close()
    print("total videos: " + str(added_count))

def recommend_top_submission():
    toplist = shelve.open("topPosts","c")

    if "1" not in list(toplist): #if the database doesn't exist
        toplist.sync()
        toplist.close()
        update_top_submissions()
        toplist = shelve.open("topPosts","c")

    rand = random.randint(0, len(toplist)-1)
    title = ''.join(char for char in toplist[str(rand)]["Title"] if char in string.printable)

    if title == "":
        title = "this video"

    rtn = "How about [" + title + "](" + (toplist[str(rand)]["URL"]) + ") by " + toplist[str(rand)]["Channel"] + "? \n\n[(Reddit link)](" + toplist[str(rand)]["Reddit Link"] + ") \n\nIf you don't like this video, reply with ""!recommend"" and I'll find you another one."
    
    toplist.sync()
    toplist.close()

    return rtn

def user_is_active(username, channel_name=""):

    return True # not fully implemented yet TODO

    if False: #so I can collapse it in VS :)
        user = r.get_redditor(username)

        time_limit = time.time()-10800000 # 125 days ago (4 months)
        old_time_limit = time.time()-2592000 # 30 days ago

        comments = list(user.get_comments(sort="new", time="year", limit=500)) # all comments by user 
        old_comments = [] # comments older than 30 days
        other_comments = [] # comments younger than 120 days on submissions other than their own
        old_other_comments = [] # comments older than 30 days and younger than 120 days and on submissions other than their own

        submissions = list(user.get_submitted(sort="new", time="year", limit=500)) #all submissions by user
        old_submissions = [] # submissions older than 30 days
        other_submissions = [] # submissions younger than 120 days to channels other than their own
        old_other_submissions = [] # submissions older than 30 days and younger than 120 days and on submissions to youtube channels other than their own

        for comment in list(comments): # copy list for iteration
            try:
                if comment.subreddit.display_name == subreddit.display_name: # if comment in /r/asmr
                    if comment.created_utc > time_limit: # and was <120 days ago 
                        if comment.link_author != username: # commented on someone else's submission
                            other_comments.append(comment) # other_comments list

                        if comment.created_utc < old_time_limit: # comment was 30<=days<120 ago
                            old_comments.append(comment) # list of comments from 30-120 days ago
                            if comment.link_author != username:
                                old_other_comments.append(comment) # old_other_comments list
                        else: # comments less than 30 days ago
                            pass # don't remove comment from comments
                    else:
                        comments.remove(comment) # remove comments from more than 120 days ago
                else:
                    comments.remove(comment) # don't care about comments in other subreddits
            except AttributeError:
                # will except e.g. if parent submission is deleted
                # must have been in /r/asmr and later than 120 days ago
                # so assume it's ok and leave it in the comments list
                pass
        for submission in list(submissions): # copy list for iteration
            if submission.subreddit.display_name == subreddit.display_name: # if submission in /r/asmr
                if submission.created_utc > time_limit: # and was <120 days ago 

                    vid_id = get_vid_id(submission.url)
                    if vid_id != -1: # if submission links to youtube. Otherwise it's a text submission or other external link
                        youtube_author = get_youtube_video_data("videos", "snippet", "id", vid_id, "channelTitle")

                        if youtube_author != channel_name: # submission of someone else's video
                            other_submissions.append(submission) # create other_submissions list

                        if submission.created_utc < old_time_limit: # submission was 30<=days<120 ago
                            old_submissions.append(submission) # create a list of submissions from 30-120 days ago
                            if youtube_author != channel_name:
                                old_other_submissions.append(submission) #create old_other_submissions list
                        else: # submissions less than 30 days ago
                            pass # don't remove submission from submissions
                    else:
                        other_submissions.append(submission)

                        if submission.created_utc < old_time_limit: 
                            old_other_submissions.append(submission)
                else:
                    submissions.remove(submission) # remove submissions from more than 120 days ago
            else:
                submissions.remove(submission) #don't care about submissions in other subreddits

        # comments now contains all comments by user in /r/asmr after 90 days ago
        # old_comments is a subset of comments in /r/asmr containing comments from before 30 days ago
        # ditto for submissions

        if  (      len(comments) < 8 # at least 2 overall comments per month
                or len(old_comments) < 6  # at least 2 historical comments per month
                or len(submissions) < 4 # at least 1 submission per month
                or len(old_submissions) < 3 # at least 1 historical submissions per month
            ):#    or len(other_comments) < 4 # at least 1 communal comment per month overall
              #  or len(old_other_comments) < 3 # at least 1 historical communal comment per month (on someone else's submission)
              #  or len(other_submissions) < 2 # at least 2 overall communal submissions
              #  or len(old_other_submissions) < 1 # at least 1 historical communal submissions
           # ): #sad
                return False
        else:
            return True

def user_is_shadowbanned(username):
    try:
        user = r.get_redditor(user_name=username, fetch=True)
        return False
    except praw.errors.HTTPException:
        return True
    except Exception as e:
        print("\n\nUnknown exception when checking shadowban for user {user_name} - exception code: \"{code}\"\n\n".format(user_name=username, code=str(e)))
        #traceback.print_exc()
        return False

def submission_is_deleted(id):
    try:
        submission = r.get_submission(submission_id = id)
        return (submission.author is None)
    except praw.errors.InvalidSubmission:
        return True

def add_warning(post): # post is a reddit 'thing' (comment or submission) for which the author is receiving a warning
    user = post.author.name
    ordinal = "?"

    warnings_cursor.execute("SELECT * FROM warnings WHERE name=?", [user])
    result = warnings_cursor.fetchone()
    
    note = "Auto-ban: {ordinal} - " + post.short_link

    if not result:
        ordinal = "First warning"
        post.remove(False)
        warnings_cursor.execute("INSERT INTO warnings VALUES(?,?)", [user, 1])
        note = "Auto-ban: first warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). This is your first warning, which is accompanied by a 7-day subreddit ban. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again. If you message the moderators referencing the rule that you broke and how you broke it, we **may consider** unbanning you early."
        subreddit.add_ban(post.author, duration=7, note=note.format(ordinal=ordinal), ban_message=msg)
    elif result[1] >= 2:
        ordinal = "Permanent"
        post.remove(False)
        warnings_cursor.execute("DELETE FROM warnings WHERE name=?", [user])
        warnings_cursor.execute("INSERT INTO warnings VALUES(?,?)",  [user, 3])
        msg = "You have been automatically banned because of your post [here](" + post.permalink + "). This is your third warning, meaning you are now permanently banned."
        subreddit.add_ban(post.author, note=note.format(ordinal=ordinal), ban_message=msg)
    elif result[1] == 1:
        ordinal = "Second warning"
        post.remove(False)
        warnings_cursor.execute("DELETE FROM warnings WHERE name=?", [user])
        warnings_cursor.execute("INSERT INTO warnings VALUES(?,?)",  [user, 2])
        note = "Auto-ban: Final warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). **This is your final warning**. You will be banned for the next 30 days; if you receive another warning, you will be permanently banned. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
        subreddit.add_ban(post.author, duration=30, note=note.format(ordinal=ordinal), ban_message=msg)
    warnings_db.commit()
    print(ordinal + " ban added for " + user)

def is_bad_title(title):
    title = title.lower()
    if any(phrase in title for phrase in ["[intentional]", "[unintentional]", "[roleplay]", "[role play]"]):
        for phrase in bad_title_phrases:
            if phrase in title:
                return True
    return False

def is_banned_link(url):
    if (    (   ".youtube." in url 
             or "youtu.be"  in url
            )
        and ("playlist" in url
             or "list=" in url 
             or "/channel/" in url 
             or "/user/" in url
            )
       ): # sad
        return True
    else:
        return False

def is_roleplay(title, vid_id):
    try:
        title = title.lower()
        rp_types = ["role play", "roleplay", "role-play", " rp ", "rp."]
        if "[intentional]" in title: #only care about submissions tagged [intentional]
            if any(rp in title for rp in rp_types):
                return True
            else:
                vid_title = get_youtube_video_data("videos", "snippet", "id", vid_id, "title")
                if vid_title != -1:
                    vid_title = vid_title.lower()
                    if "roleplay" in vid_title or "role play" in vid_title:
                        return True
                    else:
                        tags = get_youtube_video_data("videos", "snippet", "id", vid_id, "tags")
                        if tags != -1:
                            return any(rp in tags for rp in rp_types) #true if roleplay in tags; false otherwise
        return False
    except:
        return False

def purge_thread(comment): # recursion is cool
    for c in comment.replies:
        purge_thread(c)
    comment.remove(False)

def get_comment_from_submission(comment):
    s = comment.submission
    i = comment.id
    for c in s.comments:
        if c.id == i:
            return c # Yes, this is completely dumb. No, there's no other way to do it.
    return None      # Yes, the reddit api is weird sometimes. Just don't worry about it too much.

def remove_tech_tuesday():
    sticky = subreddit.get_sticky()
    try:
        if "Tech Tuesday" in sticky.title:
            sticky.unsticky()
        else:
            sticky = subreddit.get_sticky(bottom=True) # get second sticky
            if "Tech Tuesday" in sticky.title:
                sticky.unsticky()
    except praw.errors.HTTPException as e: # if there's no sticky it'll throw a 404 Not Found
        pass

def remove_ffaf(): #can't use parameter in shedules so need separate functions
    sticky = subreddit.get_sticky()
    try:
        if "Free-For-All Friday" in sticky.title:
            sticky.unsticky()
        else:
            sticky = subreddit.get_sticky(bottom=True) # get second sticky
            if "Free-For-All Friday" in sticky.title:
                sticky.unsticky()
    except praw.errors.HTTPException as e: # if there's no sticky it'll throw a 404 Not Found
        pass

def clear_user_submissions():
    # user_submission_data is a dict containing usernames as keys and lists as values
    # Each user's dict value is a list of my_submission_type objects, representing 
    # every submission they've made in the last 24 hours

    submissions = user_submission_data["submissions"]

    for user in list(submissions.keys()):
        if user == "un" and len(users) > 2: #if database is reset, dummy data is inserted as a placeholder. Remove this.
            del submissions["un"]
            continue
        submissions_by_user = submissions[user] 
        temp = list(submissions_by_user)
        for s in temp:
            if s.date_created < (time.time()-86400): #if the submission was over 24 hours ago
                submissions_by_user.remove(s) # remove it from the list

        if len(submissions_by_user) == 0: # and if there are no submissions by that user in the past 24 hours
            del submissions[user] # remove the user's key from the dict       
        elif len(submissions[user]) != len(submissions_by_user):
                submissions[user] = submissions_by_user # update submissions log

    user_submission_data["submissions"] = submissions

def update_seen_objects():
    done_submissions = seen_objects["submissions"][-100:] # trim to only 100 subs
    seen_objects["submissions"] = done_submissions
    done_comments = seen_objects["comments"][-100:] # trim to only 100 comments
    seen_objects["comments"] = done_comments
    seen_objects.sync()

def clear_video_submissions():
    submissions_dict = recent_video_data["videos"]

    dict_keys = list(submissions_dict.keys())
    
    for key in dict_keys:
        if key == "id" and len(dict_keys) > 2:
            del submissions_dict[key]
        elif submissions_dict[key].date_created < (time.time() - 7948800): #if submission was more than 3 months ago
            del submissions_dict[key]

    recent_video_data["videos"] = submissions_dict

def get_banned_channels():
    try:
        global banned_channels
        wiki = subreddit.get_wiki_page("banned")
        banned_channels = eval(wiki.content_md)
    except Exception as ex:
        r.send_message(recipient="theonefoster", subject="Error getting banned channels", message="Exeption when getting banned channels!\n\n" + str(ex) + "\n\n /r/asmr/wiki/banned")

def login():
    print("logging in..")
    r = praw.Reddit(app_user_agent, disable_update_check=True)
    r.set_oauth_app_info(app_id, app_secret, app_URI)
    r.refresh_access_information(app_refresh_token)
    print("logged in as " + str(r.user.name))
    return r

def asmr_bot():
    schedule.run_pending()
    check_submissions()
    check_comments()
    check_messages()
    check_mod_queue()

# ----------------------------
# END OF FUNCTIONS
# ----------------------------

r = login()
subreddit = r.get_subreddit("asmr")

if __name__ == "__main__":
    tof = theonefoster_bot.login()
    del(theonefoster_bot)
    lounge = r.get_subreddit("asmrcreatorlounge")

    print("Fetching banned channels..")
    get_banned_channels()

    schedule.every().thursday.at("23:50").do(remove_ffaf)
    schedule.every().wednesday.at("18:00").do(remove_tech_tuesday)
    schedule.every(14).days.at("03:00").do(update_top_submissions) #once per fortnight ish
    schedule.every().hour.do(clear_user_submissions)
    schedule.every().day.do(update_seen_objects)
    schedule.every().day.at("02:00").do(clear_video_submissions) #once per day
    schedule.every().hour.do(get_banned_channels)

    print("Setup complete. Starting bot duties.")

    while True:
        try:
            asmr_bot()
        except praw.errors.HTTPException as e:
            try:
                print("HTTP Exception: " + str(e))
                traceback.print_exc()
                r = login()
            except Exception as f:
                print("Login failed: " + str(f))
                print ("Sleeping....")
                time.sleep(30)
        except Exception as e:
            print("Unknown exception: " + str(e))
            #traceback.print_exc()
            try:
                r = login()
            except Exception as f:
                print(str(f))
                print("Sleeping..")
                time.sleep(30) # usually 503. Sleeping reduces reddit load.
        finally:
            r.handler.clear_cache()

            recent_video_data.sync()
            user_submission_data.sync()
            seen_objects.sync()

            recent_video_data.close()
            user_submission_data.close()
            seen_objects.close()

            user_submission_data = shelve.open("user_submission_data", "c") # all submissions from past day by author
            recent_video_data = shelve.open("recent_video_data", "c") # videos submitted over past 3 months
            seen_objects = shelve.open("seen_objects", "c") # track which objects have been seen

            first_run = False

            time.sleep(8) # reduces reddit load and unnecessary processor usage
