# TAGS: [status_validation]


import json
import logging
from pathlib import Path
from services.data_service import (
    get_users_records_file_path,
    get_resume_records_file_path,
    get_vacancy_directory,
)

logger = logging.getLogger(__name__)



# ****** METHODS with TAGS: [status_validation] ******

def is_user_in_records(record_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if user is in records."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        return True
    else:
        logger.debug(f"'record_id': {record_id} not found in records")
        return False


def is_manager_privacy_policy_confirmed(bot_user_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if privacy policy is confirmed."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if bot_user_id in records:
        if records[bot_user_id]["privacy_policy_confirmed"] == "yes":
            logger.debug(f"privacy_policy is confirmed for 'bot_user_id': {bot_user_id} in {users_records_file_path}")
            return True
        else:
            logger.debug(f"privacy_policy is NOT confirmed for 'bot_user_id': {bot_user_id} in {users_records_file_path}")
            return False
    else:
        logger.debug(f"'bot_user_id': {bot_user_id} is not found in {users_records_file_path}")
        return False


def is_user_authorized(record_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if user is authorized."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        if records[record_id]["access_token_recieved"] == "yes":
            return True
        else:
            logger.debug(f"'bot_user_id': {record_id} is not authorized in {users_records_file_path}")
            return False
    else:
        logger.debug(f"'bot_user_id': {record_id} is not found in {users_records_file_path}")
        return False


def is_hh_data_in_user_record(record_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if HH data is in user record."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        data_from_hh = records[record_id].get("data_from_hh")
        # None or empty dictionary will be treated as False
        if data_from_hh:
            return True
        logger.debug(f"'data_from_hh' is None or empty for 'bot_user_id': {record_id} in {users_records_file_path}")
        return False
    else:
        logger.debug(f"'bot_user_id': {record_id} is not found in {users_records_file_path}")
        return False


def is_vacancy_selected(record_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if target vacancy is selected."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        if records[record_id]["vacancy_selected"] == "yes":
            return True
        logger.debug(f"'bot_user_id': {record_id} has no target vacancy selected.")
    return False


def is_vacancy_description_recieved(record_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if target vacancy description is received."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        if records[record_id]["vacancy_description_recieved"] == "yes":
            return True
        logger.debug(f"'bot_user_id': {record_id} has no target vacancy selected.")
    return False


def is_vacancy_sourcing_criterias_recieved(record_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if target vacancy sourcing criterias are received."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        if records[record_id]["vacancy_sourcing_criterias_recieved"] == "yes":
            return True
        logger.debug(f"'bot_user_id': {record_id} has no target vacancy selected.")
    return False


def is_agree_to_record_welcome_video(record_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if welcome video is agreed to record."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        if records[record_id]["vacancy_video_is_agreed_to_record"] == "yes":
            logger.debug(f"'bot_user_id': {record_id} has agreed to record welcome video.")
            return True
        else:
            logger.debug(f"'bot_user_id': {record_id} has not agreed to record welcome video.")
            return False
    else:
        logger.debug(f"'bot_user_id': {record_id} is not found in {users_records_file_path}")
        return False


def is_welcome_video_recorded(record_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if welcome video is recorded."""
    users_records_file_path = get_users_records_file_path()
    with open(users_records_file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if record_id in records:
        if records[record_id]["vacancy_video_record_agreed"] == "yes":
            logger.debug(f"'bot_user_id': {record_id} has welcome video recorded.")
            return True
        else:
            logger.debug(f"'bot_user_id': {record_id} has no welcome video recorded.")
            return False
    else:
        logger.debug(f"'bot_user_id': {record_id} is not found in {users_records_file_path}")
        return False


def is_sourcing_criterias_file_exists(record_id: str, vacancy_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if sourcing criterias are exist."""
    vacancy_data_dir = get_vacancy_directory(bot_user_id=record_id, vacancy_id=vacancy_id)
    sourcing_criterias_file_path = vacancy_data_dir / "sourcing_criterias.json"
    if sourcing_criterias_file_path.exists():
        logger.debug(f"'sourcing_criterias.json' found in {vacancy_data_dir}")
        return True
    else:
        logger.debug(f"'sourcing_criterias.json' not found in {vacancy_data_dir}")
        return False


def is_negotiations_collection_file_exists(bot_user_id: str, vacancy_id: str, target_employer_state: str) -> bool:
    # TAGS: [status_validation]
    """Check if negotiations collection file exists."""
    vacancy_data_dir = get_vacancy_directory(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    negotiations_collection_file_path = vacancy_data_dir / f"negotiations_collections_{target_employer_state}.json"
    if negotiations_collection_file_path.exists():
        logger.debug(f"'negotiations_collections_{target_employer_state}.json' found in {vacancy_data_dir}")
        return True
    else:
        logger.debug(f"'negotiations_collections_{target_employer_state}.json' not found in {vacancy_data_dir}")
        return False


def is_resume_records_file_exists(bot_user_id: str, vacancy_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if resume records file exists."""
    resume_records_file_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    if resume_records_file_path.exists():
        logger.debug(f"Resume records file found in {resume_records_file_path}")
        return True
    else:
        logger.debug(f"Resume records file not found in {resume_records_file_path}")
        return False


def is_resume_records_file_not_empty(bot_user_id: str, vacancy_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if resume records file is not empty."""
    resume_records_file_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    with open(resume_records_file_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)
    if resume_records:
        logger.debug(f"'{resume_records_file_path}' is not empty")
        return True
    else:
        logger.debug(f"'{resume_records_file_path}' is empty")
        return False


def is_resume_id_exists_in_resume_records(bot_user_id: str, vacancy_id: str, resume_record_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if resume record exists."""
    resume_records_file_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    with open(resume_records_file_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)
    if resume_record_id in resume_records.keys():
        logger.debug(f"'resume_id': {resume_record_id} found in {resume_records_file_path}")
        return True
    else:
        logger.debug(f"'resume_id': {resume_record_id} not found in {resume_records_file_path}")
        return False


def is_applicant_video_recorded(bot_user_id: str, vacancy_id: str, resume_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if applicant video is recorded."""
    resume_records_file_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    with open(resume_records_file_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)
    if resume_id in resume_records:
        return resume_records[resume_id]["resume_video_received"] == "yes"
    else:
        logger.debug(f"'resume_id': {resume_id} is not found in {resume_records_file_path}")
        return False


def is_vacany_data_enough_for_resume_analysis(user_id: str) -> bool:
    # TAGS: [status_validation]
    """
    Check if everything is ready for resume analysis.
    Validates that user is authorized, vacancy is selected, vacancy description is received, and sourcing criterias are received.
    """
    return (
        is_user_authorized(record_id=user_id) and
        is_vacancy_selected(record_id=user_id) and
        is_vacancy_description_recieved(record_id=user_id) and
        is_vacancy_sourcing_criterias_recieved(record_id=user_id)
    )


def is_resume_accepted(bot_user_id: str, vacancy_id: str, resume_id: str) -> bool:
    # TAGS: [status_validation]
    """Check if resume is accepted."""
    resume_records_file_path = get_resume_records_file_path(bot_user_id=bot_user_id, vacancy_id=vacancy_id)
    with open(resume_records_file_path, "r", encoding="utf-8") as f:
        resume_records = json.load(f)
    if resume_id in resume_records:
        return resume_records[resume_id]["resume_accepted"] == "yes"
    else:
        logger.debug(f"'resume_id': {resume_id} is not found in {resume_records_file_path}")
        return False