"""
Video handling functionality
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)
from services.data_service import (
    get_target_vacancy_id_from_records,
    get_directory_for_video_from_managers,
    update_user_records_with_top_level_key,
    )
from services.questionnaire_service import send_message_to_user
from services.constants import (
    MAX_DURATION_SECS, 
    VIDEO_SAVED_TEXT,
    )



def _validate_incoming_video(file_size: int, duration: int, max_duration: int = MAX_DURATION_SECS) -> str:
    """Validate incoming video file and return error message if invalid, empty string if valid"""
    # Check duration
    if duration > max_duration:
        return f"Видео слишком длиннее. Пожалуйста, перезапишите более короткое до 60 секунд."
    
    # Check file size (50MB limit)
    if file_size:
        file_size_mb = file_size / (1024 * 1024)
        if file_size_mb > 50:
            return f"Видео больше максимального размера 50 MB. Пожалуйста, запишите кружочек, он точно меньше 50 MB."
    
    return ""


def _clear_pending_video_data_from_context_object(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear pending video data from context object"""
    context.user_data.pop("pending_file_id", None)
    context.user_data.pop("pending_kind", None)
    context.user_data.pop("pending_duration", None)
    context.user_data.pop("pending_file_size", None)


async def process_incoming_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    1) Collect incoming video data, validate it, and store it in "context" object's "user_data" for later processing
    2) Trigger 'ask_confirm_sending_video' method
    """
 
    # ----- GET VIDEO DETAILS from message -----
 
    # Get different video details depending on the type of video
    tg_video = update.message.video
    tg_vnote = update.message.video_note
    tg_doc = update.message.document if update.message.document and (update.message.document.mime_type or "").startswith("video/") else None

    file_id = None
    kind = None
    duration = None
    file_size = None
    
    if tg_video:
        file_id = tg_video.file_id
        kind = "video"
        duration = tg_video.duration
        file_size = getattr(tg_video, 'file_size', None)
    elif tg_vnote:
        file_id = tg_vnote.file_id
        kind = "video_note"
        duration = tg_vnote.duration
        file_size = getattr(tg_vnote, 'file_size', None)
    elif tg_doc:
        file_id = tg_doc.file_id
        kind = "document_video"
        file_size = getattr(tg_doc, 'file_size', None)

    # ----- IF NO VIDEO DETECTED, ask to reupload video -----

    if not file_id:
        await update.message.reply_text("Не удалось определить видео. Пришлите, пожалуйста, еще раз не текст, не фото или аудио, а именно видео.")
        return

    # ----- VALIDATE THAT VIDEO matches requirements -----

    # Validate video using the helper function
    error_msg = _validate_incoming_video(file_size or 0, duration or 0)
    if error_msg:
        await update.message.reply_text(error_msg)
        return

    # ----- STORE VIDEO DETAILS in "context" object's "user_data" for later processing -----

    # Store video details in "context" object's "user_data" for later processing
    context.user_data["pending_file_id"] = file_id
    context.user_data["pending_kind"] = kind
    context.user_data["pending_duration"] = duration
    context.user_data["pending_file_size"] = file_size


    # Local import to avoid circular dependency with manager_bot
    from manager_bot import ask_confirm_sending_video_command

    await ask_confirm_sending_video_command(update, context)


async def download_incoming_video_locally(update: Update, context: ContextTypes.DEFAULT_TYPE, tg_file_id: str, user_id: int, file_type: str) -> None:
    """Download video file to local storage"""
    try:
        query = update.callback_query
        bot_user_id = user_id
        target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)
        video_dir_path = get_directory_for_video_from_managers(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)

        # Generate unique filename with appropriate extension
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        if file_type == "video_note":
            filename = f"manager_{bot_user_id}_vacancy_{target_vacancy_id}_time_{timestamp}_note.mp4"
        else:
            filename = f"manager_{bot_user_id}_vacancy_{target_vacancy_id}_time_{timestamp}.mp4"

        video_file_path = video_dir_path / filename
        logger.debug(f"Video file path: {video_file_path}")

        # Download the file
        if not tg_file_id:
            raise ValueError("Telegram file identifier is empty.")

        try:
            tg_file = await context.bot.get_file(tg_file_id)
        except Exception as fetch_error:
            raise RuntimeError(f"Failed to fetch Telegram file: {fetch_error}") from fetch_error

        await tg_file.download_to_drive(custom_path=str(video_file_path))
        logger.debug(f"Video file downloaded to: {video_file_path}")

        # Update user records with video received and video path
        update_user_records_with_top_level_key(record_id=bot_user_id, key="vacancy_video_received", value="yes")
        update_user_records_with_top_level_key(record_id=bot_user_id, key="vacancy_video_path", value=video_file_path)

        # Clear pending video data from context object
        _clear_pending_video_data_from_context_object(context=context)
        logger.debug(f"Pending video data cleared from context object")
        # Verify the file was created successfully
        if video_file_path.exists():
            logger.debug(f"Video file created successfully: {video_file_path}")

            from manager_bot import read_vacancy_description_command

            # ----- READ VACANCY DESCRIPTION -----

            await read_vacancy_description_command(update=update, context=context)

        else:
            logger.warning(f"Video file not created: {video_file_path}")
            await send_message_to_user(update, context, text="Ошибка при скачивании видео. Пришлите заново, пожалуйста.")

    except Exception as e:
        logger.error(f"Failed to download video: {str(e)}", exc_info=True)

