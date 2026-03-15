import os
import praw
from dotenv import load_dotenv

load_dotenv()


def get_reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )


def fetch_subreddit_posts(reddit: praw.Reddit, subreddit_name: str, settings: dict) -> list[dict]:
    posts_per_sub = settings.get("posts_per_subreddit", 50)
    min_comments = settings.get("min_comments", 5)
    top_comments = settings.get("top_comments", 20)
    comment_depth = settings.get("comment_depth", 1)
    time_filter = settings.get("time_filter", "week")

    subreddit = reddit.subreddit(subreddit_name)
    raw_posts = list(subreddit.top(time_filter=time_filter, limit=posts_per_sub))

    qualifying = []
    for post in raw_posts:
        if post.distinguished == "moderator":
            continue
        if post.stickied:
            continue
        if post.distinguished == "admin":
            continue
        if post.num_comments <= min_comments:
            continue
        qualifying.append(post)

    qualifying.sort(key=lambda p: p.score, reverse=True)

    results = []
    for post in qualifying:
        post.comments.replace_more(limit=0)
        top = sorted(post.comments.list(), key=lambda c: getattr(c, "score", 0), reverse=True)
        top = [c for c in top if hasattr(c, "body")][:top_comments]

        comments_data = []
        for comment in top:
            replies = []
            if comment_depth >= 1:
                raw_replies = [
                    r for r in comment.replies
                    if hasattr(r, "body")
                ]
                raw_replies.sort(key=lambda r: getattr(r, "score", 0), reverse=True)
                for reply in raw_replies[:5]:
                    replies.append({
                        "body": reply.body,
                        "score": getattr(reply, "score", 0),
                    })

            comments_data.append({
                "body": comment.body,
                "score": getattr(comment, "score", 0),
                "replies": replies,
            })

        results.append({
            "title": post.title,
            "score": post.score,
            "created_utc": post.created_utc,
            "url": f"https://www.reddit.com{post.permalink}",
            "selftext": post.selftext if post.is_self else "",
            "comments": comments_data,
        })

    return results
