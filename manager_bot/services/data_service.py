# TAGS: [status_validation], [get_data], [create_data], [update_data], [directory_path], [file_path], [persistent_keyboard], [format_data]

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)



from services.constants import (
    USERS_RECORDS_FILENAME, 
    RESUME_RECORDS_FILENAME,
    BOT_FOR_APPLICANTS_USERNAME,
    )

# ****** METHODS with TAGS: [create_data] ******

def create_data_directory() -> Path:
    # TAGS: [create_data],[directory_path]
    """Create a directory for all data."""
    data_dir = Path(os.getenv("USERS_DATA_DIR", "/users_data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"{data_dir} created or exists.")
    return data_dir


def create_user_directory(bot_user_id: str) -> Path:
    # TAGS: [create_data],[directory_path]
    """Create a subdirectory for a unique user in the parent directory and return the path."""
    data_dir = get_data_directory()
    user_data_dir = data_dir / f"bot_user_id_{bot_user_id}"
    # Create directory if it doesn't exist
    user_data_dir.mkdir(exist_ok=True)
    logger.debug(f"{user_data_dir} created or exists.")
    return user_data_dir


def create_vacancy_directory(bot_user_id: str, vacancy_id: str) -> Path:
    # TAGS: [create_data],[directory_path]
    """Create a subdirectory for a vacancy in the user directory and return the path.
    Also creates subdirectories for video from managers and video from applicants."""
    user_data_dir = get_user_directory(bot_user_id=bot_user_id)
    vacancy_data_dir = user_data_dir / f"vacancy_id_{vacancy_id}"
    if vacancy_data_dir.mkdir(exist_ok=True):
        logger.debug(f"{vacancy_data_dir} created.")
        return vacancy_data_dir
    else:
        logger.debug(f"{vacancy_data_dir} already exists.")
        return vacancy_data_dir


def create_video_from_managers_directory(bot_user_id: str, vacancy_id: str) -> Path:
    # TAGS: [create_data],[directory_path]
    """Create a subdirectory for video from managers in the vacancy directory and return the path."""
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    video_from_managers_data_path = create_custom_directory(parent_directory=vacancy_data_dir, new_directory_name="video_from_managers")
    logger.debug(f"'video_from_managers' directory {video_from_managers_data_path} created.")
    return video_from_managers_data_path


def create_video_from_applicants_directory(bot_user_id: str, vacancy_id: str) -> Path:
    # TAGS: [create_data],[directory_path]
    """Create a subdirectory for video from applicants in the vacancy directory and return the path."""
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    video_from_applicants_data_path = create_custom_directory(parent_directory=vacancy_data_dir, new_directory_name="video_from_applicants")
    logger.debug(f"'video_from_applicants' directory {video_from_applicants_data_path} created.")
    return video_from_applicants_data_path


def create_resumes_directory_and_subdirectories(bot_user_id: str, vacancy_id: str, resume_subdirectories: list[str]) -> None:
    # TAGS: [create_data],[directory_path]
    """Create directories for resumes and subdirectories for new, passed, failed resumes."""
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    resume_data_path = create_custom_directory(parent_directory=vacancy_data_dir, new_directory_name="resumes")
    logger.debug(f"'resumes' directory {resume_data_path} created.")
    for subdirectory in resume_subdirectories:
        create_custom_directory(parent_directory=resume_data_path, new_directory_name=subdirectory)


def create_custom_directory(parent_directory: Path, new_directory_name: str) -> Path:
    # TAGS: [create_data],[directory_path]
    """Create a new directory in the parent directory and return the path."""
    custom_dir = parent_directory / new_directory_name
    custom_dir.mkdir(exist_ok=True)
    logger.debug(f"{custom_dir} created or exists.")
    return custom_dir


def create_users_records_file() -> None:
    # TAGS: [create_data],[file_path]
    """Create a file with users data records if it doesn't exist."""
    data_dir = get_data_directory()
    users_records_file_path = data_dir / f"{USERS_RECORDS_FILENAME}.json"
    if not users_records_file_path.exists():
        users_records_file_path.write_text(json.dumps({}), encoding="utf-8")
        logger.debug(f"{users_records_file_path} created.")
    else:
        logger.debug(f"{users_records_file_path} already exists.")


def create_resume_records_file(bot_user_id: str, vacancy_id: str) -> None:
    # TAGS: [create_data],[file_path]
    """Create a file with resume data records if it doesn't exist."""
    resume_data_dir = get_resume_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    resume_records_file_path = resume_data_dir / f"{RESUME_RECORDS_FILENAME}.json"
    if not resume_records_file_path.exists():
        resume_records_file_path.write_text(json.dumps({}), encoding="utf-8")
        logger.debug(f"{resume_records_file_path} created.")
    else:
        logger.debug(f"{resume_records_file_path} already exists.")


def create_json_file_with_dictionary_content(file_path: Path, content_to_write: dict) -> None:
    # TAGS: [create_data],[file_path]
    """Create a JSON file from a dictionary.
    If file already exists, it will be overwritten."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(content_to_write, f, ensure_ascii=False, indent=2)
    logger.debug(f"Content written to {file_path}")


def create_record_for_new_user_in_records(record_id: str) -> None:
    # TAGS: [create_data]
    """Update records and create user directory."""    
    users_records_file_path = get_users_records_file_path()
    # Read existing data
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    # Define standard key-values for new user    
    standard_new_user_values = {
        "id": record_id,
        "username": "",
        "first_name": "",
        "last_name": "",
        "first_time_seen": datetime.now(timezone.utc).isoformat(),
        "privacy_policy_confirmed": "no",
        "privacy_policy_confirmation_time": "",
        "access_token_recieved": "no",
        "access_token": "",
        "access_token_expires_at": "",
        "data_from_hh": {},
        "vacancy_selected": "no",
        "vacancy_id": "",
        "vacancy_name": "",
        "vacancy_video_record_agreed": "no",
        "vacancy_video_sending_confirmed": "no",
        "vacancy_video_received": "no",
        "vacancy_video_path": "",
        "vacancy_description_recieved": "no",
        "vacancy_sourcing_criterias_recieved": "no",
    }
    # Check if bot_user_id is not in manager_users_records keys
    if record_id not in records:
        records[record_id] = standard_new_user_values
        users_records_file_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug(f"Record ID '{record_id}' added to records")
    else:
        logger.debug(f"Record ID '{record_id}' already exists in records, skipping update")


def create_record_for_new_resume_id_in_resume_records(bot_user_id: str, vacancy_id: str, resume_record_id: str) -> None:
    """Create a new resume record in the resume records file. TAGS: [create_data]"""

    #resume_records_path = Path(DATA_DIR) / f"bot_user_id_{bot_user_id}" / f"vacancy_id_{vacancy_id}" / "resumes" / f"{RESUME_RECORDS_FILENAME}.json"
    resume_records_path = get_resume_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    resume_records_file_path = resume_records_path / f"{RESUME_RECORDS_FILENAME}.json"
    # Read existing data
    with open(resume_records_file_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)
    
    # Convert user_id to string since JSON keys are always strings
    resume_record_id_str = str(resume_record_id)
    vacancy_name = get_target_vacancy_name_from_records(record_id=bot_user_id)

    if resume_record_id not in resume_records:
        resume_records[resume_record_id_str] = {
            "manager_bot_user_id": bot_user_id,
            "vacancy_id": vacancy_id,
            "vacancy_name": vacancy_name,
            "negotiation_id": "",
            "resume_id": resume_record_id,
            "first_name": "",
            "last_name": "",
            "phone": "",
            "email": "",
            "ai_analysis": {},
            "resume_sorting_status": "new",
            "request_to_shoot_resume_video_sent": "no",
            "resume_video_received": "no",
            "resume_video_path": "",
            "resume_recommended": "no",
            "resume_accepted": "no"
        }
        resume_records_file_path.write_text(json.dumps(resume_records, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"{resume_records_file_path} has been successfully created with new resume_record: {resume_record_id_str}")
    else:
        logger.debug(f"Skipping creation of new resume record: {resume_record_id_str} because it already exists in the file {resume_records_file_path}")


def create_oauth_link(state: str) -> str:
    """
    Get the OAuth link for HH.ru authentication.
    """
    hh_client_id = os.getenv("HH_CLIENT_ID")
    if not hh_client_id:
        raise ValueError("HH_CLIENT_ID is not set in environment variables")
    oauth_redirect_url = os.getenv("OAUTH_REDIRECT_URL")
    if not oauth_redirect_url:
        raise ValueError("OAUTH_REDIRECT_URL is not set in environment variables")
    auth_link = f"https://hh.ru/oauth/authorize?response_type=code&client_id={hh_client_id}&state={state}&redirect_uri={oauth_redirect_url}"
    return auth_link


def create_tg_bot_link_for_applicant(bot_user_id: str, vacancy_id: str, resume_id: str) -> str:
    """Create Telegram bot link for applicant to start the bot. TAGS: [create_data]
    When the user taps it, Telegram sends your bot /start <payload>
    The payload is read from message.from.id (Telegram user_id) and the <payload> in the same update and persist the mapping.
    Example: https://t.me/{BOT_FOR_APPLICANTS_USERNAME}?start={bot_user_id}_{vacancy_id}_{resume_id}"""
    payload = f"{bot_user_id}_{vacancy_id}_{resume_id}"
    return f"https://t.me/{BOT_FOR_APPLICANTS_USERNAME}?start={payload}"

# ****** METHODS with TAGS: [get_data] ******

def get_data_directory() -> Path:
    # TAGS: [get_data],[directory_path]
    """Get the directory path for user data."""
    data_dir = Path(os.getenv("USERS_DATA_DIR", "/users_data"))
    #return id if data_dir exists
    if data_dir.exists():
        return data_dir
    #create it and return the path if it doesn't exist
    else:
        data_dir = create_data_directory()
        return data_dir


def get_directory_for_video_from_managers(bot_user_id: str, vacancy_id: str) -> Path:
    # TAGS: [get_data],[directory_path]
    """Get the directory path for managers videos."""
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    managers_video_data_dir = vacancy_data_dir / "video_from_managers"
    if managers_video_data_dir.exists():
        logger.debug(f"get_directory_for_video_from_managers: 'video_from_managers' directory {managers_video_data_dir} exists.")
        return managers_video_data_dir
    else:
        logger.debug(f"get_directory_for_video_from_managers: 'video_from_managers' directory {managers_video_data_dir} does not exist.")
        return None


def get_directory_for_video_from_applicants(bot_user_id: str, vacancy_id: str) -> Path:
    # TAGS: [get_data],[directory_path]
    """Get the directory path for applicants videos."""
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    applicants_video_data_dir = vacancy_data_dir / "video_from_applicants"
    if applicants_video_data_dir.exists():
        logger.debug(f"get_directory_for_video_from_applicants: 'video_from_applicants' directory {applicants_video_data_dir} exists.")
        return applicants_video_data_dir
    else:
        logger.debug(f"get_directory_for_video_from_applicants: 'video_from_applicants' directory {applicants_video_data_dir} does not exist.")
        return None


def get_user_directory(bot_user_id: str) -> Path:
    # TAGS: [get_data],[directory_path]
    """Get the directory path for a user."""
    data_dir = get_data_directory()
    user_data_dir = data_dir / f"bot_user_id_{bot_user_id}"
    if user_data_dir.exists():
        logger.debug(f"{user_data_dir} exists.")
        return user_data_dir
    else:
        user_data_dir = create_user_directory(bot_user_id=bot_user_id)
        logger.debug(f"{user_data_dir} created.")
        return user_data_dir


def get_vacancy_directory(bot_user_id: str, vacancy_id: str) -> Path:
    # TAGS: [get_data],[directory_path]
    """Get the directory path for a vacancy."""
    user_data_dir = get_user_directory(bot_user_id=bot_user_id)
    vacancy_data_dir = user_data_dir / f"vacancy_id_{vacancy_id}"
    if vacancy_data_dir.exists():
        logger.debug(f"{vacancy_data_dir} exists.")
        return vacancy_data_dir
    else:
        vacancy_data_dir = create_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
        logger.debug(f"{vacancy_data_dir} created.")
        return vacancy_data_dir


def get_resume_directory(bot_user_id: str, vacancy_id: str) -> Path:
    # TAGS: [get_data],[directory_path]
    """Get the directory path for a resume."""
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    if vacancy_data_dir is None:
        return None
    resume_data_dir = vacancy_data_dir / "resumes"
    if resume_data_dir.exists():
        return resume_data_dir
    else:
        logger.debug(f"{resume_data_dir} not found")
        return None


def get_applicants_video_directory() -> Path:
    # TAGS: [get_data],[directory_path]
    """Get the directory path for a resume."""
    data_dir = get_data_directory()
    applicants_video_data_dir = data_dir / "applicants_video"
    if applicants_video_data_dir.exists():
        logger.debug(f"{applicants_video_data_dir} exists.")
        return applicants_video_data_dir
    else:
        applicants_video_data_dir = create_custom_directory(parent_directory=data_dir, new_directory_name="applicants_video")
        logger.debug(f"{applicants_video_data_dir} created.")
        return None


def get_users_records_file_path() -> Path:
    # TAGS: [get_data],[file_path]
    """Get the path for a users records file."""
    data_dir = get_data_directory()
    users_records_file_path = data_dir / f"{USERS_RECORDS_FILENAME}.json"
    if users_records_file_path.exists():
        return users_records_file_path
    else:
        users_records_file_path = create_users_records_file()
        return users_records_file_path


def get_resume_records_file_path(bot_user_id: str, vacancy_id: str) -> Path:
    # TAGS: [get_data],[file_path]
    """Get the path for a resume records file."""
    resume_data_dir = get_resume_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    if resume_data_dir is None:
        raise ValueError(f"Resume directory not found for user {bot_user_id} and vacancy {vacancy_id}. Vacancy directory may not exist or resumes directory may not be created.")
    resume_records_file_path = resume_data_dir / f"{RESUME_RECORDS_FILENAME}.json"
    if resume_records_file_path.exists():
        logger.debug(f"'{RESUME_RECORDS_FILENAME}' found in {resume_data_dir}")
        return resume_records_file_path
    else:
        # Create the file if it doesn't exist
        create_resume_records_file(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
        logger.debug(f"'{RESUME_RECORDS_FILENAME}' created in {resume_data_dir}")
        return resume_records_file_path


def get_tg_user_data_attribute_from_update_object(update: Update, tg_user_attribute: str) -> str | int | None | bool | list | dict:
    """Collects Telegram user data from context and returns it as a dictionary. TAGS: [get_data]"""
    tg_user = update.effective_user
    if tg_user:
        tg_user_attribute_value = tg_user.__getattribute__(tg_user_attribute)
        logger.debug(f"'{tg_user_attribute}': {tg_user_attribute_value} found in update.")
        return tg_user_attribute_value 
    else:
        logger.warning(f"'{tg_user_attribute}' not found in update. CHECK CORRECTNESS OF THE ATTRIBUTE NAME")
        return None


def get_decision_status_from_selected_callback_code(selected_callback_code: str) -> str:
    #TAGS: [get_data]
    """Extract the meaningful part of a callback code.
    Args:
        selected_callback_code (str): Selected callback code, e.g. 'action_code:value'
    Returns:
        str: The part after the last colon, or the original string if no colon is present.
    """
    if ":" in selected_callback_code:
        return selected_callback_code.split(":")[-1].strip()
    else:
        return selected_callback_code


def get_access_token_from_callback_endpoint_resp(endpoint_response: dict) -> Optional[str]:
    """Get access token from endpoint response. TAGS: [get_data]"""
    if isinstance(endpoint_response, dict):
        # return access_token if it exists in endpoint_response, otherwise return None
        return endpoint_response.get("access_token", None)
    else:
        logger.debug(f"'endpoint_response' is not a dictionary: {endpoint_response}")
        return None


def get_access_token_from_records(bot_user_id: str) -> Optional[str]:
    """Get access token from users records. TAGS: [get_data]"""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if bot_user_id in records:
        return records[bot_user_id]["access_token"]
    else:
        logger.debug(f"'access_token' not found for 'bot_user_id': {bot_user_id} in {users_records_file_path}")
        return None


def get_expires_at_from_callback_endpoint_resp(endpoint_response: dict) -> Optional[int]:
    """Get expires_at from endpoint response. TAGS: [get_data]"""
    if isinstance(endpoint_response, dict):
        return endpoint_response.get("expires_at", None)
    else:
        logger.debug(f"'endpoint_response' is not a dictionary: {endpoint_response}")
        return None


def get_target_vacancy_id_from_records(record_id: str) -> Optional[str]:
    """Get target vacancy id from users records. TAGS: [get_data]"""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        vacancy_id = records[record_id].get("vacancy_id")
        if vacancy_id and vacancy_id != "":
            return vacancy_id
    logger.debug(f"'target vacancy id' not found for 'bot_user_id': {record_id} in {users_records_file_path}")
    return None


def get_target_vacancy_name_from_records(record_id: str) -> Optional[str]:
    """Get target vacancy name from users records. TAGS: [get_data]"""
    users_records_file = get_users_records_file_path()
    with open(users_records_file, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        vacancy_name = records[record_id].get("vacancy_name")
        if vacancy_name and vacancy_name != "":
            return vacancy_name
    logger.debug(f"'target vacancy name' not found for 'bot_user_id': {record_id} in {users_records_file}")
    return None


def get_list_of_resume_ids_for_recommendation(bot_user_id: str, vacancy_id: str) -> list[str]:
    # TAGS: [get_data]
    """Get list of resume IDs for recommendation.
    Criterias:
    1. Resume is passed
    2. Resume has video
    3. Resume is not recommended yet
    """
    resume_records_file_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    with open(resume_records_file_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)

    recommendation_list = []
    for resume_id, resume_record_data in resume_records.items():
        # Check if resume is passed and not recommended yet without video
        if resume_record_data["resume_sorting_status"] == "passed":
            # Collect resume id for passed resumes WITH video
            if resume_record_data["resume_video_received"] == "yes":
                if resume_record_data["resume_recommended"] == "no":
                    recommendation_list.append(resume_id)
    logger.debug(f"get_list_of_resume_ids_for_recommendation: List of resume IDs for recommendation: {recommendation_list}")
    return recommendation_list


def get_negotiation_id_from_resume_record(bot_user_id: str, vacancy_id: str, resume_record_id: str) -> Optional[str]:
    # TAGS: [get_data]
    """Get negotiation id from resume record."""
    resume_records_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    with open(resume_records_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)
    return resume_records[resume_record_id]["negotiation_id"]


def get_resume_recommendation_text_from_resume_records(bot_user_id: str, vacancy_id: str, resume_record_id: str) -> str:
    # TAGS: [get_data]
    """Get resume recommendation text from resume records."""
    resume_records_file_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    # Read existing data
    with open(resume_records_file_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)
    
    resume_record_id_data = resume_records[resume_record_id]

    # ----- GET VALUES for TEXT -----

    first_name = resume_record_id_data["first_name"]
    last_name = resume_record_id_data["last_name"]
    final_score = resume_record_id_data["ai_analysis"]["final_score"]
    recommendation = resume_record_id_data["ai_analysis"]["recommendation"]
    attention = resume_record_id_data["ai_analysis"]["requirements_compliance"]["attention"]

    if not first_name or not last_name or not final_score or not recommendation or not attention:
        raise ValueError(f"Missing required values for recommendation text for 'resume_record_id': {resume_record_id}")
    
    # ----- FORMAT ATTENTION list to present each item on a new line -----

    if isinstance(attention, list):
        attention_text = "\n".join(f"- {item}" for item in attention)
    else:
        attention_text = str(attention)

    # ----- FORMAT RECOMMENDATION TEXT and send message -----

    recommendation_text = (
        f"<b>Имя</b>: {first_name} {last_name}\n"
        f"<b>Общий балл</b>: <b>{final_score}</b> из 10\n"
        f"--------------------\n"
        f"<b>Рекомендация:</b>\n{recommendation}\n"
        f"--------------------\n"
        f"<b>Обратить внимание:</b>\n{attention_text}"
    )
    return recommendation_text



def get_path_to_video_from_applicant_from_resume_records(bot_user_id: str, vacancy_id: str, resume_record_id: str) -> Path:
    """Get path to video from applicant from resume records. TAGS: [get_data]"""
    resume_records_file_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    # Read existing data
    with open(resume_records_file_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)
    video_path_value = resume_records[resume_record_id].get("resume_video_path")
    if video_path_value is None:
        raise ValueError(f"'resume_video_path' not found for 'resume_record_id': {resume_record_id}")
    return Path(video_path_value)


def get_reply_from_update_object(update: Update):
    """ Get user reply to from the update object if user did one of below. TAGS: [get_data].
    1. sent message (text, photo, video, etc.) - update.message OR
    2. clicked button - update.callback_query.message
    If none of the above, return None
    """
    if update.message:
        return update.message.reply_text
    elif update.callback_query and update.callback_query.message:
        return update.callback_query.message.reply_text
    else:
        return None


def get_employer_id_from_records(record_id: str) -> Optional[str]:
    """Get employer id from users records. TAGS: [get_data]"""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        employer_id = records[record_id]["data_from_hh"]["employer"]["id"]
        logger.debug(f"'employer_id': {employer_id} found for 'bot_user_id': {record_id} in {users_records_file_path}")
        return employer_id
    else:
        logger.debug(f"'record_id': {record_id} not found in {users_records_file_path}")
        return None


def get_list_of_users_from_records() -> list[str]:
    # TAGS: [get_data]
    """Get list of users from users records."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    return list(records.keys())


# ****** METHODS with TAGS: [update_data] ******

def update_user_records_with_top_level_key(record_id: int | str, key: str, value: str | int | bool | dict | list) -> None:
    """Only updates if the user_id exists in the JSON. TAGS: [update_data]"""
    users_records_path = get_users_records_file_path()
    # Read existing data
    with open(users_records_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    
    # Convert user_id to string since JSON keys are always strings
    record_id_str = str(record_id)
    
    if record_id_str in records:
        records[record_id_str][key] = value
        users_records_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"{record_id_str} has been successfully updated with {key}={value}")
    else:
        logger.debug(f"Skipping update: user_id {record_id_str} does not exist in the file")


def update_resume_record_with_top_level_key(bot_user_id: str, vacancy_id: str, resume_record_id: str, key: str, value: str | int | bool | dict | list) -> None:
    """Update resume record with new resume data. TAGS: [update_data]"""
    try:
        resume_records_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
        with open(resume_records_path, "r", encoding="utf-8") as f:
            resume_records = json.load(f)
        if resume_record_id in resume_records:
            resume_records[resume_record_id][key] = value
            resume_records_path.write_text(json.dumps(resume_records, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"{resume_records_path} has been successfully updated with {key}={value}")
        else:
            raise ValueError(f"Resume record {resume_record_id} does not exist in the file {resume_records_path}")
    except Exception as e:
        raise ValueError(f"Error updating resume record with top level key: {e}")

# ****** METHODS with TAGS: [persistent_keyboard] ******


def get_persistent_keyboard_messages(bot_user_id: str) -> list[tuple[int, int]]:
    # TAGS: [persistent_keyboard]
    """Get persistent keyboard message IDs for a user. Returns list of (chat_id, message_id) tuples."""
    users_records_file_path = get_users_records_file_path()
    try:
        with open(users_records_file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        if bot_user_id in records:
            keyboard_messages = records[bot_user_id].get("messages_with_keyboards", [])
            # Convert list of lists to list of tuples
            return [tuple(msg) for msg in keyboard_messages if isinstance(msg, (list, tuple)) and len(msg) == 2]
        return []
    except Exception as e:
        logger.error(f"Error reading keyboard messages for {bot_user_id}: {e}")
        return []


def add_persistent_keyboard_message(bot_user_id: str, chat_id: int, message_id: int) -> None:
    # TAGS: [persistent_keyboard]
    """Add a keyboard message ID to persistent storage."""
    users_records_file_path = get_users_records_file_path()
    try:
        with open(users_records_file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        bot_user_id_str = str(bot_user_id)
        if bot_user_id_str not in records:
            logger.debug(f"User {bot_user_id_str} not found in records, cannot track keyboard")
            return
        
        if "messages_with_keyboards" not in records[bot_user_id_str]:
            records[bot_user_id_str]["messages_with_keyboards"] = []
        
        # Add if not already present
        keyboard_messages = records[bot_user_id_str]["messages_with_keyboards"]
        if [chat_id, message_id] not in keyboard_messages:
            keyboard_messages.append([chat_id, message_id])
            records[bot_user_id_str]["messages_with_keyboards"] = keyboard_messages
            users_records_file_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug(f"Added keyboard message {message_id} to persistent storage for user {bot_user_id_str}")
    except Exception as e:
        logger.error(f"Error adding keyboard message to persistent storage: {e}")


def remove_persistent_keyboard_message(bot_user_id: str, chat_id: int, message_id: int) -> None:
    # TAGS: [persistent_keyboard]
    """Remove a keyboard message ID from persistent storage."""
    users_records_file_path = get_users_records_file_path()
    try:
        with open(users_records_file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        bot_user_id_str = str(bot_user_id)
        if bot_user_id_str not in records:
            return
        
        if "messages_with_keyboards" in records[bot_user_id_str]:
            keyboard_messages = records[bot_user_id_str]["messages_with_keyboards"]
            records[bot_user_id_str]["messages_with_keyboards"] = [
                msg for msg in keyboard_messages if not (msg[0] == chat_id and msg[1] == message_id)
            ]
            users_records_file_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug(f"Removed keyboard message {message_id} from persistent storage for user {bot_user_id_str}")
    except Exception as e:
        logger.error(f"Error removing keyboard message from persistent storage: {e}")


def clear_all_persistent_keyboard_messages(bot_user_id: str) -> None:
    # TAGS: [persistent_keyboard]
    """Clear all persistent keyboard messages for a user."""
    users_records_file_path = get_users_records_file_path()
    try:
        with open(users_records_file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        bot_user_id_str = str(bot_user_id)
        if bot_user_id_str in records:
            records[bot_user_id_str]["messages_with_keyboards"] = []
            users_records_file_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug(f"Cleared all persistent keyboard messages for user {bot_user_id_str}")
    except Exception as e:
        logger.error(f"Error clearing persistent keyboard messages: {e}")       


# ****** METHODS with TAGS: [format_data] ******

def format_oauth_link_text(oauth_link: str) -> str:
    # TAGS: [format_data]
    """Format oauth link text. TAGS: [format_data]"""
    return f"<a href=\"{oauth_link}\">Ссылка для авторизации</a>"
