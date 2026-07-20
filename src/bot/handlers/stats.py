"""/stats and /top command handlers (read-side analytics)."""

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from bot.locales.messages import get_message
from bot.services.stats import StatsService

log = structlog.get_logger()


def _ranked(items: list) -> str:
    if not items:
        return "—"
    return "\n".join(f"{i}. {name} — {n}" for i, (name, n) in enumerate(items, 1))


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    user = update.effective_user
    lang = user.language_code
    stats: StatsService = context.bot_data["stats"]
    if not stats.enabled:
        await update.effective_message.reply_text(get_message("stats_unavailable", lang))
        return
    user_store = context.bot_data["user_store"]
    want_global = bool(context.args) and context.args[0].lower() == "all"
    try:
        if want_global and user_store.is_admin(user.id):
            g = await stats.global_stats()
            text = get_message(
                "stats_global",
                lang,
                users=g.users,
                requests=g.requests,
                downloads=g.downloads,
                top_users=_ranked(g.top_users),
                platforms=_ranked(g.platforms),
                creators=_ranked(g.creators),
                hashtags=_ranked(g.hashtags),
            )
        else:
            s = await stats.user_stats(user.id)
            if s.requests == 0:
                await update.effective_message.reply_text(get_message("stats_empty", lang))
                return
            text = get_message(
                "stats_personal",
                lang,
                requests=s.requests,
                downloads=s.downloads,
                since=s.first_use.date().isoformat() if s.first_use else "—",
                platforms=_ranked(s.platforms),
                creators=_ranked(s.creators),
                hashtags=_ranked(s.hashtags),
            )
    except Exception:
        log.warning("stats.query_failed", exc_info=True)
        await update.effective_message.reply_text(get_message("stats_unavailable", lang))
        return
    await update.effective_message.reply_text(text)


async def handle_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    lang = update.effective_user.language_code
    stats: StatsService = context.bot_data["stats"]
    if not stats.enabled:
        await update.effective_message.reply_text(get_message("stats_unavailable", lang))
        return
    arg = context.args[0].lower() if context.args else ""
    try:
        if arg == "tags":
            rows = await stats.top_tags(10)
            if rows:
                items = "\n".join(f"{i}. #{name} — {n}" for i, (name, n) in enumerate(rows, 1))
                text = get_message("top_tags_title", lang, items=items)
            else:
                text = get_message("top_empty", lang)
        elif arg == "creators":
            rows = await stats.top_creators(10)
            if rows:
                text = get_message("top_creators_title", lang, items=_ranked(rows))
            else:
                text = get_message("top_empty", lang)
        elif arg.startswith("#") and len(arg) > 1:
            tag = arg[1:]
            videos = await stats.top_videos_for_tag(tag, 5)
            if videos:
                items = "\n".join(
                    f"{i}. {v.title or '?'} — {v.creator}, "
                    f"❤ {v.like_count if v.like_count is not None else '?'}\n{v.url}"
                    for i, v in enumerate(videos, 1)
                )
                text = get_message("top_videos_title", lang, tag=tag, items=items)
            else:
                text = get_message("top_empty", lang)
        else:
            text = get_message("top_usage", lang)
    except Exception:
        log.warning("stats.query_failed", exc_info=True)
        text = get_message("stats_unavailable", lang)
    await update.effective_message.reply_text(text)
