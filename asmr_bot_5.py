# for /u/asmr_bot 
# REQUIRES PRAW 5.4 OR LATER
import praw
import prawcore
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

class my_submission_type():
    sub_permalink = ""
    sub_ID = ""
    channel_ID = ""
    date_created = ""

# PRAW details, other imported data
bad_title_phrases = d.bad_title_phrases
banned_channels = d.BANNED_CHANNELS

# gdata details
g_browser_key = d.g_browser_key

# global variables
mod_list = {'theonefoster', 'nvadergir', 'mahi-mahi', 'asmr_bot', 'underscorewarrior', 'roflbbq', 'unicornica', 'automoderator'}
viewed_mod_queue = set()
modqueue_is_full = True # if bot is restarted it will wait for empty modqueue before full queue notifications begin
unactioned_modqueue = queue.Queue(0)
first_run = True # does a lot more processing on first run to catch up with anything missed during downtime
first_run_backcheck = 100
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
replies = d.messages
comment_reply = d.comment_reply
taggable_channels = d.linkable_channels
capital_explain = d.CAPITAL_TITLE
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

if "submissions" not in user_submission_data: # initialise dict
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

warnings_db = sqlite3.connect('warnings.db', detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES) # for warnings database (bad if corrupted so not using shelve as it's lost data in the past)
warnings_cursor = warnings_db.cursor()
warnings_cursor.execute("CREATE TABLE IF NOT EXISTS warnings(NAME TEXT, LINK TEXT, BANNING_MOD TEXT, REASON TEXT, DATE DATE)")
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
        if return_val == "all":
            return snippet
        else:
            rtn = snippet[return_val]
            return rtn
    except Exception as e:
        # traceback.print_exc()
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

def check_mod_queue(): #tested - works
    global modqueue_is_full
    global unactioned_modqueue
    global seen_objects
    global user_submission_data
    global recent_video_data # shouldn't really need these but seems not to work on linux without them
    
    modqueue = list(subreddit.mod.modqueue()) #modqueue is a list of comments. Each comment has attributes mod_reports and user_reports, which are lists. Each is a list of reports, where each report is a list of ["report reason", int:num reports].
 
    for item in modqueue:
        if item.fullname not in viewed_mod_queue:
            print("New modqueue item!")
            viewed_mod_queue.add(item.fullname)

            #for 4 hours in future:
            hour = str((time.struct_time(time.strptime(time.ctime())).tm_hour + 4)%24)
            min = str(time.struct_time(time.strptime(time.ctime())).tm_min)

            #for 1 min in future (for testing):
            #hour = str((time.struct_time(time.strptime(time.ctime())).tm_hour)%24)
            #min = str((time.struct_time(time.strptime(time.ctime())).tm_min + 1)%60)

            schedule_time = hour+":"+min
            
            unactioned_modqueue.put(item)

            schedule.every().day.at(schedule_time).do(check_old_mod_queue_item)

            if len(modqueue) >= 4 and modqueue_is_full == False:
                print("Full modqueue detected! Messaging mods..")
                subject = "Modqueue items require attention! (bot v5.0)"
                message = "The modqueue has multiple unactioned items in it - please review them asap! \n\n https://www.reddit.com/r/asmr/about/modqueue/"
                subreddit.message(subject=subject, message=message)
                modqueue_is_full = True
            elif len(modqueue) <=3:
                modqueue_is_full = False

def check_old_mod_queue_item(): #tested - works
    submission = unactioned_modqueue.get()
    modqueue = list(subreddit.mod.modqueue())
    for item in modqueue:
        if item.id == submission.id:
            print("Modqueue item unactioned for 4 hours - messaging mods")
            subject = "Unactioned Modqueue Item (bot v5.0)"
            message = "Attention - a modqueue item hasn't been actioned for 4 hours. Please review it asap!\n\nhttps://www.reddit.com/r/asmr/about/modqueue/"
            subreddit.message(subject=subject, message=message)
    return schedule.CancelJob

def check_comments():
    global first_run
    global seen_objects
    global user_submission_data
    global recent_video_data # shouldn't really need these but seems not to work on linux without them

    limit = first_run_backcheck if first_run else 6

    comments = list(subreddit.comments(limit=limit)) # sends request  

    for comment in comments:
        if comment.id not in seen_objects["comments"]:
            seen_comments = seen_objects["comments"]
            seen_comments.append(comment.id)
            seen_objects["comments"] = seen_comments
            seen_objects.sync()

            try:
                comment_author = comment.author.name.lower()
                comment_body = comment.body.lower()

                # public commands:
                if any(comment_body == x for x in ["ayy", "ayyy", "ayyyy", "ayyyyy"]):
                    print("Responding to ayy by /u/" + comment_author)
                    comment.reply("lmao").mod.distinguish()
                    continue

#                if comment_author != "asmr_bot":
#                    reply = link_youtube_channel(comment_body)

#                    # Reply will be the proposed reply to the comment
#                    # if no reply is needed it will be empty
#                    # so "if reply" will evaluate to False
#                    if reply:
#                        print("Replying to tagged channel..")
#                        comment.reply(reply).distinguish()
#                        continue # don't carry out further checks
                    
                # moderator commands
                if (comment_author in mod_list) and comment.banned_by is None: #if mod comment not removed..
                    if comment.is_root:
                        #commands which can only be used at the top-level (as comments in reply to submissions)
                        if comment_body.startswith("!meta"):
                            print("Removing submission in response to " + comment_author + " (bad meta post)")
                            remove_mod_comment(comment)
                            submission = r.submission(id=comment.parent_id[3:]) #will break here if command is not top-level comment
                            submission.mod.remove()
                            submission.reply(meta_explain.format(mod=comment_author)).mod.distinguish()
                        elif comment_body.startswith("!music"):
                            print("Removing submission in response to " + comment_author + " (music)")
                            remove_mod_comment(comment)
                            submission = r.submission(id=comment.parent_id[3:])
                            submission.mod.remove()
                            submission.reply(mus_explain.format(mod=comment_author)).mod.distinguish()
                        elif comment_body.startswith("!title"):
                            print("Removing submission in response to " + comment_author + " (bad title)")
                            remove_mod_comment(comment)
                            submission = r.submission(id=comment.parent_id[3:])
                            submission.mod.remove()
                            submission.reply(mod_title_explain.format(mod=comment_author)).mod.distinguish()
                    if comment_body.startswith("!remove"):
                        print("Removing submission in response to " + comment_author + " (remove by command)")
                        remove_mod_comment(comment)
                        parent = get_parent(comment)
                        parent.mod.remove()
                    elif comment_body.startswith("!warning"):
                        reason = comment_body[9:]
                        remove_mod_comment(comment)
                        parent = get_parent(comment)
                        if not user_is_subreddit_banned(parent.author.name):
                            # comment_author is mod who is giving the warning
                            print("Removing post in response to " + comment_author + " (add warning)")
                            parent.mod.remove()
                            new_warning(parent, comment_author, reason, False)
                        else:
                            print("Not adding warning in response to " + comment_author + " - user /u/" + parent.author.name + " is already banned.")
                            r.redditor(comment_author).message(subject="Warning not added", message="No warning ban for /u/" + parent.author.name + " was added because that user is already banned. Their comment and your command have been removed.")

                    elif comment_body.startswith("!purge"):
                        print("Removing comment tree in response to " + comment_author + " (kill thread)")
                        try:
                            parent = get_parent(comment)
                            if parent.fullname[:2] == "t1":# comment
                                parent.refresh()
                                purge_thread(parent)
                            else:
                                r.redditor(comment_author).message(subject="Failed command", message="The !purge command can only be used in reply to a comment. It cannot be a top-level comment.") # todo: wat
                           
                            remove_mod_comment(comment)
                        except Exception as e:
                            print("Exception when purging comment tree - "+str(e)+"\nParent was " + parent.id)
                            # traceback.print_exc()
                            r.send_message(recipient=comment_author, subject="Failed command", message="Your purge command failed for an unknown reason. Your comment was removed.")
                        finally:
                            comment.mod.remove()
                    elif comment_body.startswith("!ban"):
                        reason = comment_body[5:]
                        if reason == "":
                            reason = "<No reason given>"

                        parent = get_parent(comment)

                        ban_user = parent.author.name
                        msg = "You have been banned by {mod} for [your post here]({link}). The moderator who banned you provided the following reason:\n\n**{reason}**"

                        try:
                            print("Banning user {ban_user} for post {post}. Reason give: ""{reason}""".format(ban_user=ban_user, post=parent.id, reason=reason))
                            parent.mod.remove(False)
                            remove_mod_comment(comment)
                        
                            note = comment.author.name + ": " + reason + ": " + parent.permalink
                            subreddit.banned.add(redditor=ban_user, note=note, ban_message=msg.format(mod=comment.author.name, link=parent.permalink, reason=reason))

                            message = "I have permanently banned {ban_user} for their [post here]({ban_post}?context=9) in response to [your comment here]({comment}?context=9), with the reason: \n\n\> {reason} \n\n Ban list: /r/asmr/about/banned"

                            r.redditor(comment_author).message(subject="Ban successful", message=message.format(ban_user=ban_user, ban_post=parent.permalink, comment=comment.permalink, reason=reason))
                        except PermissionError:
                            r.send_message(recipient=comment_author, subject="Ban failed", message="You issued a command [here]({link}) in which you tried to ban a moderator, which is not possible.".format(link=comment.permalink))
                        except praw.exceptions.APIException as ex:
                            if ex.error_type == "CANT_RESTRICT_MODERATOR":
                                r.send_message(recipient=comment_author, subject="Ban failed", message="You issued a command [here]({link}) in which you tried to ban a moderator, which is not possible.".format(link=comment.permalink))
                            else:
                                raise #act as if the exception was never caught here
                    else:
                        if any(comment_body.startswith(command) for command in ["!meta", "!music", "!title"]):
                            print("Invalid command from " + comment_author + " - submission command in reply to comment.")
                            r.redditor(comment.author.name).message(subject="Invalid bot command", message="You issued a command [here]({link}) in reply to a comment, but that command can only be used in reply to a submission. Please re-issue the command as a top-level comment.".format(link=comment.permalink))
                            remove_mod_comment(comment)
                       

            except AttributeError as ex: # if comment has no author (is deleted) (comment.author.name returns AttributeError), do nothing
                print("Attribute Error! Comment was probably deleted. Comment was " + str(comment.fullname))
                print(str(ex))
                # traceback.print_exc()
    
#def check_submissions():
#    global first_run
#    global recent_video_data
#    global user_submission_data
#    global seen_objects # shouldn't really need these but seems not to work on linux without them

#    limit = first_run_backcheck if first_run else 6

#    submissions = list(subreddit.get_new(limit=limit))

#    for submission in submissions:
#        if submission.id not in seen_objects["submissions"]: 
#            seen_submissions = seen_objects["submissions"]
#            seen_submissions.append(submission.id)
#            seen_objects["submissions"] = seen_submissions
#            seen_objects.sync()
            
#            # for each new submission..
#            if(title_has_two_tags(submission.title)):
#                submission.remove(False)
#                submission.add_comment(two_tags_explain).distinguish(sticky=True)
#                print("Removed submission " + submission.id + " for having two flair tags.")
#            elif is_bad_title(submission.title):
#                submission.remove(False)
#                submission.add_comment(auto_title_explain).distinguish(sticky=True)
#                r.send_message(recipient="theonefoster", subject="Bad title - submission removed", message=submission.permalink + "\n\nTitle was: \"**" + submission.title + "**\"")
#                print("Removed submission " + submission.id + " for having a bad title.")
#            elif title_is_caps(submission.title):
#                submission.remove(False)
#                submission.add_comment(capital_explain).distinguish(sticky=True)
#                r.send_message(recipient="theonefoster", subject="Upper case title - submission removed", message=submission.permalink + "\n\nTitle was: \"**" + submission.title + "**\"")
#                print("Removed submission " + submission.id + " for having an uppercase title.")
#            elif ("youtube" in submission.url or "youtu.be" in submission.url):
#                try:
#                    if is_banned_link(submission.url):
#                        submission.remove(False)
#                        submission.add_comment(channel_or_playlist_explain).distinguish(sticky=True)
#                        print("Removed submission " + submission.id + " (link to channel/playlist)")
#                    else:
#                        vid_id = get_vid_id(submission.url)
#                        channel_id = get_youtube_video_data("videos", "snippet", "id", vid_id, "channelId")                  
#                        removed = False

#                        if channel_id in banned_channels:
#                            submission.remove(False) # checks for banned youtube channels
#                            submission.add_comment(banned_channel_explain).distinguish(sticky=True)
#                            print("Removed submission " + submission.id + " (banned youtube channel)")
#                            removed = True
#                        elif video_is_unlisted(vid_id):
#                            submission.remove(False)
#                            submission.add_comment(unlisted_explain).distinguish(sticky=True)
#                            print("Removed submission " + submission.shortlink + " (unlisted video)")
#                            removed = True
#                        elif vid_id in recent_video_data["videos"]: # submission is repost
#                            my_old_post = recent_video_data["videos"][vid_id]
#                            try:
#                                old_post = r.get_info(thing_id="t3_" + my_old_post.sub_ID)
#                                if old_post is None or old_post.author is None or old_post.banned_by is not None: # if old post isn't live, i.e. is removed or deleted
#                                    remove_post = False # allow repost since old one is gone
#                                else: 
#                                    if old_post.permalink == submission.permalink:
#                                        continue
#                                    else:
#                                        remove_post = True # repost will be removed
#                            except:
#                                remove_post = False # assume repost is allowed by default; won't be removed

#                            if remove_post: # flag to show if it should be removed
#                                submission.remove(False)
#                                comment = repost_explain.format(old_link=old_post.permalink)
#                                submission.add_comment(comment).distinguish(sticky=True)
#                                removed = True
#                                print("Removed submission " + submission.id + " (reposted video)")

#                        if not removed: # successful submission (youtube links only)
#                            my_sub = my_submission_type()
#                            my_sub.sub_permalink = submission.permalink
#                            my_sub.sub_ID = submission.id
#                            my_sub.channel_ID = channel_id
#                            my_sub.date_created = submission.created_utc

#                            time.sleep(1)
#                            submission.refresh() #I wonder if this will solve the "Nonetype has no attribute 'lower()'" issue..

#                            if submission.link_flair_text.lower() != "roleplay" and "[intentional]" in submission.title.lower() and is_roleplay(submission.title, vid_id):
#                                submission.set_flair("ROLEPLAY", "roleplay")
#                                print("Reflaired submission " + submission.id + " as roleplay.")
                                    
#                            recent_videos_copy = recent_video_data["videos"]
#                            recent_videos_copy[vid_id] = my_sub # add submission info to temporary dict
#                            recent_video_data["videos"] = recent_videos_copy # copy new dict to shelve (can't add to shelve dict directly)

#                            # now check if user has submitted three videos of same channel
                                
#                            if submission.author.name not in user_submission_data["submissions"]:
#                                subs = user_submission_data["submissions"]
#                                subs[submission.author.name] = [my_sub]
#                                user_submission_data["submissions"] = subs
#                            else:
#                                user_submission_list = user_submission_data["submissions"][submission.author.name]
#                                count = 1 # there's already one in submission, don't forget to count that!
                                
#                                for _submission in user_submission_list:
#                                    live_submission = r.get_info(thing_id="t3_" + _submission.sub_ID) # update object (might have been removed etc)

#                                    if (not submission_is_deleted(live_submission.id)) and live_submission.banned_by is None: # if submission isn't deleted or removed
#                                        if _submission.channel_ID == channel_id:
#                                            count += 1

#                                if count >= 3: # 3 or more submissions to same channel in past day
                                        
#                                    submission_links = submission.permalink + "\n\n" #start the newline-separated list of submission links
                                    
#                                    for s in user_submission_list:
#                                        submission_links += s.sub_permalink + "\n\n"
#                                        sub_to_remove = r.get_info(thing_id="t3_" + s.sub_ID)
#                                        sub_to_remove.remove(False)

#                                    user_submission_data["submissions"][submission.author.name] = [] # clear the list (user is banned anyway)

#                                    submission.remove(False)
#                                    submission.add_comment(spam_explain).distinguish(sticky=True) # doesn't mention ban length
#                                    duration = new_warning(submission, "asmr_bot", "spam", spam_warning=True)

#                                    if duration == 1:
#                                        duration = "1 day only"
#                                    else:
#                                        duration = str(duration) + " days"

#                                    r.send_message("/r/" + subreddit.display_name, "Ban Notification", "I have banned /u/" + submission.author.name + " for spammy behaviour (submitting three links to the same youtube channel in a 24-hour period). The ban will last **" + duration + "**.\n\nLinks to the offending submissions:\n\n" + submission_links + "\n\n/r/asmr/about/banned")

#                                    print("Removed submission " + submission.id + " and banned user /u/" + submission.author.name + " for too many links to same youtube channel")
                                        
#                                else:
#                                    subs = user_submission_data["submissions"]  # copy dict
#                                    l = subs[submission.author.name] # get list of user submissions
#                                    l.append(my_sub) # append submission to list
#                                    subs[submission.author.name] = l # update dict value
#                                    user_submission_data["submissions"] = subs # write dict back to shelve 
#                except Exception as ex:
#                    print("exception on processing of submission " + submission.shortlink + " - " + str(ex))
                    
#                    if "ran out of input" in str(ex).lower():
#                        break

#def check_messages():
#    messages = list(r.get_unread()) 

#    for message in messages:
#        try:
#            if not message.was_comment:
#                user = message.author.name
#                print("Message dectected from " + user)

#                if ("!recommend" in message.body.lower() or "!recommend" in message.subject.lower()): # recommendation
#                    print("Recommending popular video to " + message.author.name)
#                    message_to_send = recommend_top_submission()
#                    message.reply(message_to_send)
#                elif(message.subject == "flair request" or message.subject == "re: flair request"): # set flair
                
#                    global replies

#                    using_id = False
#                    channel_name = message.body.replace(" ", "").replace(".", "")
#                    description = get_youtube_video_data("channels", "snippet", "forUsername", channel_name, "description")
                
#                    if description == -1:
#                        description = get_youtube_video_data("channels", "snippet", "id", message.body, "description")
#                        channel_name = get_youtube_video_data("channels", "snippet", "id", message.body, "title")
#                        using_id = True

#                    if description != -1:
#                        if using_id:
#                            subs = int(get_youtube_video_data("channels", "statistics", "id", message.body, "subscriberCount"))
#                        else:
#                            subs = int(get_youtube_video_data("channels", "statistics", "forUsername", channel_name, "subscriberCount"))

#                        if subs >= 1000:
#                            if using_id:
#                                age = days_since_youtube_channel_creation(id=message.body)
#                            else:
#                                age = days_since_youtube_channel_creation(name=channel_name)

#                            if age > 182:

#                                if using_id:
#                                    video_count = int(get_youtube_video_data("channels", "statistics", "id", message.body, "videoCount"))
#                                else:
#                                    video_count = int(get_youtube_video_data("channels", "statistics", "forUsername", channel_name, "videoCount"))

#                                if video_count >= 15:
#                                    if not user_is_too_new(message.author):
#                                        if "hey /r/asmr mods!" in description.lower():
#                                            try:
#                                                global subreddit
#                                                subreddit.set_flair(item=user, flair_text=channel_name, flair_css_class="purpleflair")
#                                                subreddit.add_contributor(user)
#                                                message.reply("Verification has been successful! Your flair should be applied within a few minutes, but it can sometimes take up to an hour depending on how slow reddit is being today. Please remember to remove the verification message from your channel description as soon as possible, otherwise somebody could steal your flair. Enjoy!")

#                                                global lounge
#                                                lounge.add_contributor(user)
#                                                lounge.set_flair(item=user, flair_text=channel_name, flair_css_class="purpleflair")
#                                                print("Verified and set flair for " + user)
#                                            except:
#                                                message.reply(replies.unknown_error)
#                                                r.send_message(recipient="theonefoster", subject="Failed flair assignment", message="/u/" + user + " passed flair eligibility but flair assignment failed. Please ensure their flair is set correctly on /r/asmr and /r/asmrCreatorLounge, and that they are an approved submitter on both subreddits. \n\nChannel was: " + channel_name)
#                                        else:
#                                            message.reply(replies.no_verification)
#                                            print("flair verification for " + channel_name + " failed - no verification message.")
#                                    else:
#                                        message.reply(replies.inactive)
#                                        print("flair verification for " + channel_name + " failed - account is too new.")
#                                else:
#                                    message.reply(replies.not_enough_videos.format(vid_count = str(video_count)))
#                                    print("flair verification for " + channel_name + " failed - not enough published videos.")
#                            else:
#                                message.reply(replies.underage)
#                                print("flair verification for " + channel_name + " failed - channel too new.")
#                        else:
#                            message.reply(replies.not_enough_subs.format(current_subs=str(subs)))
#                            print("flair verification for " + channel_name + " failed - not enough subs.")
#                    else:
#                        message.reply(replies.channel_not_found)
#                        print("flair verification failed - channel not found. Message was: " + message.body)
#                elif(message.subject == "delete flair"): # delete flair
#                    if message.body == "delete flair":
#                        r.delete_flair(subreddit="asmr", user=user)
#                        message.reply(replies.flair_deleted)
#                        print("Flair deleted for " + user)
#                elif("post reply" not in message.subject) and ("username mention" not in message.subject) and ("you've been banned from" not in message.subject):
#                    print("Command not recognised. Message was " + message.body)
#                    message.reply(replies.command_not_recognised)
#            else:
#                print("Replying to comment in messages..")
#                message.reply(comment_reply).distinguish()
#        except:
#            pass
#        finally:
#            message.mark_as_read()

def remove_mod_comment(comment):
    """If comment was made by me, I have the authentication to delete it, which is preferred. 
    Otherwise Remove it since I can't delete other mods' comments
    """
    if comment.author.name == "theonefoster":
        my_comment = tof.comment(id = comment.id) #re-fetch the comment with my personal credentials
        my_comment.delete() #delete comment while authenticated as u/theonefoster
    else:
        comment.mod.remove()

def get_parent(comment):
    """Returns the parent comment or submission of a given comment"""

    if comment.parent_id[:2] == "t1": #comment
        return r.comment(id=comment.parent_id[3:])
    elif comment.parent_id[:2] == "t3": #submission
        return r.submission(id=comment.parent_id[3:])
    else:
        return None

#def link_youtube_channel(comment):
#    TODO: do a youtube search for the channel rather than a lookup
#    m = re.compile("\[\[([^\]]*)\]\]")
#    matches = re.findall(m, comment)
#    channels = {}

#    for channel in matches:
#        for name_list in taggable_channels:
#            if channel in name_list:
#                channels[channel] = taggable_channels[name_list]
#                break # breaks out of the for name_list loop

#    footer = "\n\n----\n\n[^Add ^a ^channel ^to ^be ^tagged!](/r/asmr/wiki/channel_tags) ^| [^Broken ^link? ^Let ^me ^know](https://www.reddit.com/message/compose?to=theonefoster&subject=broken tag link)"

#    if len(channels) > 0:

#        if len(channels) > 1: # multiple matches
#            reply = "Here is a list of the youtube channels you tagged:\n\n{list}"
#        else: # one match
#            reply = "Here is the youtube channel you tagged:\n\n{list}"

#        list = ""
#        url = "https://www.youtube.com/channel/{id}"

#        for channel in channels.keys():
#            link = url.format(id = channels[channel])
#            list += "* [{channel}]({link})\n\n".format(channel=channel.title(), link=link)

#        return reply.format(list=list) + footer
#    else:
#        return ""
    
#def update_top_submissions(): # updates recommendation database. Doesn't usually need to be run unless the data gets corrupt or the top submissions drastically change.
#    toplist = shelve.open("topPosts","c")
#    submissions = subreddit.get_top_from_all(limit=1000)
#    added_count = 0
#    total_count = 0
#    goal = 700

#    for submission in submissions:
#        total_count += 1
#        print("Got submission " + submission.id + "(" + str(total_count) + ")")
#        if (".youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
#            try:
#                result = vid_id_regex.split(submission.url)
#                vid_id = result[5]
#                vid_data = get_youtube_video_data("videos", "snippet", "id", vid_id, "all")
#                if vid_data != -1:
#                    channel_name = vid_data["channelTitle"]
#                    vid_title = vid_data["title"]
#                    toplist[str(added_count)] = {"URL" : submission.url, "Channel": channel_name, "Title": vid_title, "Reddit Link": submission.permalink}
#                    added_count += 1
#                    if added_count > goal:
#                        break
#                else:
#                    print("Youtube Exception. Bad link?")
#            except Exception as e:
#                print("Other exception - " + str(e))
#                # traceback.print_exc()
#    toplist.sync()
#    toplist.close()
#    print("total videos: " + str(added_count))

#def recommend_top_submission():
#    toplist = shelve.open("topPosts","c")

#    if "1" not in list(toplist): # if the database doesn't exist
#        toplist.sync()
#        toplist.close()
#        update_top_submissions()
#        toplist = shelve.open("topPosts","c")

#    rand = random.randint(0, len(toplist)-1)
#    title = ''.join(char for char in toplist[str(rand)]["Title"] if char in string.printable)

#    if title == "":
#        title = "this video"

#    rtn = "How about [" + title + "](" + (toplist[str(rand)]["URL"]) + ") by " + toplist[str(rand)]["Channel"] + "? \n\n[(Reddit link)](" + toplist[str(rand)]["Reddit Link"] + ") \n\nIf you don't like this video, reply with ""!recommend"" and I'll find you another one."
    
#    toplist.sync()
#    toplist.close()

#    return rtn

#def user_is_too_new(user):
#    if user.created_utc > time.time()-(60*60*24*182): #account is LESS than 6 months (182 days) old
#        return True
#    else:
#        return False # not fully implemented yet TODO

#def submission_is_deleted(id):
#    try:
#        submission = r.get_submission(submission_id = id)
#        return (submission.author is None)
#    except praw.errors.InvalidSubmission:
#        return True

def new_warning(post, banning_mod, reason="", spam_warning=False):
    user = post.author.name.lower()

    if type(banning_mod) != type(""):
        raise TypeError("banning_mod must be of type string")
    
    if user in mod_list:
        raise PermissionError("Error on ban attempt - cannot ban moderator " + user)

    if reason == "spam" and banning_mod != "asmr_bot": #only asmr_bot can give spam warnings, which are identified by the reason of "spam"
        reason = "spamming"

    if spam_warning:
        msg_intro = "You have received an automatic warning ban for spamming links to a youtube channel after your post [here]({link}).\n\n"
    else:
        msg_intro = "You have received an automatic warning ban because of your post [here]({link}).\n\n"

    if reason != "":
        reason_text = "The moderator who invoked this ban, /u/{mod}, gave the following reason: **\"" + reason + "\"**\n\n"
    else:
        reason_text = "The moderator who invoked this ban, /u/{mod}, did not provide a reason for the ban.**\n\n"
        if spam_warning:
            reason = "spam"
        else:
            reason = "<No reason provided>"

    link = ""
    note = "{mod} - {reason} - {link}"

    if "t3" == post.fullname[:2]: # submission
        link = post.shortlink
    else: # comment
        link = post.permalink

    note = note.format(mod=banning_mod, reason=reason, link=link)
    msg_intro = msg_intro.format(link=link)
    reason_text = reason_text.format(mod=banning_mod)

    #at this point, got user, note, link, msg_intro, reason_text. Need number of previous bans, so..

    warnings_cursor.execute("SELECT * FROM warnings WHERE name=?", [user])
    db_result = warnings_cursor.fetchall()

    has_spam_warning = False
    previous_bans = 0

    for ban in db_result: #count number of previous bans (excluding one spam ban)
        if ban[3] == "spam":
            if not has_spam_warning:
                has_spam_warning = True
            else:
                previous_bans += 1
        else:
            previous_bans += 1

    spam_warning_added = False
    ban_number = None
    if spam_warning:
        if previous_bans == 0 and has_spam_warning == False:
            #add zeroeth warning
            reason_text = ""
            description = "This warning is to give you an opportunity to read the subreddit and site-wide rules on self-promotion and spam.\n\nThis is your soft warning, which is accompanied by a 1-day subreddit ban. Please take 2 minutes to read our subreddit rules before participating in the community again.".format(link=link)
            duration = 1
            spam_warning_added = True
        else:
            spam_warning_added = False

    if not spam_warning_added: #could still be a spam warning if they've had a warning in the past
        if previous_bans == 0:
            description = "This is your first official warning, which is accompanied by a 7-day subreddit ban. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
            if not spam_warning:
                description = description + " If you message the moderators referencing the rule that you broke and how you broke it, we **may consider** unbanning you early."
            duration = 7
        elif previous_bans == 1:
            description = "**This is your final warning**, which is accompanied by a 30-day subreddit ban; if you receive another warning, you will be permanently banned. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
            duration = 30
        elif previous_bans >= 2:
            description = "This is your third warning, meaning you are now permanently banned."
            duration = None
        
    ban_date = datetime.date.today()
    msg = msg_intro + reason_text + description
    print("Adding ban for user " + user + ". (reason: " + reason + ")")
    subreddit.banned.add(post.author, duration=duration, note=note, ban_message=msg)
    warnings_cursor.execute("INSERT INTO warnings VALUES(?,?,?,?,?)",  [user, link, banning_mod, reason, ban_date])
    warnings_db.commit()
    update_warnings_wiki()
    return duration

def is_bad_title(title):
    title = title.lower()
    if any(tag in title for tag in ["[intentional]", "[unintentional]", "[roleplay]", "[role play]"]):
        for phrase in bad_title_phrases:
            if phrase in title:
                return True
    return False

def title_has_two_tags(title):
    title = title.lower()
    two_tags_regex = re.compile('.*\[(intentional|unintentional|roleplay|role play|journalism|discussion|question|meta|request)\].*\[(intentional|unintentional|roleplay|role play|journalism|discussion|question|meta|request)\].*', re.I)
    two_tags = (re.search(two_tags_regex, title) is not None) # search the title for two tags; if two are found set true, else set false

    if two_tags:
       if "[intentional]" in title and ("[roleplay]" in title or "[role play]" in title):
            title = title.replace("[intentional]", "").replace("[roleplay]", "").replace("[role play]", "")
            
            if any(f in title for f in ["[unintentional]", "[journalism]", "[question]", "[discussion]", "[request]", "[meta]"]): # remove detected tags and check if there are still some left
                return True # another tag is found
            else: 
                return False # those were the only ones

            return False # if the two tags are [intentional] and [roleplay] then allow it
       return True # two tags in title but not intentional and roleplay
    else:
        return False

def title_is_caps(title):
    title = title.replace("ASMR", "") # Remove the string "ASMR"
    title = title.replace("[INTENTIONAL]", "") # Remove the string "INTENTIONAL"
    title = title.replace("[Intentional]", "")
    title = title.replace("[intentional]", "")
    title = title.replace("[UNINTENTIONAL]", "") # Remove the string "UNINTENTIONAL"
    title = title.replace("[Unintentional]", "")
    title = title.replace("[unintentional]", "")
    title = ''.join(char for char in title if char in "etaoinsrhldcufmpgwybvkxjqzABCDEFGHIJKLMNOPQRSTUVWXYZ ")  # Remove anything that isn't alphabetic or a space

    words = title.split(" ")
    tails = []

    for word in words:
        tails.append(word[1:]) #Remove first letter of each word

    normalised_title = "".join(word for word in tails) # merge words back together
    capitals = "".join(char for char in normalised_title if char.upper() == char) # copy only capitals
    
    if len(capitals) >= 0.2 * len(normalised_title): #if capitals are 20% of remaining title
        return True
    else:
        return False

def is_banned_link(url):
    if (   (    ".youtube." in url 
             or "youtu.be"  in url
           )
        and(    "playlist"  in url
             or "list="     in url 
             or "/channel/" in url 
             or "/user/"    in url
           )
       ): # sadface
        return True
    else:
        return False

def is_roleplay(title, vid_id):
    try:
        title = title.lower()
        rp_types = ["role play", "roleplay", "role-play", " rp "]
        if "[intentional]" in title: # only care about submissions tagged [intentional]
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
                            return any(rp in tags for rp in rp_types) # true if roleplay in tags; false otherwise
        return False
    except: 
        #don't want any errors to cause a removal
        return False

def purge_thread(comment): #works
    for reply in comment.replies:
        purge_thread(reply) # recursion is cool
    comment.mod.remove(False)

#def remove_tech_tuesday(): # Called from schedule where parameters can't be used
#    sticky = subreddit.get_sticky()
#    try:
#        if "Tech Tuesday" in sticky.title:
#            sticky.unsticky()
#        else:
#            sticky = subreddit.get_sticky(bottom=True) # get second sticky
#            if "Tech Tuesday" in sticky.title:
#                sticky.unsticky()
#    except praw.errors.HTTPException as e: # if there's no sticky it'll throw a 404 Not Found
#        pass

#def remove_ffaf(): # Called from schedule where parameters can't be used
#    sticky = subreddit.get_sticky()
#    try:
#        if "Free-For-All Friday" in sticky.title:
#            sticky.unsticky()
#        else:
#            sticky = subreddit.get_sticky(bottom=True) # get second sticky
#            if "Free-For-All Friday" in sticky.title:
#                sticky.unsticky()
#    except praw.errors.HTTPException as e: # if there's no sticky it'll throw a 404 Not Found
#        pass

def clear_user_submissions():
    # user_submission_data is a dict containing usernames as keys and lists as values
    # Each user's dict value is a list of my_submission_type objects, representing 
    # every submission they've made in the last 24 hours

    submissions = user_submission_data["submissions"]
    users = list(submissions.keys())

    for user in users:
        if user == "un" and len(users) > 2: # if database is reset, dummy data is inserted as a placeholder. Remove this.
            del submissions["un"] # "un" is an invalid reddit username so this is safe.
            continue
        submissions_by_user = submissions[user] 
        temp = list(submissions_by_user)
        for s in temp:
            if s.date_created < (time.time()-86400): # if the submission was over 24 hours ago
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
        elif submissions_dict[key].date_created < (time.time() - 7948800): # if submission was more than 3 months ago
            del submissions_dict[key]

    recent_video_data["videos"] = submissions_dict

def get_banned_channels(): #tesdted in bot_5, works
    global banned_channels
    try:
        wiki = subreddit.wiki["banned"]
        banned_channels = eval(wiki.content_md)
    except Exception as ex:
        import asmr_bot_data as d # d for data
        banned_channels = d.BANNED_CHANNELS #fall back on known (but probably incomplete) list
        del(d)
        r.redditor("theonefoster").message(subject="Error getting banned channels", message="Exeption when getting banned channels!\n\n" + str(ex) + "\n\n /r/asmr/wiki/banned")

def update_warnings_wiki():
    warnings_cursor.execute("SELECT * FROM warnings")
    db_result = warnings_cursor.fetchall()

    warned_users = dict()

    for war in db_result:
        username, link, mod, reason, date = war
        if username not in warned_users:
            if reason == "spam":
                warned_users[username] = [(link, mod, reason, str(date), 0)]
            else:
                warned_users[username] = [(link, mod, reason, str(date), 1)]
        else:
            bans = warned_users[username]

            ban_number = len(bans) + 1
            bans.append((link, mod, reason, date, ban_number))
            warned_users[username] = bans

    page = "Name | Post | Banned by | Reason given | Date banned | Status\n---|---|---|---|---|---\n"

    for user in warned_users.keys():
        bans = warned_users[user]
        warnings = len(bans)

        page = page + "/u/" + user
       
        for ban in bans:
            link, mod, reason, date, ban_number = ban
            if ban_number == 0:
                status = "Spam warning"
            elif ban_number == 1:
                status = "First warning"
            elif ban_number == 2:
                status = "LAST warning"
            else:
                status = "Permanent"

            page = page + " | " + link + " | " + "/u/" + mod + " | " + reason + " | " + str(date) + " | " + status + "\n"

    subreddit.wiki["warnings"].edit(page)

def user_is_subreddit_banned(username): #tested, works
    banned = subreddit.banned()
    names = [user.name.lower() for user in banned]

    return username.lower() in names

def asmr_bot():
    schedule.run_pending()
#    check_submissions()
    check_comments()
#    check_messages()
    check_mod_queue()

## ----------------------------
## END OF FUNCTIONS
## ----------------------------

r = praw.Reddit("asmr_bot")
print("Logged in as ", end="")
print(r.user.me())
subreddit = r.subreddit("asmr")
#lounge = r.subreddit("asmrcreatorlounge")

###### TEST CODE GOES HERE

#input()
#exit()

###### END OF TEST CODE


if __name__ == "__main__":
    tof = praw.Reddit("theonefoster")
    
    print("Fetching banned channels..")
    get_banned_channels()

#    schedule.every().thursday.at("23:50").do(remove_ffaf)
#    schedule.every().wednesday.at("18:00").do(remove_tech_tuesday)
#    schedule.every(14).days.at("03:00").do(update_top_submissions) # once per fortnight ish
#    schedule.every().hour.do(clear_user_submissions)
#    schedule.every().day.do(update_seen_objects)
#    schedule.every().day.at("02:00").do(clear_video_submissions) # once per day
#    schedule.every(4).hours.do(get_banned_channels) # 6 times per day

    print("Updating submissions databases..")
    clear_user_submissions()
    update_seen_objects()
    clear_video_submissions()

    print("Setup complete. Starting bot duties.")

    exponential_dropoff = 10

    while True:
        try:
            asmr_bot()
            exponential_dropoff = 5
            time.sleep(5)
        except prawcore.exceptions.ServerError as e:
            try:
                print("Server Exception: " + str(e))
                #traceback.print_exc()
                time.sleep(exponential_dropoff) #usually 503 so just try again soon
                exponential_dropoff *= 3
        except Exception as e:
            print("Unknown exception: " + str(e))
            traceback.print_exc()
            print("Sleeping..")
            time.sleep(30) # usually 503. Sleeping reduces reddit load.
        finally:

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

            time.sleep(5) # reduces reddit load and unnecessary processor usage