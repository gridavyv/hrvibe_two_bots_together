# TAGS: [admin], [user_related], [vacancy_related], [resume_related], [recommendation_related]

from ast import Pass
import asyncio
import logging
from datetime import datetime, timezone
from multiprocessing import process
from pathlib import Path
from typing import Optional, List, Tuple
import os
import json
import shutil
import re

logger = logging.getLogger(__name__)

from pydantic.type_adapter import P
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from telegram.constants import ParseMode
from telegram.ext import (  
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from telegram.error import TelegramError

from services.video_service import (
    process_incoming_video,
    download_incoming_video_locally
)

from services.status_validation_service import (
    is_user_in_records,
    is_user_authorized,
    is_hh_data_in_user_record,
    is_vacancy_selected,
    is_vacancy_description_recieved,
    is_vacancy_sourcing_criterias_recieved,
    is_welcome_video_recorded,
    is_sourcing_criterias_file_exists,
    is_negotiations_collection_file_exists,
    is_resume_records_file_exists,
    is_resume_records_file_not_empty,
    is_manager_privacy_policy_confirmed,
    is_applicant_video_recorded,
)


from services.data_service import (
    get_directory_for_video_from_applicants,
    format_oauth_link_text,
    create_resume_records_file,
    get_resume_records_file_path,
    get_path_to_video_from_applicant_from_resume_records,
    get_tg_user_data_attribute_from_update_object,
    create_oauth_link,
    get_decision_status_from_selected_callback_code,
    update_user_records_with_top_level_key,
    create_user_directory, 
    create_vacancy_directory,
    get_vacancy_directory,
    create_resumes_directory_and_subdirectories,
    create_record_for_new_resume_id_in_resume_records,
    get_resume_recommendation_from_resume_records,
    update_resume_record_with_top_level_key,
    get_resume_directory,
    create_record_for_new_user_in_records, 
    get_access_token_from_callback_endpoint_resp,
    get_access_token_from_records,
    get_expires_at_from_callback_endpoint_resp,
    create_json_file_with_dictionary_content,
    get_target_vacancy_id_from_records,
    get_target_vacancy_name_from_records,
    get_list_of_passed_resume_ids_with_video,
    get_negotiation_id_from_resume_record,
    get_users_records_file_path,
    get_employer_id_from_records,
    get_list_of_users_from_records,
    create_tg_bot_link_for_applicant,
    create_video_from_managers_directory,
    create_video_from_applicants_directory,
)
from services.auth_service import (
    get_token_by_state,
    callback_endpoint_healthcheck,
    BOT_SHARED_SECRET,
)
from services.hh_service import (
    get_user_info_from_hh, 
    clean_user_info_received_from_hh,
    get_employer_vacancies_from_hh,
    filter_open_employer_vacancies,
    get_vacancy_description_from_hh,
    get_negotiations_by_collection,
    change_collection_status_of_negotiation,
    send_negotiation_message,
    get_resume_info,
)
from services.ai_service import (
    analyze_vacancy_with_ai, 
    format_vacancy_analysis_result_for_markdown,
    analyze_resume_with_ai
)
from services.questionnaire_service import (
    ask_question_with_options, 
    handle_answer,
    send_message_to_user,
    clear_all_unprocessed_keyboards
)
from task_queue import TaskQueue

from services.status_validation_service import is_vacany_data_enough_for_resume_analysis


from services.constants import *


HH_CLIENT_ID = os.getenv("HH_CLIENT_ID")
HH_CLIENT_SECRET = os.getenv("HH_CLIENT_SECRET")
OAUTH_REDIRECT_URL = os.getenv("OAUTH_REDIRECT_URL")
USER_AGENT = os.getenv("USER_AGENT")

# Global task queue for AI analysis tasks
ai_task_queue = TaskQueue(maxsize=500)


##########################################
# ------------ ADMIN COMMANDS ------------``
##########################################


async def send_message_to_admin(application: Application, text: str, parse_mode: Optional[ParseMode] = None) -> None:
    #TAGS: [admin]

    # ----- GET ADMIN ID from environment variables -----
    
    admin_id = os.getenv("ADMIN_ID", "")
    if not admin_id:
        logger.error("send_message_to_admin:ADMIN_ID environment variable is not set. Cannot send admin notification.")
        return
    
    # ----- SEND NOTIFICATION to admin -----
    
    try:
        if application and application.bot:
            await application.bot.send_message(
                chat_id=int(admin_id),
                text=text,
                parse_mode=parse_mode
            )
            logger.debug(f"send_message_to_admin: Admin notification sent successfully to admin_id: {admin_id}")
        else:
            logger.warning("send_message_to_admin: Cannot send admin notification: application or bot instance not available")
    except Exception as e:
        logger.error(f"send_message_to_admin: Failed to send admin notification: {e}", exc_info=True)


async def admin_get_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #TAGS: [admin]
    """
    Admin command to list all user IDs from user records.
    Only accessible to users whose ID is in the ADMIN_IDS whitelist.
    """

    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"admin_get_users_command: started. User_id: {bot_user_id}")
        
        #  ----- CHECK IF USER IS NOT AN ADMIN and STOP if it is -----

        admin_id = os.getenv("ADMIN_ID", "")
        if not admin_id or bot_user_id != admin_id:
            await send_message_to_user(update, context, text=FAIL_TO_IDENTIFY_USER_AS_ADMIN_TEXT)
            logger.error(f"Unauthorized for {bot_user_id}")
            return

        # ----- SEND LIST OF USERS IDs from records -----

        user_ids = get_list_of_users_from_records()

        await send_message_to_user(update, context, text=f"📋 List of users: {user_ids}")
    
    except Exception as e:
        logger.error(f"admin_get_users_command: Failed to execute admin_get_list_of_users command: {e}", exc_info=True)        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error executing admin_get_list_of_users command: {e}\nAdmin ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def admin_update_negotiations_for_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #TAGS: [admin]
    """
    Admin command to update negotiations for all users.
    Only accessible to users whose ID is in the ADMIN_IDS whitelist.
    """

    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"admin_update_negotiations_for_all_command: started. User_id: {bot_user_id}")

        #  ----- CHECK IF USER IS NOT AN ADMIN and STOP if it is -----

        admin_id = os.getenv("ADMIN_ID", "")
        if not admin_id or bot_user_id != admin_id:
            await send_message_to_user(update, context, text=FAIL_TO_IDENTIFY_USER_AS_ADMIN_TEXT)
            logger.error(f"Unauthorized for {bot_user_id}")
            return

        # ----- UPDATE NEGOTIATIONS for all users -----

        user_ids = get_list_of_users_from_records()
        negotiations_updated = 0
        for user_id in user_ids:
            if is_vacany_data_enough_for_resume_analysis(user_id=user_id):
                await source_negotiations_triggered_by_admin_command(bot_user_id=user_id)
                negotiations_updated += 1
            else:
                logger.debug(f"admin_update_negotiations_for_all_command: User {user_id} does not have enough vacancydata for resume analysis. Negotiations update skipped.")

        await send_message_to_user(update, context, text=f"Total users: {len(user_ids)}. Negotiations collections updated for: {negotiations_updated} users.")
    
    except Exception as e:
        logger.error(f"admin_update_negotiations_for_all_command: Failed to execute command: {e}", exc_info=True)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error admin_update_negotiations_for_all_command: {e}\nAdmin ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def admin_get_fresh_resumes_for_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #TAGS: [admin]
    """
    Admin command to get fresh resumes for all users.
    Only accessible to users whose ID is in the ADMIN_IDS whitelist.
    """

    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"admin_get_fresh_resumes_for_all_command: started. User_id: {bot_user_id}")
        
        #  ----- CHECK IF USER IS NOT AN ADMIN and STOP if it is -----

        admin_id = os.getenv("ADMIN_ID", "")
        if not admin_id or bot_user_id != admin_id:
            await send_message_to_user(update, context, text=FAIL_TO_IDENTIFY_USER_AS_ADMIN_TEXT)
            logger.error(f"Unauthorized for {bot_user_id}")
            return

        # ----- SOURCE RESUMES for all users -----

        user_ids = get_list_of_users_from_records()
        resumes_sourced = 0
        for user_id in user_ids:
            if is_vacany_data_enough_for_resume_analysis(user_id=user_id):
                await source_resumes_triggered_by_admin_command(bot_user_id=user_id)
                resumes_sourced += 1
            else:
                logger.debug(f"admin_get_fresh_resumes_for_all_command: User {user_id} does not have enough vacancy data for resume analysis. Resume sourcing skipped.")
                
        await send_message_to_user(update, context, text=f"Total users: {len(user_ids)}. Fresh resumes sourced for: {resumes_sourced} users.")
    
    except Exception as e:
        logger.error(f"admin_get_fresh_resumes_for_all_command: Failed to execute command: {e}", exc_info=True)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error admin_get_fresh_resumes_for_all_command: {e}\nAdmin ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def admin_anazlyze_resumes_for_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #TAGS: [admin]
    """
    Admin command to analyze fresh resumes for all users.
    Only accessible to users whose ID is in the ADMIN_IDS whitelist.
    """

    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"admin_anazlyze_resumes_for_all_command: started. User_id: {bot_user_id}")
        
        #  ----- CHECK IF USER IS NOT AN ADMIN and STOP if it is -----

        admin_id = os.getenv("ADMIN_ID", "")
        if not admin_id or bot_user_id != admin_id:
            await send_message_to_user(update, context, text=FAIL_TO_IDENTIFY_USER_AS_ADMIN_TEXT)
            logger.error(f"Unauthorized for {bot_user_id}")
            return

        # ----- CREATE TASKS for resume ananlysis for all users -----

        user_ids = get_list_of_users_from_records()
        analyze_tasks_created = 0
        for user_id in user_ids:
            if is_vacany_data_enough_for_resume_analysis(user_id=user_id):
                await analyze_resume_triggered_by_admin_command(bot_user_id=user_id)
                analyze_tasks_created += 1
            else:
                logger.debug(f"admin_anazlyze_resumes_for_all_command: User {user_id} does not have enough vacancy data for resume analysis. Analyze task skipped.")
                
        await send_message_to_user(update, context, text=f"Total users: {len(user_ids)}. Analyze tasks created for: {analyze_tasks_created} users.")
    
    except Exception as e:
        logger.error(f"admin_anazlyze_resumes_for_all_command: Failed to execute command: {e}", exc_info=True)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error admin_anazlyze_resumes_for_all_command: {e}\nAdmin ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def admin_update_resume_records_with_applicants_video_status_for_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #TAGS: [admin]
    """
    Admin command to update resume records with fresh videos from applicants for all users.
    Only accessible to users whose ID is in the ADMIN_IDS whitelist.
    """

    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"admin_update_resume_records_with_applicants_video_status_for_all_command: started. User_id: {bot_user_id}")

        #  ----- CHECK IF USER IS NOT AN ADMIN and STOP if it is -----

        admin_id = os.getenv("ADMIN_ID", "")
        if not admin_id or bot_user_id != admin_id:
            await send_message_to_user(update, context, text=FAIL_TO_IDENTIFY_USER_AS_ADMIN_TEXT)
            logger.error(f"Unauthorized for {bot_user_id}")
            return


        # ----- UPDATE RESUME RECORDS with FRESH VIDEOS from applicants for each user -----

        user_ids = get_list_of_users_from_records()
        videos_updated = 0
        for user_id in user_ids:
            if is_vacany_data_enough_for_resume_analysis(user_id=user_id):
                # Get vacancy_id for each user individually
                user_vacancy_id = get_target_vacancy_id_from_records(record_id=user_id)
                if user_vacancy_id:
                    await update_resume_records_with_fresh_video_from_applicants_command(bot_user_id=user_id, vacancy_id=user_vacancy_id, application=context.application)
                    videos_updated += 1
                else:
                    logger.debug(f"admin_update_resume_records_with_applicants_video_status_for_all_command: User {user_id} does not have a vacancy selected. Video update skipped.")
            else:
                logger.debug(f"admin_update_resume_records_with_applicants_video_status_for_all_command: User {user_id} does not have enough vacancy data for resume analysis. Video update skipped.")

        await send_message_to_user(update, context, text=f"Total users: {len(user_ids)}. Tasks to update resume records with fresh videos from applicants triggered for: {videos_updated} users.")
    
    except Exception as e:
        logger.error(f"admin_update_resume_records_with_applicants_video_status_for_all_command: Failed to execute command: {e}", exc_info=True)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error admin_update_resume_records_with_applicants_video_status_for_all_command: {e}\nAdmin ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            ) 


async def admin_recommend_applicants_with_video_for_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #TAGS: [admin]
    """
    Admin command to recommend applicants with video for all users.
    Only accessible to users whose ID is in the ADMIN_IDS whitelist.
    """

    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"admin_recommend_applicants_with_video_for_all_command: started. User_id: {bot_user_id}")
        
        #  ----- CHECK IF USER IS NOT AN ADMIN and STOP if it is -----

        admin_id = os.getenv("ADMIN_ID", "")
        if not admin_id or bot_user_id != admin_id:
            await send_message_to_user(update, context, text=FAIL_TO_IDENTIFY_USER_AS_ADMIN_TEXT)
            logger.error(f"Unauthorized for {bot_user_id}")
            return

        # ----- CREATE TASKS for recommendation of resumes with video for all users -----

        user_ids = get_list_of_users_from_records()
        recommendation_tasks = 0
        for user_id in user_ids:
            if is_vacany_data_enough_for_resume_analysis(user_id=user_id):
                target_vacancy_id = get_target_vacancy_id_from_records(record_id=user_id)
                passed_resume_ids_with_video = get_list_of_passed_resume_ids_with_video(bot_user_id=user_id, vacancy_id=target_vacancy_id)
                # means manager has passed resumes with video
                if len(passed_resume_ids_with_video) > 0:
                    await recommend_resumes_with_video_command(bot_user_id=user_id, application=context.application)
                    recommendation_tasks += 1
                else:
                    logger.debug(f"admin_recommend_applicants_with_video_for_all_command: User {user_id} does not have passed resumes with video. Recommendation skipped.")
            else:
                logger.debug(f"admin_recommend_applicants_with_video_for_all_command: User {user_id} does not have enough data to analyze resumes. Recommendation skipped.")
                
        admin_update_text = f"Total users: {len(user_ids)}. Recomendation of resumes with video triggered for: {recommendation_tasks} users."
        await send_message_to_user(update, context, text=admin_update_text)
    
    except Exception as e:
        logger.error(f"admin_recommend_applicants_with_video_for_all_command: Failed to execute command: {e}", exc_info=True)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error admin_recommend_applicants_with_video_for_all_command: {e}\nAdmin ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def admin_send_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #TAGS: [admin]
    """
    Admin command to send a message to a specific user by user_id (chat_id).
    Usage: /admin_send_message <user_id> <message_text>
    Usage example: /admin_send_message 7853115214 Привет! Как дела?
    Sends notification to admin if fails
    """
    
    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"admin_send_message_command triggered by user_id: {bot_user_id}")
        
        #  ----- CHECK IF USER IS NOT AN ADMIN and STOP if it is -----

        admin_id = os.getenv("ADMIN_ID", "")
        if not admin_id or bot_user_id != admin_id:
            await send_message_to_user(update, context, text=FAIL_TO_IDENTIFY_USER_AS_ADMIN_TEXT)
            logger.error(f"Unauthorized for {bot_user_id}")
            return

        # ----- PARSE COMMAND ARGUMENTS -----

        if not context.args or len(context.args) < 2:
            await send_message_to_user(
                update, 
                context, 
                text="⚠️ Неверный формат команды.\nИспользование: /admin_send_message <user_id> <текст_сообщения>"
            )
            return
        
        target_user_id = context.args[0]
        message_text = " ".join(context.args[1:])  # Join all remaining arguments as message text

        # ----- VALIDATE USER_ID -----

        try:
            target_user_id_int = int(target_user_id)
        except ValueError:
            await send_message_to_user(update, context, text=f"❌ Неверный формат user_id: {target_user_id}")
            return

        # ----- SEND MESSAGE TO USER -----

        if context.application and context.application.bot:
            try:
                await context.application.bot.send_message(
                    chat_id=target_user_id_int,
                    text=message_text
                )
                await send_message_to_user(update, context, text=f"✅ Сообщение отправлено пользователю {target_user_id}:\n'{message_text}'")
                logger.info(f"Admin {bot_user_id} sent message to user {target_user_id}: {message_text}")
            except Exception as send_err:
                error_msg = f"❌ Не удалось отправить сообщение пользователю {target_user_id}: {send_err}"
                await send_message_to_user(update, context, text=error_msg)
                logger.error(f"Failed to send message to user {target_user_id}: {send_err}", exc_info=True)
                raise
        else:
            raise ValueError("Application or bot instance not available")
    
    except Exception as e:
        logger.error(f"Failed to execute admin_send_message_to_user command: {e}", exc_info=True)
        await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error executing admin_send_message_to_user command: {e}\nAdmin ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def admin_pull_log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #TAGS: [admin]
    """
    Admin command to pull and send log files.
    Usage: /admin_pull_log <log_type> <log_name>
    Usage example: /admin_pull_log manager_bot 1234432.log
    Sends the log file as a document to the admin chat.
    """
    
    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"admin_pull_log_command: started. User_id: {bot_user_id}")
        
        #  ----- CHECK IF USER IS NOT AN ADMIN and STOP if it is -----

        admin_id = os.getenv("ADMIN_ID", "")
        if not admin_id or bot_user_id != admin_id:
            await send_message_to_user(update, context, text=FAIL_TO_IDENTIFY_USER_AS_ADMIN_TEXT)
            logger.error(f"Unauthorized for {bot_user_id}")
            return

        # ----- PARSE COMMAND ARGUMENTS -----

        if not context.args or len(context.args) < 2:
            invalid_args_text = "Invalid request format.\nValid: /admin_pull_log <log_type> <log_name>"
            raise ValueError(invalid_args_text)
        
        log_type = context.args[0]
        log_name = context.args[1]

        # ----- VALIDATE LOG_TYPE -----

        valid_log_types = ["applicant_bot_logs", "manager_bot_logs", "orchestrator_logs"]
        if log_type not in valid_log_types:
            invalid_log_type_text = f"Invalid log type: {log_type}\nValid types: {', '.join(valid_log_types)}"
            raise ValueError(invalid_log_type_text)

        # ----- CONSTRUCT LOG FILE PATH -----

        data_dir = Path(os.getenv("USERS_DATA_DIR", "/users_data"))
        log_file_path = data_dir / "logs" / log_type / log_name

        # ----- CHECK IF FILE EXISTS -----

        if not log_file_path.exists():
            invalid_log_path_text = f"Invalid log path'{log_file_path}'. File not found"
            raise FileNotFoundError(invalid_log_path_text)
            
            return

        # ----- SEND LOG FILE TO USER -----

        if context.application and context.application.bot:
            try:
                chat_id = update.effective_chat.id
                with open(log_file_path, 'rb') as log_file:
                    await context.application.bot.send_document(
                        chat_id=chat_id,
                        document=InputFile(log_file, filename=log_name),
                        caption=f"📄 Log file: {log_name}\nLog Type: {log_type}"
                    )
                logger.info(f"admin_pull_log_command: log file '{log_file_path}' sent to user {bot_user_id}")
            except Exception as send_err:
                raise TelegramError(f"Failed to send log file '{log_file_path}': {send_err}")
        else:
            raise RuntimeError("Application or bot instance not available")
    except Exception as e:
        logger.error(f"admin_pull_log_command: Failed to execute: {e}", exc_info=True)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error admin_pull_log_command: {e}\nAdmin ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def admin_pull_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #TAGS: [admin]
    """
    Admin command to pull and send log files.
    Usage: /admin_pull_file <file_relative_path>
    Usage example: /admin_pull_file logs/manager_bot_logs/1234432.log
    Sends the log file as a document to the admin chat.
    """
    
    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"admin_pull_file_command: started. User_id: {bot_user_id}")
        
        #  ----- CHECK IF USER IS NOT AN ADMIN and STOP if it is -----

        admin_id = os.getenv("ADMIN_ID", "")
        if not admin_id or bot_user_id != admin_id:
            await send_message_to_user(update, context, text=FAIL_TO_IDENTIFY_USER_AS_ADMIN_TEXT)
            logger.error(f"Unauthorized for {bot_user_id}")
            return

        # ----- PARSE COMMAND ARGUMENTS -----

        if not context.args or len(context.args) != 1:
            invalid_args_text = "Invalid arguments.\nValid: /admin_pull_file <file_relative_path>"
            raise ValueError(invalid_args_text)
        
        file_relative_path = context.args[0]

        # ----- CONSTRUCT LOG FILE PATH -----

        data_dir = Path(os.getenv("USERS_DATA_DIR", "/users_data"))
        file_path = data_dir / file_relative_path
        file_name = file_path.name

        # ----- VALIDATE FILE EXTENSION -----

        valid_extensions = [".log", ".json", ".mp4"]
        file_extension = file_path.suffix
        if file_extension not in valid_extensions:
            invalid_extension_text = f"Invalid file extension.\nValid: {', '.join(valid_extensions)}"
            raise ValueError(invalid_extension_text)

        # ----- CHECK IF FILE EXISTS -----

        if not file_path.exists():
            invalid_path_text = f"Invalid file relative path'{file_relative_path}'. File not found"
            raise FileNotFoundError(invalid_path_text)

        # ----- SEND LOG FILE TO USER -----

        if context.application and context.application.bot:
            try:
                chat_id = update.effective_chat.id
                with open(file_path, 'rb') as file:
                    await context.application.bot.send_document(
                        chat_id=chat_id,
                        document=InputFile(file, filename=file_name)
                    )
                logger.info(f"admin_pull_file_command: file '{file_path}' sent to user {bot_user_id}")
            except Exception as send_err:
                raise TelegramError(f"Failed to send file '{file_path}': {send_err}")
        else:
            raise RuntimeError("Application or bot instance not available")
    except Exception as e:
        logger.error(f"admin_pull_file_command: Failed to execute: {e}", exc_info=True)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error admin_pull_file_command: {e}\nAdmin ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


########################################################################################
# ------------ AUTOMATIC FLOW ON START - can be triggered by from MAIN MENU ------------
########################################################################################
# - setup user
# - ask privacy policy confirmation
# - handle answer privacy policy confirmation
# - HH authorization
# - pull user data from HH
# - select vacancy
# - handle answer select vacancy
# - ask to record video
# - handle answer video record request
# - send instructions to shoot video
# - ask confirm sending video
# - handle answer confirm sending video
# - read vacancy description
# - define sourcing criterias
# - get sourcing criterias from AI and save to file


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler. 
    Called from: 'start' button in main menu.
    Triggers: 1) setup new user 2) ask privacy policy confirmation
    """

    # ----- SETUP NEW USER and send welcome message -----

    # if existing user, setup_new_user_command will be skipped
    await setup_new_user_command(update=update, context=context)

    # ----- ASK PRIVACY POLICY CONFIRMATION -----

    # if already confirmed, second confirmation will be skipped
    await ask_privacy_policy_confirmation_command(update=update, context=context)

    # IMPORTANT: ALL OTHER COMMANDS will be triggered from functions if PRIVACY POLICY is confirmed


async def setup_new_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Setup new user in system.
    Called from: 'start_command'.
    Triggers: nothing.
    Sends notification to admin if fails"""

    try:
        # ------ COLLECT NEW USER ID and CREATE record and user directory if needed ------

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"setup_new_user_command started. user_id: {bot_user_id}")

        if not is_user_in_records(record_id=bot_user_id):
            create_record_for_new_user_in_records(record_id=bot_user_id)
            create_user_directory(bot_user_id=bot_user_id)

            # ------ ENRICH RECORDS with NEW USER DATA ------

        tg_user_attributes = ["username", "first_name", "last_name"]
        for item in tg_user_attributes:
            tg_user_attribute_value = get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute=item)
            update_user_records_with_top_level_key(record_id=bot_user_id, key=item, value=tg_user_attribute_value)
        logger.debug(f"{bot_user_id} in user records is updated with telegram user attributes.")
    
    except Exception as e:
        logger.error(f"Failed to setup new user: {e}", exc_info=True)
        await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error setting up new user: {e}\nUser ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def ask_privacy_policy_confirmation_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Ask privacy policy confirmation command handler. 
    Called from: 'start_command'.
    Triggers: nothing."""

    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"ask_privacy_policy_confirmation_command started. user_id: {bot_user_id}")

    # ----- CHECK IF PRIVACY POLICY is already confirmed and STOP if it is -----

    if is_manager_privacy_policy_confirmed(bot_user_id=bot_user_id):
        await send_message_to_user(update, context, text=SUCCESS_TO_GET_PRIVACY_POLICY_CONFIRMATION_TEXT)
        return

    # Build options (which will be tuples of (button_text, callback_data))
    answer_options = [
        ("Ознакомлен, даю согласие на обработку.", "privacy_policy_confirmation:yes"),
        ("Не даю согласие на обрабоку.", "privacy_policy_confirmation:no"),
    ]
    # Store button_text and callback_data options in context to use it later for button _text identification as this is not stored in "update.callback_query" object
    context.user_data["privacy_policy_confirmation_answer_options"] = answer_options
    await ask_question_with_options(update, context, question_text=PRIVACY_POLICY_CONFIRMATION_TEXT, answer_options=answer_options)


async def handle_answer_policy_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Handle button click, updates confirmation status in user records.
    Called from: nowhere.
    Triggers commands:
    - If user agrees to process personal data, triggers 'hh_authorization_command'.
    - If user does not agree to process personal data, informs user how to give consent."""

    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"handle_answer_policy_confirmation started. user_id: {bot_user_id}")
    
    # ------- UNDERSTAND WHAT BUTTON was clicked and get "callback_data" from it -------

    # Get the "callback_data" extracted from "update.callback_query" object created once button clicked
    selected_callback_code = await handle_answer(update, context)

    # ----- UNDERSTAND TEXT on clicked buttton from option taken from context -----

    # Get options from context or return empty list [] if not found
    privacy_policy_confirmation_answer_options = context.user_data.get("privacy_policy_confirmation_answer_options", [])
    # find selected button text from callback_data
    for button_text, callback_code in privacy_policy_confirmation_answer_options:
        if selected_callback_code == callback_code:
            selected_button_text = button_text
            # Clear privacy policy confirmation answer options from "context" object, because now use "selected_button_text" variable instead
            context.user_data.pop("privacy_policy_confirmation_answer_options", None)
            break

    # ----- INFORM USER about selected option -----

    # If "options" is NOT an empty list execute the following code
    if privacy_policy_confirmation_answer_options:
        await send_message_to_user(update, context, text=f"Вы выбрали: '{selected_button_text}'")
    else:
        # No options available, inform user and return
        if update.callback_query and update.callback_query.message:
            await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        return

    # ----- UPDATE USER RECORDS with selected vacancy data -----

    # Now you can use callback_data or selected_option for your logic
    if update.callback_query and update.callback_query.message:
        if selected_callback_code is None:
            await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
            return
        privacy_policy_confirmation_user_decision = get_decision_status_from_selected_callback_code(selected_callback_code=selected_callback_code)
        # Update user records with selected vacancy data
        update_user_records_with_top_level_key(record_id=bot_user_id, key="privacy_policy_confirmed", value=privacy_policy_confirmation_user_decision)
        current_time = datetime.now(timezone.utc).isoformat()
        update_user_records_with_top_level_key(record_id=bot_user_id, key="privacy_policy_confirmation_time", value=current_time)
        logger.debug(f"Privacy policy confirmation user decision: {privacy_policy_confirmation_user_decision} at {current_time}")

        # ----- IF USER CHOSE "YES" download video to local storage -----

        if privacy_policy_confirmation_user_decision == "yes":
            await send_message_to_user(update, context, text=SUCCESS_TO_GET_PRIVACY_POLICY_CONFIRMATION_TEXT)
            
        # ----- SEND AUTHENTICATION REQUEST and wait for user to authorize -----
    
            # if already authorized, second authorization will be skipped
            await hh_authorization_command(update=update, context=context)
        
        # ----- IF USER CHOSE "NO" inform user about need to give consent to process personal data -----
        
        else:
            await send_message_to_user(update, context, text=MISSING_PRIVACY_POLICY_CONFIRMATION_TEXT)


async def hh_authorization_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """ HH authorization command. 
    Called from: 'handle_answer_policy_confirmation'.
    Triggers: 'pull_user_data_from_hh_command'.
    - Sends intro text and link to authorize via HH.ru.
    - Waits for user to authorize
        - If user authorized, sends success text.
        - If user didn't authorize, sends error text.
    """
    
    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"hh_authorization_command triggered by user_id: {bot_user_id}")
    
    # ----- CHECK IF NO Privacy policy consent or AUTHORIZAED already and STOP if it is -----
    if not is_manager_privacy_policy_confirmed(bot_user_id=bot_user_id):
        await send_message_to_user(update, context, text=MISSING_PRIVACY_POLICY_CONFIRMATION_TEXT)
        return

    if is_user_authorized(record_id=bot_user_id):
        await send_message_to_user(update, context, text=SUCCESS_TO_HH_AUTHORIZATION_TEXT)
        return

    # ------ HH.ru AUTHENTICATION PROCESS ------
    
    # Check if the authentication endpoint is healthy
    if not callback_endpoint_healthcheck():
        await send_message_to_user(update, context, text="Сервер авторизации недоступен. Тех. поддержка свяжется с вами в ближайшее время.")
        await send_message_to_admin(application=context.application, text=f"⚠️ Error: Сервер авторизации недоступен. Пользователь: {bot_user_id} не может авторизаоваться.")
        return

    # ------ SEND USER AUTH link in HTML format ------
    
    # Build OAuth link and send it to the user
    auth_link = create_oauth_link(state=bot_user_id)
    # Format oauth link text to keep https links in html format
    formatted_oauth_link_text = format_oauth_link_text(oauth_link=auth_link)
    authorization_request_text = AUTH_REQ_TEXT + formatted_oauth_link_text
    await send_message_to_user(update, context, text=authorization_request_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    await asyncio.sleep(1) 

    # ------ WAIT FOR USER AUTHORIZATION ------

    await send_message_to_user(update, context, text="⏳ Ожидаю авторизацию...")
    # Wait for user to authorize - retry 5 times over ~60 seconds
    max_attempts = 30
    retry_delay = 6  # seconds between retries
    endpoint_response = None
    # Retry to get access token by state 5 times over ~60 seconds
    for attempt in range(1, max_attempts + 1):
        await asyncio.sleep(retry_delay)
        endpoint_response = get_token_by_state(state=bot_user_id, bot_shared_secret=BOT_SHARED_SECRET)
        
        if endpoint_response is not None:
            if endpoint_response is not CALLBACK_ENDPOINT_RESPONSE_WHEN_RECORDS_NOT_READY:
                logger.debug(f"Endpoint response: {endpoint_response}")
                access_token = get_access_token_from_callback_endpoint_resp(endpoint_response=endpoint_response)
                expires_at = get_expires_at_from_callback_endpoint_resp(endpoint_response=endpoint_response)
                if access_token is not None and expires_at is not None:
                    update_user_records_with_top_level_key(record_id=bot_user_id, key="access_token_recieved", value="yes")
                    update_user_records_with_top_level_key(record_id=bot_user_id, key="access_token", value=access_token)
                    update_user_records_with_top_level_key(record_id=bot_user_id, key="access_token_expires_at", value=expires_at)
                logger.info(f"Authorization successful on attempt {attempt}. Access token '{access_token}' and expires_at '{expires_at}' updated in records.")
                await send_message_to_user(update, context, text=AUTH_SUCCESS_TEXT)

    # ----- PULL USER DATA from HH and enrich records with it -----

                await pull_user_data_from_hh_command(update=update, context=context)
                
                #Stop the loop after successful authorization
                break
        else:
            logger.debug(f"Attempt {attempt}/{max_attempts}: User hasn't authorized yet. Retrying...")
    # If still None after all attempts, user didn't authorize
    if endpoint_response is None:
        await send_message_to_user(update, context, text=AUTH_FAILED_TEXT)
        return


async def pull_user_data_from_hh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Pull user data from HH and enrich records with it. 
    Called from: 'hh_authorization_command'.
    Triggers: 'select_vacancy_command'.
    Sends notification to admin if fails"""
    
    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"pull_user_data_from_hh_command started. user_id: {bot_user_id}")
        access_token = get_access_token_from_records(bot_user_id=bot_user_id)

        # ----- CHECK IF USER DATA is already in records and STOP if it is -----

        # Check if user is already authorized, if not, pull user data from HH
        if is_hh_data_in_user_record(record_id=bot_user_id):
            logger.debug(f"'bot_user_id': {bot_user_id} already has HH data in user record.")
            return 
            
        # ----- PULL USER DATA from HH and enrich records with it -----

        # Get user info from HH.ru API
        hh_user_info = get_user_info_from_hh(access_token=access_token)
        # Clean user info received from HH.ru API
        cleaned_hh_user_info = clean_user_info_received_from_hh(user_info=hh_user_info)
        # Update user info from HH.ru API in records
        update_user_records_with_top_level_key(record_id=bot_user_id, key="data_from_hh", value=cleaned_hh_user_info)

        # ----- SELECT VACANCY -----

        await select_vacancy_command(update=update, context=context)
    
    except Exception as e:
        logger.error(f"Failed to pull user data from HH: {e}", exc_info=True)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error pulling user data from HH: {e}\nUser ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def ask_to_record_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Ask to record video command. 
    Called from: 'handle_vacancy_selection'.
    Triggers: nothing."""

    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"ask_to_record_video_command triggered by user_id: {bot_user_id}")
    target_vacancy_name = get_target_vacancy_name_from_records(record_id=bot_user_id)

    # ----- CHECK MUST CONDITIONS are met and STOP if not -----

    if not is_manager_privacy_policy_confirmed(bot_user_id=bot_user_id):
        await send_message_to_user(update, context, text=MISSING_PRIVACY_POLICY_CONFIRMATION_TEXT)
        return

    if not is_vacancy_selected(record_id=bot_user_id):
        logger.debug(f"'bot_user_id': {bot_user_id} doesn't have target vacancy selected.")
        await send_message_to_user(update, context, text=MISSING_VACANCY_SELECTION_TEXT)
        return

    if is_welcome_video_recorded(record_id=bot_user_id):
        logger.debug(f"'bot_user_id': {bot_user_id} already has welcome video recorded for vacancy '{target_vacancy_name}'.")
        await send_message_to_user(update, context, text=SUCCESS_TO_RECORD_VIDEO_TEXT + f" Вакансия: '{target_vacancy_name}'.")
        return

    # ----- ASK USER IF WANTS TO RECORD or drop welcome video for the selected vacancy -----

    # Build options (which will be tuples of (button_text, callback_data))
    answer_options = [
        ("Хочу записать или загрузить видео", "record_video_request:yes"), 
        ("Продолжить без видео", "record_video_request:no")
        ]
    # Store button_text and callback_data options in context to use it later for button _text identification as this is not stored in "update.callback_query" object
    context.user_data["video_record_request_options"] = answer_options
    await ask_question_with_options(update, context, question_text=WELCOME_VIDEO_RECORD_REQUEST_TEXT, answer_options=answer_options)
    logger.debug(f"Record video request question with options asked")


async def handle_answer_video_record_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Handle button click. 
    Called from: nowhere.
    Triggers commands:
    - If user agrees to record, sends instructions to shootv ideo command'.
    - If user does not agree to record, triggers 'read_vacancy_description_command'.

    This is called AUTOMATICALLY by Telegram when a button is clicked (via CallbackQueryHandler).

    Note: Bot knows which user clicked because:
    - update.effective_user.id contains the user ID (works for both messages and callbacks)
    - context.user_data is automatically isolated per user by python-telegram-bot framework
    """

    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"handle_answer_video_record_request triggered by user_id: {bot_user_id}")
    
    # ------- UNDERSTAND WHAT BUTTON was clicked and get "callback_data" from it -------

    # Get the "callback_data" extracted from "update.callback_query" object created once button clicked
    selected_callback_code = await handle_answer(update, context)
    
    logger.debug(f"Callback code found: {selected_callback_code}")

    # ----- UNDERSTAND TEXT on clicked buttton from option taken from context -----

    if not selected_callback_code:
        if update.callback_query and update.callback_query.message:
            logger.debug(f"No callback code found in update.callback_query.message")
            await send_message_to_user(update, context, text="Не удалось определить ваш выбор. Попробуйте еще раз командой /ask_to_record_video.")
        return

    logger.debug(f"Callback code found: {selected_callback_code}")

    # Get options from context or use fallback defaults if not found
    video_record_request_options = context.user_data.get("video_record_request_options", [])
    logger.debug(f"Video record request options: {video_record_request_options}")
    if not video_record_request_options:
        video_record_request_options = [
            ("Хочу записать или загрузить видео", "record_video_request:yes"),
            ("Продолжить без видео", "record_video_request:no"),
        ]
    logger.debug(f"Video record request options set: {video_record_request_options}")
    selected_button_text = None
    # find selected button text from callback_data
    for button_text, callback_code in video_record_request_options:
        if selected_callback_code == callback_code:
            selected_button_text = button_text
            # Clear video record request options from "context" object, because now use "selected_button_text" variable instead
            context.user_data.pop("video_record_request_options", None)
            break
    logger.debug(f"Selected button text: {selected_button_text}")
    logger.debug(f"Context user data: {context.user_data}")

    # ----- INFORM USER about selected option -----

    if selected_button_text:
        await send_message_to_user(update, context, text=f"Вы выбрали: '{selected_button_text}'")
    else:
        # No option identified, inform user and return
        if update.callback_query and update.callback_query.message:
            await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        return

    # ----- UPDATE USER RECORDS with selected vacancy data and infrom user -----

    # Now you can use callback_data or selected_option for your logic
    if update.callback_query and update.callback_query.message:
        logger.debug(f"Selected callback code: {selected_callback_code}")
        if selected_callback_code is None:
            await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
            return
        video_record_request_user_decision = get_decision_status_from_selected_callback_code(selected_callback_code=selected_callback_code)
        logger.debug(f"Video record request user decision: {video_record_request_user_decision}")
        # Update user records with selected vacancy data
        update_user_records_with_top_level_key(record_id=bot_user_id, key="vacancy_video_record_agreed", value=video_record_request_user_decision)
        logger.debug(f"User records updated")
    
    # ----- PROGRESS THROUGH THE VIDEO FLOW BASED ON THE USER'S RESPONSE -----

    # ----- IF USER CHOSE "YES" send instructions to shoot video -----

    if video_record_request_user_decision == "yes":
        logger.debug(f"Video record request user decision is yes")
        await send_message_to_user(update, context, text=INSTRUCTIONS_TO_SHOOT_VIDEO_TEXT)
        await asyncio.sleep(1)
        await send_message_to_user(update, context, text=INFO_DROP_VIDEO_HERE_TEXT)
        
        # ----- NOW HANDLER LISTENING FOR VIDEO from user -----

        # this line just for info that handler will work from "create_manager_application" method in file "manager_bot.py"
        # once handler will be triggered, it will trigget "handle_video" method from file "services.video_service.py"

    # ----- IF USER CHOSE "NO" inform user about need to continue without video -----

    else:
        await send_message_to_user(update, context, text=CONTINUE_WITHIOUT_WELCOME_VIDEO_TEXT)

        # ----- READ VACANCY DESCRIPTION -----

        await read_vacancy_description_command(update=update, context=context)


async def ask_confirm_sending_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Ask confirm sending video command handler. 
    Called from: 'process_incoming_video' from file "services.video_service.py".
    Triggers: nothing. """

    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"ask_confirm_sending_video_command started. user_id: {bot_user_id}")

    # Build options (which will be tuples of (button_text, callback_data))
    answer_options = [
        ("Да. Отправить это.", "sending_video_confirmation:yes"),
        ("Нет. Попробую еще раз.", "sending_video_confirmation:no"),
    ]
    # Store button_text and callback_data options in context to use it later for button _text identification as this is not stored in "update.callback_query" object
    context.user_data["sending_video_confirmation_answer_options"] = answer_options
    await ask_question_with_options(update, context, question_text=VIDEO_SENDING_CONFIRMATION_TEXT, answer_options=answer_options)


async def handle_answer_confrim_sending_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Handle button click.
    Called from: nowhere.
    Triggers commands:
    - If user agrees to send video, triggers 'download_incoming_video_locally' method.
    - If user does not agree to send video, inform that waiting for another video to be sent by user.
    """
    
    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"handle_answer_confrim_sending_video triggered by user_id: {bot_user_id}")

    # ------- UNDERSTAND WHAT BUTTON was clicked and get "callback_data" from it -------

    # Get the "callback_data" extracted from "update.callback_query" object created once button clicked
    selected_callback_code = await handle_answer(update, context)

    # ----- UNDERSTAND TEXT on clicked buttton from option taken from context -----

    # Get options from context or return empty list [] if not found
    sending_video_confirmation_answer_options = context.user_data.get("sending_video_confirmation_answer_options", [])
    # find selected button text from callback_data
    for button_text, callback_code in sending_video_confirmation_answer_options:
        if selected_callback_code == callback_code:
            selected_button_text = button_text
            # Clear sending video confirmation answer options from "context" object, because now use "selected_button_text" variable instead
            context.user_data.pop("sending_video_confirmation_answer_options", None)
            break

    # ----- INFORM USER about selected option -----

    # If "options" is NOT an empty list execute the following code
    if sending_video_confirmation_answer_options:
        await send_message_to_user(update, context, text=f"Вы выбрали: '{selected_button_text}'")
    else:
        # No options available, inform user and return
        if update.callback_query and update.callback_query.message:
            await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        return

    # ----- UPDATE USER RECORDS with selected vacancy data -----

    # Now you can use callback_data or selected_option for your logic
    if update.callback_query and update.callback_query.message:
        if selected_callback_code is None:
            await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
            return
        sending_video_confirmation_user_decision = get_decision_status_from_selected_callback_code(selected_callback_code=selected_callback_code)
        # Update user records with selected vacancy data
        update_user_records_with_top_level_key(record_id=bot_user_id, key="vacancy_video_sending_confirmed", value=sending_video_confirmation_user_decision)

    # ----- IF USER CHOSE "YES" start video download  -----

    if sending_video_confirmation_user_decision == "yes":
        
        # ----- GET VIDEO DETAILS from message -----

        # Get file_id and video_kind from user_data
        file_id = context.user_data.get("pending_file_id")
        video_kind = context.user_data.get("pending_kind")

        # ----- DOWNLOAD VIDEO to local storage -----
        logger.debug(f"Downloading video to local storage...")
        await download_incoming_video_locally(
            update=update,
            context=context,
            tg_file_id=file_id,
            user_id=bot_user_id,
            file_type=video_kind
        )

        # ----- UPDATE USER RECORDS with video status and path -----
        # skipping as updated in "download_incoming_video_locally" method

        # ----- IF VIDEO NOT FOUND, ask for another video -----

        if not file_id:
            logger.warning("No file_id found in user_data")
            await send_message_to_user(update, context, text=MISSING_VIDEO_RECORD_TEXT)
            return

    else:

    # ----- IF USER CHOSE "NO" ask for another video -----

        await send_message_to_user(update, context, text=WAITING_FOR_ANOTHER_VIDEO_TEXT)


async def select_vacancy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [vacancy_related]
    """Asks users to select a vacancy to work with. 
    Called from: 'pull_user_data_from_hh_command'.
    Triggers: nothing.
    Sends notification to admin if fails"""
    
    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"select_vacancy_command started. user_id: {bot_user_id}")
        access_token = get_access_token_from_records(bot_user_id=bot_user_id)

        # ----- CHECK IF Privacy confirmed and VACANCY is selected and STOP if it is -----

        if not is_manager_privacy_policy_confirmed(bot_user_id=bot_user_id):
            await send_message_to_user(update, context, text=MISSING_PRIVACY_POLICY_CONFIRMATION_TEXT)
            return

        if is_vacancy_selected(record_id=bot_user_id):
            await send_message_to_user(update, context, text=SUCCESS_TO_SELECT_VACANCY_TEXT)
            return

        # ----- PULL ALL OPEN VACANCIES from HH and enrich records with it -----

        employer_id = get_employer_id_from_records(record_id=bot_user_id)
        if not employer_id:
            await send_message_to_user(update, context, text=FAILED_TO_GET_OPEN_VACANCIES_TEXT)
            # Raise exception to be caught by outer try-except block (which will notify admin)
            raise ValueError(f"No employer id found for user {bot_user_id}")

        # Get open vacancies from HH.ru API
        all_employer_vacancies = get_employer_vacancies_from_hh(access_token=access_token, employer_id=employer_id)
        if all_employer_vacancies is None:
            await send_message_to_user(update, context, text=FAILED_TO_GET_OPEN_VACANCIES_TEXT)
            # Raise exception to be caught by outer try-except block (which will notify admin)
            raise ValueError(f"No open vacancies found for user {bot_user_id}")
        # Filter only open vacancies (id, name tuples)
        vacancy_status = VACANCY_STATUS_TO_FILTER
        # get nested dict with open vacancies {id: {id, name, status=open}}
        open_employer_vacancies_dict = filter_open_employer_vacancies(vacancies_json=all_employer_vacancies, status_to_filter=vacancy_status)
        
        # If dict is empty => no open vacancies, inform user and raise exception
        if not open_employer_vacancies_dict:
            await send_message_to_user(update, context, text=FAILED_TO_GET_OPEN_VACANCIES_TEXT)
            # Raise exception to be caught by outer try-except block (which will notify admin)
            raise ValueError(f"No open vacancies found for user {bot_user_id}")

        # ----- ASK USER what vacancy to work on -----

        # Initialize options for user to select a vacancy (from JSON/dict)
        # Build options (which will be tuples of (vacancy_name, vacancy_id)) from dict: key is vacancy_id, value is {id, name, ...}
        answer_options = []
        for vacancy_id, vacancy_data in open_employer_vacancies_dict.items():
            if not vacancy_data:
                continue
            vacancy_name = vacancy_data.get("name")
            if vacancy_name:
                answer_options.append((vacancy_name, vacancy_id))
        # Store options in context so handler can access them
        context.user_data["vacancy_options"] = answer_options
        await ask_question_with_options(update, context, question_text="Выберите c какой из вакансий вы хотите работать.", answer_options=answer_options)
    
    except Exception as e:
        logger.error(f"Failed to select vacancy: {e}", exc_info=True)        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error selecting vacancy: {e}\nUser ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def handle_answer_select_vacancy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [vacancy_related]
    """Handle button click.
    Called from: nowhere.
    Triggers 'ask_to_record_video_command'.

    Saves selected vacancy data to records, vacancy description and available employer_states_and_collections to vacancy directory.
    This is called AUTOMATICALLY by Telegram when a button is clicked (via CallbackQueryHandler).
    The options list should be stored in context.user_data["vacancy_options"] when asking the question.
    
    Note: Bot knows which user clicked because:
    - update.effective_user.id contains the user ID (works for both messages and callbacks)
    - context.user_data is automatically isolated per user by python-telegram-bot framework
    Sends notification to admin if fails
    """
    
    try:
        # ----- IDENTIFY USER and pull required data from records -----
        
        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        logger.info(f"handle_answer_select_vacancy started. user_id: {bot_user_id}")
        
        # ------- UNDERSTAND WHAT BUTTON was clicked and get "callback_data" from it -------

        # Get the callback_data from the button click
        callback_data = await handle_answer(update, context)

        # ------- CREATE VACANCY DIRECTORY  for selected vacancy and NESTED RESUMES DIRECTORIES  -------

        target_vacancy_id = str(callback_data)
        logger.debug(f"Target vacancy id: {target_vacancy_id}")
        if target_vacancy_id:
            create_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
            create_video_from_managers_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
            create_video_from_applicants_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
            create_resumes_directory_and_subdirectories(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_subdirectories=RESUME_SUBDIRECTORIES_LIST)
            create_resume_records_file(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
        else:
            raise ValueError(f"No target_vacancy_id {target_vacancy_id} found in callback_data")
        
        # ----- PULL OPTIONS from context (stored when question asked) -----

        # Get options from context (stored when question was asked)
        answer_options=context.user_data.get("vacancy_options", [])
        if not answer_options:
            raise ValueError(f"No answer_options available in context")
        
        # ----- FIND SELECTED OPTION from options list and store it in variable -----

        # Find the selected option
        selected_option = None
        for button_text, callback_code in answer_options:
            # Compare as strings to avoid type mismatches (e.g., int vs str)
            if str(callback_data) == str(callback_code):
                selected_option = (button_text, callback_code)
                # Clear vacancy options from "context" object, because now use "selected_option" variable instead
                context.user_data.pop("vacancy_options", None)
                break

        # ----- UPDATE USER RECORDS with selected vacancy data and infrom user -----

        # Now you can use callback_data or selected_option for your logic
        if update.callback_query and update.callback_query.message:
            vacancy_name_value = selected_option[0]
            vacancy_id_value = selected_option[1]
            # Update user records with selected vacancy data
            update_user_records_with_top_level_key(record_id=bot_user_id, key="vacancy_selected", value="yes")
            update_user_records_with_top_level_key(record_id=bot_user_id, key="vacancy_name", value=vacancy_name_value)
            update_user_records_with_top_level_key(record_id=bot_user_id, key="vacancy_id", value=vacancy_id_value)
            # Inform user that selected vacancy is being processed
            if selected_option:
                vacancy_name, vacancy_id = selected_option
                await send_message_to_user(update, context, text=f"Вы выбрали вакансию:\n'{vacancy_name}'")
                await asyncio.sleep(2)

        # ----- ASK USER to record welcome video -----

        await ask_to_record_video_command(update=update, context=context)
    

    except Exception as e:
        logger.error(f"Failed to handle answer select vacancy: {e}", exc_info=True)
        await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error handling answer select vacancy: {e}\nUser ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def read_vacancy_description_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [vacancy_related]
    """Read vacancy description and save it. 
    Called from: 'download_incoming_video_locally' from file "services.video_service.py".
    Triggers: 'define_sourcing_criterias_command'.
    Sends notification to admin if fails"""
    
    # ----- IDENTIFY USER and pull required data from records -----
    
    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"read_vacancy_description_command started. user_id: {bot_user_id}")
    access_token = get_access_token_from_records(bot_user_id=bot_user_id)
    target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)
    target_vacancy_name = get_target_vacancy_name_from_records(record_id=bot_user_id)
    
    # ----- VALIDATE VACANCY IS SELECTED and has description and sourcing criterias exist -----

    validations = [
        (is_vacancy_selected, MISSING_VACANCY_SELECTION_TEXT)
    ]
    
    for check_func, error_text in validations:
        if not check_func(record_id=bot_user_id):
            logger.error(f"Validation failed: {error_text}")
            await send_message_to_user(update, context, text=error_text)
            return

    try:

        # ----- IF FILE with VACANCY DESCRIPTION already exists then SKIP PULLING it from HH -----

        vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
        vacancy_description_file_path = vacancy_data_dir / "vacancy_description.json"
        if vacancy_description_file_path.exists():
            logger.warning(f"Vacancy description file already exists: {vacancy_description_file_path}")
            return

        # ----- PULL VACANCY DESCRIPTION from HH and save it to file -----

        vacancy_description = get_vacancy_description_from_hh(access_token=access_token, vacancy_id=target_vacancy_id)
        if vacancy_description is None:
            logger.error(f"Failed to get vacancy description from HH: {target_vacancy_name}")
            return
        
        await send_message_to_user(update, context, text=f"Читаю описание вакансии '{target_vacancy_name}'.")
        
        # ----- SAVE VACANCY DESCRIPTION to file and update records -----

        create_json_file_with_dictionary_content(file_path=vacancy_description_file_path, content_to_write=vacancy_description)
        update_user_records_with_top_level_key(record_id=bot_user_id, key="vacancy_description_recieved", value="yes")
        
        # ----- TRIGGER DEFINE SOURCING CRITERIAS COMMAND -----

        await define_sourcing_criterias_command(update=update, context=context)
    
    except Exception as e:
        logger.error(f"Failed to read vacancy description: {e}", exc_info=True)
        await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error reading vacancy description: {e}\nUser ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def define_sourcing_criterias_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [vacancy_related]
    """Prepare everything for vacancy description analysis and 
    create TaksQueue job to get sourcing criteria from AI and save it to file.
    Called from: 'read_vacancy_description_command'.
    Triggers: nothing.
    """

    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"define_sourcing_criterias_command started. user_id: {bot_user_id}")
    target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)

    # ----- VALIDATE VACANCY IS SELECTED and has description and sourcing criterias exist -----

    validations = [
        (is_vacancy_selected, MISSING_VACANCY_SELECTION_TEXT),
        (is_vacancy_description_recieved, MISSING_VACANCY_DESCRIPTION_TEXT),
    ]
    
    for check_func, error_text in validations:
        if not check_func(record_id=bot_user_id):
            logger.error(f"Validation failed: {error_text}")
            await send_message_to_user(update, context, text=error_text)
            return

    try:
        # ----- IDENTIFY USER and pull required data from records -----

        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)

        # ----- CHECK IF SOURCING CRITERIA is already derived and STOP if it is -----

        if is_sourcing_criterias_file_exists(record_id=bot_user_id, vacancy_id=target_vacancy_id):
            await send_message_to_user(update, context, text=SUCCESS_TO_GET_SOURCING_CRITERIAS_TEXT)
            return

        # ----- DO AI ANALYSIS of the vacancy description  -----

        # Get files paths for AI analysis
        vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
        vacancy_description_file_path = vacancy_data_dir / "vacancy_description.json"
        prompt_file_path = Path(PROMPT_DIR) / "for_vacancy.txt"

        await send_message_to_user(update, context, text="Анализирую вакансию. Это может занять некоторое время. Я нашипу в чат когда будет готово.")

        # Load inputs for AI analysis
        with open(vacancy_description_file_path, "r", encoding="utf-8") as f:
            vacancy_description = json.load(f)
        with open(prompt_file_path, "r", encoding="utf-8") as f:
            prompt_text = f.read()


        # Add AI analysis task to queue
        await ai_task_queue.put(
            get_sourcing_criterias_from_ai_and_save_to_file,
            vacancy_description,
            prompt_text,
            vacancy_data_dir,
            update,
            context,
            task_id=f"vacancy_analysis_{bot_user_id}_{target_vacancy_id}"
        )
    except Exception as e:
        logger.error(f"Error in define_sourcing_criterias_command: {e}", exc_info=True)
        await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error in define_sourcing_criterias_command: {e}\nUser ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def get_sourcing_criterias_from_ai_and_save_to_file(
    vacancy_description: dict,
    prompt_text: str,
    vacancy_data_dir: Path,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
    ) -> None:
    # TAGS: [vacancy_related]
    """
    Wrapper function to process vacancy analysis result.
    This function is executed through TaskQueue.
    """

    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"get_sourcing_criterias_from_ai_and_save_to_file started. user_id: {bot_user_id}")

    try:
        
        # ----- CALL AI ANALYZER -----

        vacancy_analysis_result = analyze_vacancy_with_ai(
            vacancy_data=vacancy_description,
            prompt_vacancy_analysis_text=prompt_text
        )
        
        # ----- SAVE SOURCING CRITERIAS to file and update records -----

        sourcing_file_path = Path(vacancy_data_dir) / "sourcing_criterias.json"
        with open(sourcing_file_path, "w", encoding="utf-8") as f:
            json.dump(vacancy_analysis_result, f, ensure_ascii=False, indent=2)
        
        update_user_records_with_top_level_key(record_id=bot_user_id, key="vacancy_sourcing_criterias_recieved", value="yes")

        # Format and send result to user
        formatted_result = format_vacancy_analysis_result_for_markdown(str(sourcing_file_path))
        await send_message_to_user(
            update,
            context,
            text=f"Проанализировал вакансию и буду отбирать кандидатов по следующим критериям:\n\n{formatted_result}",
            parse_mode=ParseMode.MARKDOWN
        )
        await asyncio.sleep(1)
        await send_message_to_user(update, context, text=SUCCESS_TO_START_SOURCING_TEXT)
        
    except Exception as e:
        logger.error(f"Failed to process vacancy analysis: {e}", exc_info=True)        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error getting sourcing criterias from AI: {e}\nUser ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )




########################################################################################
# ------------ COMMANDS EXECUTED on ADMIN request ------------
########################################################################################


async def source_negotiations_triggered_by_admin_command(bot_user_id: str) -> None:
    # TAGS: [resume_related]
    """Sources negotiations collection."""
    
    logger.info(f"source_negotiations_triggered_by_admin_command started. user_id: {bot_user_id}")

    # ----- IDENTIFY USER and pull required data from records -----
    
    access_token = get_access_token_from_records(bot_user_id=bot_user_id)
    target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)

    # ----- IMPORTANT: do not check if NEGOTIATIONS COLLECTION file exists, we update it every time -----

    # ----- PULL COLLECTIONS of negotiations and save it to file -----

    #Define what employer_state to use for pulling the collection
    target_employer_state = TARGET_EMPLOYER_STATE_COLLECTION_STATUS
    #Build path to the file for the collection of negotiations data
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
    negotiations_collection_file_path = vacancy_data_dir / f"negotiations_collections_{target_employer_state}.json"
    
    #Get collection of negotiations data for the target collection status "consider"
    negotiations_collection_data = get_negotiations_by_collection(access_token=access_token, vacancy_id=target_vacancy_id, collection=target_employer_state)
    # Write negotiations data JSON into negotiations_file_path
    # If file already exists, it will be overwritten.
    create_json_file_with_dictionary_content(file_path=str(negotiations_collection_file_path), content_to_write=negotiations_collection_data)


async def source_resumes_triggered_by_admin_command(bot_user_id: str) -> None:
    # TAGS: [resume_related]
    """Sources resumes from negotiations."""

    logger.info(f"source_resumes_triggered_by_admin_command: started. User_id: {bot_user_id}")
    
    # ----- IDENTIFY USER and pull required data from records -----
    
    access_token = get_access_token_from_records(bot_user_id=bot_user_id)
    target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)
    target_employer_state = TARGET_EMPLOYER_STATE_COLLECTION_STATUS
    
    # ----- CHECK IF NEGOTIATIONS COLLECTION file exists, otherwise trigger source negotiations command -----
    
    if not is_negotiations_collection_file_exists(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, target_employer_state=target_employer_state):
        return

    # ----- CHECK IF RESUME RECORDS file exists, otherwise trigger source resumes command -----
    
    if not is_resume_records_file_exists(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id):
        create_resumes_directory_and_subdirectories(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_subdirectories=RESUME_SUBDIRECTORIES_LIST)
        create_resume_records_file(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)

    # ----- SOURCE RESUMES IDs from negotiations collection -----

    #Build path to the file for the collection of negotiations data
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
    negotiations_collection_file_path = vacancy_data_dir / f"negotiations_collections_{target_employer_state}.json"
    #Open negotiations collection data file and get resumes IDs
    with open(negotiations_collection_file_path, "r", encoding="utf-8") as f:
        negotiations_collection_data = json.load(f)
    resume_ids_from_negotiations_collection = []
    tmp_resume_id_and_negotiation_id_dict = {}
    for negotiations_collection_item in negotiations_collection_data["items"]:
        #add resume_id to the list
        resume_ids_from_negotiations_collection.append(negotiations_collection_item["resume"]["id"])
        #key is resume_id, value is negotiation_id - required for updating resume records file and send message to the user
        tmp_resume_id_and_negotiation_id_dict[negotiations_collection_item["resume"]["id"]] = negotiations_collection_item["id"]
    logger.debug(f"source_resumes_triggered_by_admin_command: tmp_negotiation_id_dict: {tmp_resume_id_and_negotiation_id_dict}")
    logger.debug(f"source_resumes_triggered_by_admin_command: resume_ids: {resume_ids_from_negotiations_collection}")

    # ----- COLLECT RESUMES IDs from resume records -----
    
    # Create empty list of resume IDs from resume_records.json
    resumes_ids_in_resume_records = []
    # Get resume records file path and read existing resume IDs
    resume_records_file_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
    with open(resume_records_file_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)
        # Append all resume_ids (keys) from resume_records.json to the list
        resumes_ids_in_resume_records = list(resume_records.keys())
    
    # ----- FILTER ONLY FRESH RESUMES IDs not existing in resume records -----

    # Compare and exclude resume_ids that already exist in resume_records
    fresh_resume_ids_list = []
    for resume_id in resume_ids_from_negotiations_collection:
        if resume_id not in resumes_ids_in_resume_records:
            fresh_resume_ids_list.append(resume_id)
    logger.debug(f"source_resumes_triggered_by_admin_command: New resume IDs to process: {fresh_resume_ids_list}")

    # ----- PREPARE RESUME directory for 'new' resumes -----

    resume_data_dir = get_resume_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
    #Get path to the directory for new resumes
    new_resume_data_dir = Path(resume_data_dir) / "new"

    # ----- DOWNLOAD RESUMES from HH.ru to "new" resumes -----

    #Download resumes from HH.ru and save to file
    for resume_id in fresh_resume_ids_list:
        resume_file_path = new_resume_data_dir / f"resume_{resume_id}.json"
        resume_data = get_resume_info(access_token=access_token, resume_id=resume_id)
        # Write resume data JSON into resume_file_path
        create_json_file_with_dictionary_content(file_path=str(resume_file_path), content_to_write=resume_data)

        # ----- UPDATE RESUME_RECORDS file with new resume_record_id and contact data -----

        #Create new resume record in resume records file with specific structure
        create_record_for_new_resume_id_in_resume_records(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id)
 
         # ----- ENRICH RESUME_RECORDS file with resume data -----

        # Update resume records with new resume data
        negotiation_id = tmp_resume_id_and_negotiation_id_dict[resume_id]
        first_name = resume_data.get("first_name", "")
        last_name = resume_data.get("last_name", "")
        
        # Safely extract phone and email from contact array
        phone = ""
        email = ""
        contacts_list = resume_data.get("contact", [])
        
        for contact in contacts_list:
            # Handle both "value" and "contact_value" keys
            contact_data = contact.get("contact_value") or contact.get("value")
            
            # Skip if contact_data is None or not a string
            if not isinstance(contact_data, str):
                continue
            
            # Filter email by '@' sign
            if "@" in contact_data:
                email = contact_data
            elif not phone:
                # If it's a string but not email, assume it's phone (if phone not set yet)
                phone = contact_data
        
        # Log warning if contact data is missing
        if not phone and not email:
            logger.warning(f"source_resumes_triggered_by_admin_command: No contact information found for resume {resume_id}")
        elif not phone:
            logger.debug(f"source_resumes_triggered_by_admin_command: No phone found for resume {resume_id}, email: {email}")
        elif not email:
            logger.debug(f"source_resumes_triggered_by_admin_command: No email found for resume {resume_id}, phone: {phone}")

        update_resume_record_with_top_level_key(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id, key="negotiation_id", value=negotiation_id)
        update_resume_record_with_top_level_key(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id, key="first_name", value=first_name)
        update_resume_record_with_top_level_key(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id, key="last_name", value=last_name)
        update_resume_record_with_top_level_key(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id, key="phone", value=phone)
        update_resume_record_with_top_level_key(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id, key="email", value=email)

    logger.info(f"source_resumes_triggered_by_admin_command:Found {len(fresh_resume_ids_list)} new resumes")


async def analyze_resume_triggered_by_admin_command(bot_user_id: str) -> None:
    # TAGS: [resume_related]
    """Analyzes resume with AI. 
    Sorts resumes into "passed" or "failed" directories based on the final score. 
    Triggers 'send_message_to_applicants_command' and 'change_employer_state_command' for each resume.
    Does not trigger any other commands once done.
    """

    logger.info(f"analyze_resume_triggered_by_admin_command: started. User_id: {bot_user_id}")

    # ----- IDENTIFY USER and pull required data from records -----
    
    target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)

    # ----- PREPARE paths and files for AI analysis -----

    #Get files paths for AI analysis
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
    vacancy_description_file_path = vacancy_data_dir / "vacancy_description.json"
    sourcing_criterias_file_path = vacancy_data_dir / "sourcing_criterias.json"
    resume_analysis_prompt_file_path = Path(PROMPT_DIR) / "for_resume.txt"
    resume_data_dir = get_resume_directory(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
    new_resume_data_path = Path(resume_data_dir) / "new"
    passed_resume_data_path = Path(resume_data_dir) / "passed"
    failed_resume_data_path = Path(resume_data_dir) / "failed"

    # Load inputs for AI analysis
    with open(vacancy_description_file_path, "r", encoding="utf-8") as f:
        vacancy_description = json.load(f)
    with open(sourcing_criterias_file_path, "r", encoding="utf-8") as f:
        sourcing_criterias = json.load(f)
    with open(resume_analysis_prompt_file_path, "r", encoding="utf-8") as f:
        resume_analysis_prompt = f.read() 

    # ----- QUEUE RESUMES for AI ANALYSIS -----

    # Add resumes to AI analysis queue
    try:
        new_resume_data_path.mkdir(parents=True, exist_ok=True)
        new_resume_json_paths_list = list(new_resume_data_path.glob("*.json"))
        num_of_new_resumes = len(new_resume_json_paths_list)
        logger.debug(f"Total resumes: {num_of_new_resumes} in directory {new_resume_data_path}")
        queued_resumes = 0
        # Open each resume file and add AI analysis task to queue
        for resume_json_path in new_resume_json_paths_list:
            resume_id = resume_json_path.stem.split("_")[1]
            try:
                with open(resume_json_path, "r", encoding="utf-8") as rf:
                    resume_json = json.load(rf)
                
                # Add AI analysis task to queue
                await ai_task_queue.put(
                    resume_analysis_from_ai_to_user_sort_resume,
                    bot_user_id,
                    target_vacancy_id,
                    vacancy_description,
                    sourcing_criterias,
                    resume_id,
                    resume_json_path,
                    resume_json,
                    resume_analysis_prompt,
                    passed_resume_data_path,
                    failed_resume_data_path,
                    task_id=f"resume_analysis_{bot_user_id}_{target_vacancy_id}_{resume_id}"
                )
                queued_resumes += 1
                logger.info(f"Added resume {resume_id} to analysis queue. Total queued: {queued_resumes} out of {num_of_new_resumes}")
            except Exception as inner_e:
                logger.error(f"Failed to queue resume analysis for '{resume_json_path}': {inner_e}", exc_info=True)
    except Exception as e:
        logger.error(f"Failed to queue resumes for analysis in directory {new_resume_data_path}: {e}", exc_info=True)

    # ----- COMMUNICATE RESULT of QUEUING RESUMES -----
    logger.info(f"Added {queued_resumes} out of {num_of_new_resumes} resumes to analysis queue. Analysis is performed in background.")


async def resume_analysis_from_ai_to_user_sort_resume(
    bot_user_id: str,
    target_vacancy_id: str,
    vacancy_description: dict,
    sourcing_criterias: dict,
    resume_id: str,
    resume_json_path: Path,
    resume_json: dict,
    resume_analysis_prompt: str,
    passed_resume_data_path: Path,
    failed_resume_data_path: Path,
    ) -> None:
    """
    Wrapper function to process resume analysis result.
    This function is executed through TaskQueue.
    """
    try:
        # Call AI analyzer
        ai_analysis_result = analyze_resume_with_ai(
            vacancy_description=vacancy_description,
            sourcing_criterias=sourcing_criterias,
            resume_data=resume_json,
            prompt_resume_analysis_text=resume_analysis_prompt
        )
        
        # Update resume records with AI analysis results
        update_resume_record_with_top_level_key(
            bot_user_id=bot_user_id,
            vacancy_id=target_vacancy_id,
            resume_record_id=resume_id,
            key="ai_analysis",
            value=ai_analysis_result
        )
        
        # Send message to applicant
        await send_message_to_applicant_command(bot_user_id=bot_user_id, resume_id=resume_id)
        
        # Change employer state
        await change_employer_state_command(bot_user_id=bot_user_id, resume_id=resume_id)
        
        # Sort resume based on final score
        resume_final_score = int(ai_analysis_result.get("final_score", 0))
        if resume_final_score >= RESUME_PASSED_SCORE:
            shutil.move(resume_json_path, passed_resume_data_path)
            update_resume_record_with_top_level_key(
                bot_user_id=bot_user_id,
                vacancy_id=target_vacancy_id,
                resume_record_id=resume_id,
                key="resume_sorting_status",
                value="passed"
            )
        else:
            shutil.move(resume_json_path, failed_resume_data_path)
            update_resume_record_with_top_level_key(
                bot_user_id=bot_user_id,
                vacancy_id=target_vacancy_id,
                resume_record_id=resume_id,
                key="resume_sorting_status",
                value="failed"
            )
                   
    except Exception as e:
        logger.error(f"Failed to process resume analysis for {resume_id}: {e}", exc_info=True)


async def send_message_to_applicant_command(bot_user_id: str, resume_id: str) -> None:
    # TAGS: [resume_related]
    """Sends message to applicant. Triggers 'change_employer_state_command'."""
    
    # ----- IDENTIFY USER and pull required data from records -----
    
    access_token = get_access_token_from_records(bot_user_id=bot_user_id)
    target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)

    # ----- SEND MESSAGE TO APPLICANT  -----

    # Get negotiation ID from resume record
    negotiation_id = get_negotiation_id_from_resume_record(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id)
    # Create Telegram bot link for applicant
    tg_link = create_tg_bot_link_for_applicant(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_id=resume_id)
    negotiation_message_text = APPLICANT_MESSAGE_TEXT_WITHOUT_LINK + f"{tg_link}"
    logger.debug(f"Sending message to applicant for negotiation ID: {negotiation_id}")
    try:
        send_negotiation_message(access_token=access_token, negotiation_id=negotiation_id, user_message=negotiation_message_text)
        logger.info(f"Message to applicant for negotiation ID: {negotiation_id} has been successfully sent")
    except Exception as send_err:
        logger.error(f"Failed to send message for negotiation ID {negotiation_id}: {send_err}", exc_info=True)
        # stop method execution in this case, because no need to update resume_records and negotiations status
        return

    # ----- UPDATE RESUME_RECORDS file with new status of request to shoot resume video -----

    new_status_of_request_to_shoot_resume_video = "yes"
    update_resume_record_with_top_level_key(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id, key="request_to_shoot_resume_video_sent", value=new_status_of_request_to_shoot_resume_video)


async def change_employer_state_command(bot_user_id: str, resume_id: str) -> None:
    # TAGS: [resume_related]
    """Trigger send message to applicant command handler - allows users to send message to applicant."""

    logger.info(f"change_employer_state_command started. user_id: {bot_user_id}")
    
    # ----- IDENTIFY USER and pull required data from records -----
    
    access_token = get_access_token_from_records(bot_user_id=bot_user_id)
    target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)
    negotiation_id = get_negotiation_id_from_resume_record(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id)

   # ----- CHANGE EMPLOYER STATE  -----

    #await update.message.reply_text(f"Изменяю статус приглашения кандидата на {NEW_EMPLOYER_STATE}...")
    logger.debug(f"Changing collection status of negotiation ID: {negotiation_id} to {NEW_EMPLOYER_STATE_COLLECTION_STATUS}")
    try:
        change_collection_status_of_negotiation(
            access_token=access_token,
            negotiation_id=negotiation_id,
            collection_name=TARGET_EMPLOYER_STATE_COLLECTION_STATUS,
            new_state=NEW_EMPLOYER_STATE_COLLECTION_STATUS
        )
        logger.info(f"Collection status of negotiation ID: {negotiation_id} has been successfully changed to {NEW_EMPLOYER_STATE_COLLECTION_STATUS}")
    except Exception as status_err:
        logger.error(f"Failed to change collection status for negotiation ID {negotiation_id}: {status_err}", exc_info=True)


async def update_resume_records_with_fresh_video_from_applicants_command(bot_user_id: str, vacancy_id: str, application: Optional[Application] = None) -> None:
    # TAGS: [resume_related]
    """Update resume records with fresh videos from applicants directory.
    Sends notification to admin if fails"""

    logger.info(f"update_resume_records_with_fresh_video_from_applicants_command started. user_id: {bot_user_id}")
    
    try:
        # ----- PREPARE PATHS to video files -----

        video_from_applicants_dir = get_directory_for_video_from_applicants(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
        if video_from_applicants_dir is None:
            raise ValueError(f"update_resume_records_with_fresh_video_from_applicants_command: video_from_applicants directory is not found for bot user id: {bot_user_id}, vacancy id: {vacancy_id}")
        all_video_paths_list = list(video_from_applicants_dir.glob("*.mp4"))
        fresh_videos_list = []
        
        for video_path in all_video_paths_list:
            # Parse video path to get resume ID. Video shall have the following structure: 
            # - type #1: applicant_{applicant_user_id}_resume_{resume_id}_time_{timestamp}_note.mp4
            # - type #2: - applicant_{applicant_user_id}_resume_{resume_id}_time_{timestamp}.mp4
            resume_id = video_path.stem.split("_")[3]
            logger.debug(f"update_resume_records_with_fresh_video_from_applicants_command: Found applicant video. Video path: {video_path} / Resume ID: {resume_id}")
            # If video not recorded, update list and update resume records
            if not is_applicant_video_recorded(bot_user_id=bot_user_id, vacancy_id=vacancy_id, resume_id=resume_id):
                fresh_videos_list.append(resume_id)
                update_resume_record_with_top_level_key(bot_user_id=bot_user_id, vacancy_id=vacancy_id, resume_record_id=resume_id, key="resume_video_received", value="yes")
                update_resume_record_with_top_level_key(bot_user_id=bot_user_id, vacancy_id=vacancy_id, resume_record_id=resume_id, key="resume_video_path", value=str(video_path))
        
        logger.debug(f"update_resume_records_with_fresh_video_from_applicants_command: {len(fresh_videos_list)} fresh videos have been found and updated in resume records")
    
    except Exception as e:
        logger.error(f"update_resume_records_with_fresh_video_from_applicants_command: Failed to update resume records with fresh videos from applicants: {e}", exc_info=True)
        # Send notification to admin about the error
        if application:
            await send_message_to_admin(
                application=application,
                text=f"⚠️ Error update_resume_records_with_fresh_video_from_applicants_command: {e}\nUser ID: {bot_user_id}\nVacancy ID: {vacancy_id}"
            )


async def recommend_resumes_with_video_command(bot_user_id: str, application: Application) -> None:
    # TAGS: [recommendation_related]
    """Recommend resumes with video for all users.
    Sends notification to admin if fails"""

    logger.info(f"recommend_resumes_with_video_command started. user_id: {bot_user_id}")

    # ----- IDENTIFY USER and pull required data from records -----
        
    target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)
    target_vacancy_name = get_target_vacancy_name_from_records(record_id=bot_user_id)

    # ----- VALIDATE VACANCY IS SELECTED and has description and sourcing criterias exist -----

    validations = [
        (is_vacancy_selected, MISSING_VACANCY_SELECTION_TEXT),
        (is_vacancy_description_recieved, MISSING_VACANCY_DESCRIPTION_TEXT),
        (is_vacancy_sourcing_criterias_recieved, MISSING_SOURCING_CRITERIAS_TEXT),
    ]
    
    for check_func, error_text in validations:
        if not check_func(record_id=bot_user_id):
            logger.error(f"Validation failed: {error_text}")
            if application and application.bot:
                await application.bot.send_message(chat_id=int(bot_user_id), text=error_text)
            return

    try:

        # ----- GET LIST of RESUME IDs that have not been recommended yet -----

        passed_resume_ids_with_video = get_list_of_passed_resume_ids_with_video(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
        logger.debug(f"recommend_resumes_with_video_command: List of resume IDs with video: {passed_resume_ids_with_video} has been fetched.")

        # ----- COMMUNICATE SUMMARY of recommendation -----

        num_of_passed_resume_ids_with_video = len(passed_resume_ids_with_video)
        # if there are no suitable applicants, communicate the result
        if num_of_passed_resume_ids_with_video == 0:
            if application and application.bot:
                await application.bot.send_message(chat_id=int(bot_user_id), text=f"Вакансия: '{target_vacancy_name}'.\nПока нет подходящих кандидатов, записавших видео визитку.")
            else:
                logger.warning(f"recommend_resumes_with_video_command: Cannot send message to user {bot_user_id}: application or bot instance not provided")
            return

        summary_text = (
                f"Вакансия '{target_vacancy_name}'\n"
                f"Могу порекомендовать '{num_of_passed_resume_ids_with_video}' подходящих кандидатов, записавших видео визитки."
            )
        if application and application.bot:
            await application.bot.send_message(chat_id=int(bot_user_id), text=summary_text, parse_mode=ParseMode.HTML)
            await asyncio.sleep(1)
        else:
            logger.warning(f"recommend_resumes_with_video_command: Cannot send message to user {bot_user_id}: application or bot instance not provided")
        await asyncio.sleep(1)

        # ----- COMMUNICATE RESULT of resumes with video -----

        #set counter to number the recommendations
        recommendation_num = 1
        # build text based on data from resume records
        for resume_id in passed_resume_ids_with_video:

            # ----- GET RECOMMENDATION TEXT and VIDEO PATH for each applicant -----

            # Get recommendation text for each applicant
            recommendation_title = f"<b>Рекомендация #{recommendation_num}</b>\n"
            recommendation_body = get_resume_recommendation_from_resume_records(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id)
            recommendation_text = f"{recommendation_title}{recommendation_body}"

            # Get video file path for each applicant
            applicant_video_file_path = get_path_to_video_from_applicant_from_resume_records(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id, resume_record_id=resume_id)

            # ----- SEND RECOMMENDATION TEXT and VIDEO for each applicant -----
            
            if application and application.bot:
                await application.bot.send_message(chat_id=int(bot_user_id), text=recommendation_text, parse_mode=ParseMode.HTML)
                if applicant_video_file_path:
                    await application.bot.send_video(chat_id=int(bot_user_id), video=str(applicant_video_file_path))
                    logger.info(f"recommend_resumes_with_video_command: Video for resume {resume_id} has been successfully sent to user {bot_user_id}")
                    
                    # ----- SEND BUTTON TO INVITE APPLICANT TO INTERVIEW -----
                    # cannot use "questionnaire_service.py", because requires update and context objects
                    
                    # Create inline keyboard with invite button
                    # Validate values are not None and convert to strings
                    if not bot_user_id or not target_vacancy_id or not resume_id:
                        logger.error(f"recommend_resumes_with_video_command: Missing required values for callback_data. bot_user_id: {bot_user_id}, target_vacancy_id: {target_vacancy_id}, resume_id: {resume_id}")
                        raise ValueError(f"Missing required values for invite button callback_data")
                    
                    # Telegram callback_data limit is 64 bytes, so we need to ensure it's not too long
                    callback_data = f"{INVITE_TO_INTERVIEW_CALLBACK_PREFIX}:{bot_user_id}:{target_vacancy_id}:{resume_id}"
                    callback_data_bytes = len(callback_data.encode('utf-8'))
                    
                    if callback_data_bytes > 64:
                        logger.warning(f"recommend_resumes_with_video_command: Callback data too long ({callback_data_bytes} bytes), truncating resume_id")
                        # Calculate available space: prefix + separators + bot_user_id + target_vacancy_id
                        base_length = len(f"{INVITE_TO_INTERVIEW_CALLBACK_PREFIX}:{bot_user_id}:{target_vacancy_id}:")
                        max_resume_id_length = 64 - base_length - 1  # -1 for safety margin
                        if max_resume_id_length > 0:
                            truncated_resume_id = resume_id[:max_resume_id_length]
                            callback_data = f"{INVITE_TO_INTERVIEW_CALLBACK_PREFIX}:{bot_user_id}:{target_vacancy_id}:{truncated_resume_id}"
                        else:
                            logger.error(f"recommend_resumes_with_video_command: Cannot create valid callback_data, base length too long")
                            raise ValueError(f"Callback data base length exceeds Telegram limit")
                    
                    invite_button = InlineKeyboardButton(
                        text=BTN_INVITE_TO_INTERVIEW,
                        callback_data=callback_data
                    )
                    keyboard = InlineKeyboardMarkup([[invite_button]])
                    await application.bot.send_message(
                        chat_id=int(bot_user_id),
                        text=f"Хотите пригласить кандидата на интервью?", 
                        parse_mode=ParseMode.HTML,
                        reply_markup=keyboard
                    )
                else:
                    raise ValueError(f"recommend_resumes_with_video_command: Cannot send video to user {bot_user_id}: video file not found for resume {resume_id}")
            else:
                logger.warning(f"recommend_resumes_with_video_command: Cannot send message to user {bot_user_id}: application or bot instance not provided")
            recommendation_num += 1
    
    except Exception as e:
        logger.error(f"recommend_resumes_with_video_command: Failed to recommend resumes with video: {e}", exc_info=True)
        if application and application.bot:
            await application.bot.send_message(chat_id=int(bot_user_id), text=FAIL_TECHNICAL_SUPPORT_TEXT)
        # Send notification to admin about the error
        if application:
            await send_message_to_admin(
                application=application,
                text=f"⚠️ Error recommend_resumes_with_video_command: {e}\nUser ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )


async def handle_invite_to_interview_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [recommendation_related]
    """Handle invite to interview button click. Sends notification to admin.
    Sends notification to admin if fails"""

    logger.info(f"handle_invite_to_interview_button started. user_id: {bot_user_id}")
    
    if not update.callback_query:
        return
    
    try:
        # ----- IDENTIFY USER and pull required data from callback -----
        
        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        
        # Use handle_answer() from questionnaire_service to extract callback_data and handle keyboard removal
        callback_data = await handle_answer(update, context, remove_keyboard=True)
        
        if not callback_data or not callback_data.startswith(INVITE_TO_INTERVIEW_CALLBACK_PREFIX):
            raise ValueError(f"Invalid callback_data for invite to interview: {callback_data}")


        # ----- EXTRACT DATA from callback_data -----

        parts = callback_data.split(":")
        if len(parts) != 4:
            raise ValueError(f"Invalid callback_data format for invite to interview: {callback_data}")
        
        # Unpack (destruct) tuple to assign values from a list to variables.
        callback_prefix, user_id, vacancy_id, resume_id = parts
        vacancy_name = get_target_vacancy_name_from_records(record_id=user_id)

        # ----- SEND NOTIFICATION TO ADMIN -----
            
        if context.application:
            admin_message = (
                f"📞 Пользователь {user_id}.\n"
                f"хочет пригласить кандидата {resume_id} на интервью.\n"
                f"Вакансия: {vacancy_id}: {vacancy_name}.\n"
                f"Резюме кандидата: {resume_id}."
            )
            await send_message_to_admin(
                application=context.application,
                text=admin_message
            )
            
            # Confirm to user (keyboard already removed by handle_answer())
            await send_message_to_user(update, context, text=INVITE_TO_INTERVIEW_SENT_TEXT)
        else:
            raise ValueError(f"Invalid callback_data format for invite to interview: {callback_data}")
    except Exception as e:
        logger.error(f"Failed to handle invite to interview: {e}", exc_info=True)
        await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        # Send notification to admin about the error
        if context.application:
            await send_message_to_admin(
                application=context.application,
                text=f"⚠️ Error handling invite to interview: {e}\nUser ID: {bot_user_id if 'bot_user_id' in locals() else 'unknown'}"
            )



########################################################################################
# ------------ MAIN MENU related commands ------------
########################################################################################

async def user_status(bot_user_id: str) -> dict:
    status_dict = {}
    status_dict["bot_authorization"] = is_user_in_records(record_id=bot_user_id)
    status_dict["privacy_policy_confirmation"] = is_manager_privacy_policy_confirmed(bot_user_id=bot_user_id)
    status_dict["hh_authorization"] = is_user_authorized(record_id=bot_user_id)
    status_dict["vacancy_selection"] = is_vacancy_selected(record_id=bot_user_id)
    status_dict["welcome_video_recording"] = is_welcome_video_recorded(record_id=bot_user_id)
    target_vacancy_id = get_target_vacancy_id_from_records(record_id=bot_user_id)
    # depends on vacancy selection
    if target_vacancy_id: # not None
        status_dict["vacancy_description_recieved"] = is_vacancy_description_recieved(record_id=bot_user_id)
        status_dict["sourcing_criterias_recieved"] = is_vacancy_sourcing_criterias_recieved(record_id=bot_user_id)
        status_dict["resume_records_file_not_empty"] = is_resume_records_file_not_empty(bot_user_id=bot_user_id, vacancy_id=target_vacancy_id)
    else:
        status_dict["vacancy_description_recieved"] = False
        status_dict["sourcing_criterias_recieved"] = False
        status_dict["resume_records_file_not_empty"] = False
    return status_dict


async def build_user_status_text(bot_user_id: str, status_dict: dict) -> str:

    status_to_text_transcription = {
        "bot_authorization": " Авторизация в боте.",
        "privacy_policy_confirmation": " Согласие на обработку перс. данных.",
        "hh_authorization": " Авторизация в HeadHunter.",
        "vacancy_selection": " Выбор вакансии.",
        "welcome_video_recording": " Приветственное видео.",
        "vacancy_description_recieved": " Описание вакансии.",
        "sourcing_criterias_recieved": " Критерии отбора.",
        "resume_records_file_not_empty": " Резюме в работе.",
    }
    status_images = {True: "✅", False: "❌"}
    user_status_text = "Статус пользователя:\n"
    for key, value_bool in status_dict.items():
        status_image = status_images[value_bool]
        status_text = status_to_text_transcription[key]
        user_status_text += f"{status_image}{status_text}\n"

    target_vacancy_name = get_target_vacancy_name_from_records(record_id=bot_user_id)
    if target_vacancy_name: # not None
        user_status_text += f"\nВакансия в работе: {target_vacancy_name}.\n"
    return user_status_text


async def show_chat_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    # ----- IDENTIFY USER and pull required data from records -----
    
    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"show_chat_menu_command started. user_id: {bot_user_id}")
    status_dict = await user_status(bot_user_id=bot_user_id)
    status_text = await build_user_status_text(bot_user_id=bot_user_id, status_dict=status_dict)

    status_to_button_transcription = {
        "bot_authorization": "Авторизация в боте",
        "privacy_policy_confirmation": "Обработка перс. данных",
        "hh_authorization": "Авторизоваться на HeadHunter",
        "vacancy_selection": "Выбрать вакансию",
        "welcome_video_recording": "Записать приветственное видео",
        "vacancy_description_recieved": "Запросить описание вакансии",
        "sourcing_criterias_recieved": "Выработать критерии отбора",
        "resume_records_file_not_empty": "Получить рекомендации",
    }
    answer_options = []
    for key, value_bool in status_dict.items():
        # add button only if status is False (not completed)
        if key in status_to_button_transcription and value_bool == False:
            answer_options.append((status_to_button_transcription[key], "menu_action:" + key))
    logger.debug(f"Answer options for chat menu: {answer_options}")

    # ----- STORE ANSWER OPTIONS in CONTEXT -----
    
    context.user_data["chat_menu_action_options"] = answer_options
    
    # ----- SEND MESSAGE WITH STATUS AND BUTTONS USING ask_question_with_options -----
    
    # Always send status text, even if no options available
    if answer_options:
        await ask_question_with_options(
            update=update,
            context=context,
            question_text=status_text,
            answer_options=answer_options
        )
    else:
        # If no options, just send status text without buttons
        await send_message_to_user(update, context, text=status_text)


async def handle_chat_menu_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle chat menu action button clicks."""

    # ----- IDENTIFY USER and pull required data from records -----
    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"handle_chat_menu_action started. user_id: {bot_user_id}")
    
    # ------- UNDERSTAND WHAT BUTTON was clicked and get "callback_data" from it -------
    
    # Get the "callback_data" extracted from "update.callback_query" object created once button clicked
    selected_callback_code = await handle_answer(update, context)
    
    if not selected_callback_code:
        logger.warning("No callback_code received from handle_answer")
        await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        return
    
    # ----- UNDERSTAND TEXT on clicked button from option taken from context -----
    
    # Get options from context or return empty list [] if not found
    chat_menu_action_options = context.user_data.get("chat_menu_action_options", [])
    # find selected button text from callback_data
    selected_button_text = None
    for button_text, callback_code in chat_menu_action_options:
        if selected_callback_code == callback_code:
            selected_button_text = button_text
            # Clear chat menu action options from "context" object, because now use "selected_button_text" variable instead
            context.user_data.pop("chat_menu_action_options", None)
            break
    
    # ----- INFORM USER about selected option -----
    
    # If "options" is NOT an empty list execute the following code
    if chat_menu_action_options and selected_button_text:
        await send_message_to_user(update, context, text=f"Вы выбрали: '{selected_button_text}'")
    else:
        # No options available, inform user and return
        logger.warning(f"Could not find button text for callback_code '{selected_callback_code}'. Available options: {chat_menu_action_options}")
        if update.callback_query and update.callback_query.message:
            await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
        return
    
    # ----- EXTRACT ACTION from callback_data and route to appropriate command -----
    
    # Extract action from callback_data (format: "menu_action:action_name")
    action = get_decision_status_from_selected_callback_code(selected_callback_code=selected_callback_code)
    logger.debug(f"Extracted action from callback_code '{selected_callback_code}': '{action}'")
 

    if action == "bot_authorization":
        await start_command(update=update, context=context)
    elif action == "privacy_policy_confirmation" or action == "privacy_policy":
        await ask_privacy_policy_confirmation_command(update=update, context=context)
    elif action == "hh_authorization":
        await hh_authorization_command(update=update, context=context)
    elif action == "vacancy_selection":
        await select_vacancy_command(update=update, context=context)
    elif action == "welcome_video_recording":
        await ask_to_record_video_command(update=update, context=context)
    elif action == "vacancy_description_recieved":
        await read_vacancy_description_command(update=update, context=context)
    elif action == "sourcing_criterias_recieved":
        await define_sourcing_criterias_command(update=update, context=context)
    elif action == "resume_records_file_not_empty":
        bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
        await recommend_resumes_with_video_command(bot_user_id=bot_user_id, application=context.application)
    else:
        logger.warning(f"Unknown action '{action}' from callback_code '{selected_callback_code}'. Available actions: bot_authorization, privacy_policy_confirmation, privacy_policy, hh_authorization, hh_auth, select_vacancy, record_video, get_recommendations")
        await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)


async def handle_feedback_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Handle feedback button click. Sets flag to wait for user feedback message."""
        
    # ----- IDENTIFY USER and pull required data from records -----
    
    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"handle_feedback_button_click started. user_id: {bot_user_id}")

    # ----- SET WAITING FOR FEEDBACK FLAG TO TRUE -----

    # Reset flag and allow new feedback (user can click button again to send new message)
    context.user_data["waiting_for_feedback"] = True
    await send_message_to_user(update, context, text=FEEDBACK_REQUEST_TEXT)


async def handle_feedback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Handle feedback message from user. Forwards it to admin."""
    
    # ----- CHECK IF MESSAGE IS NOT EMPTY -----

    if not update.message:
        return
    
    # ----- IDENTIFY USER and pull required data from records -----

    bot_user_id = str(get_tg_user_data_attribute_from_update_object(update=update, tg_user_attribute="id"))
    logger.info(f"handle_feedback_message started. user_id: {bot_user_id}")
    
    # ----- CHECK FOR WAITING FOR FEEDBACK FLAG -----

    # if not waiting for feedback, ignore this message
    if not context.user_data.get("waiting_for_feedback", False):
        return  # Not waiting for feedback, ignore this message
    # if waiting for feedback, clear the flag (only allow 1 message)
    context.user_data["waiting_for_feedback"] = False

    # ----- GET FEEDBACK TEXT -----

    feedback_text = update.message.text.strip()
    
    # ----- FORWARD FEEDBACK TO ADMIN -----

    try:
        if context.application:
            # Get user info for admin message
            user_records_path = get_users_records_file_path()
            user_info = ""
            try:
                with open(user_records_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                    if is_user_in_records(record_id=bot_user_id):
                        username = records[bot_user_id].get("username", "N/A")
                        first_name = records[bot_user_id].get("first_name", "N/A")
                        last_name = records[bot_user_id].get("last_name", "N/A")
                        user_info = f"Пользователь: ID: {bot_user_id}, @{username}, {first_name} {last_name})"
                    else:
                        user_info = f"Пользователь ID: {bot_user_id}, не найден в records."
            except Exception as e:
                logger.error(f"Failed to get user info for feedback: {e}")
                user_info = f"Пользователь ID: {bot_user_id}"
            
            admin_message = f"⚠️  Обратная связь от пользователя\n\n{user_info}\n\nСообщение:\n{feedback_text}"
            await send_message_to_admin(
                application=context.application,
                text=admin_message
            )
            # Confirm to user
            await send_message_to_user(update, context, text=FEEDBACK_SENT_TEXT)
        else:
            logger.error("Cannot send feedback to admin: application not available")
            await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)
    except Exception as e:
        logger.error(f"Failed to send feedback to admin: {e}", exc_info=True)
        await send_message_to_user(update, context, text=FAIL_TECHNICAL_SUPPORT_TEXT)


async def handle_feedback_non_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TAGS: [user_related]
    """Handle non-text messages when waiting for feedback (reject audio, images, etc.)."""
    
    if not update.message:
        return
    
    # Check if we're waiting for feedback
    if not context.user_data.get("waiting_for_feedback", False):
        return  # Not waiting for feedback, ignore this message
    
    # User sent non-text content (audio, image, document, etc.)
    await send_message_to_user(update, context, text=FEEDBACK_ONLY_TEXT_ALLOWED_TEXT)


async def handle_bottom_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle custom manager menu buttons."""

    if not update.message:
        return

    message_text = (update.message.text or "").strip()

    if message_text == BTN_MENU:
        # Clear all unprocessed inline keyboards before showing status
        # IMPORTANT: to avoid showing old keyboards when user clicks "Статус" button to avoid data rewriting
        chat_id = update.message.chat.id
        await clear_all_unprocessed_keyboards(update, context, chat_id)
        await show_chat_menu_command(update, context)
    elif message_text == BTN_FEEDBACK:
        # Handle feedback button click
        await handle_feedback_button_click(update, context)




########################################################################################
# ------------  APPLICATION SETUP ------------
########################################################################################


def create_manager_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CallbackQueryHandler(handle_answer_select_vacancy, pattern=r"^\d+$"))
    application.add_handler(CallbackQueryHandler(handle_answer_video_record_request, pattern=r"^record_video_request:"))
    application.add_handler(CallbackQueryHandler(handle_answer_confrim_sending_video, pattern=r"^sending_video_confirmation:"))
    application.add_handler(CallbackQueryHandler(handle_answer_policy_confirmation, pattern=r"^privacy_policy_confirmation:"))
    application.add_handler(CallbackQueryHandler(handle_chat_menu_action, pattern=r"^menu_action:"))
    application.add_handler(CallbackQueryHandler(handle_invite_to_interview_button, pattern=r"^invite_to_interview:"))
    menu_buttons_pattern = f"^({re.escape(BTN_MENU)}|{re.escape(BTN_FEEDBACK)})$"
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(menu_buttons_pattern), handle_bottom_menu_buttons)
    )
    # Handler for feedback messages (text only, when waiting_for_feedback flag is set)
    # This handler must be added AFTER menu buttons handler to avoid conflicts
    # Exclude commands (~filters.COMMAND) so command handlers can process them first
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.Regex(menu_buttons_pattern) & ~filters.COMMAND, handle_feedback_message)
    )
    # Handler for non-text messages when waiting for feedback (reject audio, images, etc.)
    # This must be added BEFORE video handler so it can check the flag first
    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.TEXT & ~(filters.VIDEO | filters.VIDEO_NOTE | filters.Document.VIDEO),
            handle_feedback_non_text_message
        )
    )
    # this handler listens to all video messages and passes them to the video service - 
    # "MessageHandler" works specifically with messages, not callback queries
    # "filters.ALL & (filters.VIDEO | filters.VIDEO_NOTE | filters.Document.VIDEO)" means handler will work only with video messages
    # when handler is triggered, it calls the defined lambda function
    application.add_handler(MessageHandler(filters.ALL & (filters.VIDEO | filters.VIDEO_NOTE | filters.Document.VIDEO), lambda update, context: process_incoming_video(update, context)))
    return application


