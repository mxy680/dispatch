import logging
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from services.telegram import verify_secret_token, send_telegram_message, send_typing_action
from database import models
from agents.intent import parse_intent      # adjust to your actual import path
from agents.dispatcher import dispatch_task  # adjust to your actual import path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram")


@router.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    # 1. Verify secret token
    incoming_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not verify_secret_token(incoming_token):
        logger.warning("Rejected webhook request with invalid secret token")
        return JSONResponse({"status": "unauthorized"})

    update = await request.json()

    # 2. Only handle plain messages (ignore edits, channel posts, etc.)
    message = update.get("message")
    if not message or "text" not in message:
        return JSONResponse({"status": "ignored"})

    chat_id: int = message["chat"]["id"]
    text: str = message["text"].strip()
    telegram_username: str = message.get("from", {}).get("username", "")

    # 3. Route to background so Telegram gets a fast 200 OK
    background_tasks.add_task(handle_message, chat_id, text, telegram_username)
    return JSONResponse({"status": "success", "processed": True})


async def handle_message(chat_id: int, text: str, username: str):
    """All agent logic runs here, off the request/response cycle."""
    try:
        await send_typing_action(chat_id)

        # 4. Resolve or create a user account for this chat_id
        user_id = models.get_user_id_by_telegram_chat_id(chat_id)
        if not user_id:
            user_id = models.upsert_user(telegram_chat_id=chat_id, username=username)
            await send_telegram_message(
                chat_id,
                "Welcome to Dispatch! I've created a new account for you. Processing your command now..."
            )

        # 5. Parse intent and dispatch to agents
        projects = models.get_user_projects(user_id)
        intent = await parse_intent(text, projects)

        has_terminal = models.get_terminal_access_for_user(user_id)
        result = await dispatch_task(
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            intent=intent,
            has_terminal=has_terminal,
        )

        # 6. Log and reply
        models.log_agent_event_task(user_id=user_id, event=text, result=result)
        await send_telegram_message(chat_id, result.get("summary", "✅ Done."))

    except Exception as e:
        logger.exception("Error handling Telegram message from chat_id %s", chat_id)
        await send_telegram_message(chat_id, "⚠️ Something went wrong. Please try again.")