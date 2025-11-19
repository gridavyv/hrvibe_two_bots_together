# exchange_code.py
import os, requests, json
import sys
import logging
from typing import Optional
from pathlib import Path

from telegram._passport.passportdata import PassportData

from services.data_service import create_json_file_with_dictionary_content

logger = logging.getLogger(__name__)

HH_CLIENT_ID     = os.getenv("HH_CLIENT_ID")
HH_CLIENT_SECRET = os.getenv("HH_CLIENT_SECRET")
REDIRECT_URI     = os.getenv("OAUTH_REDIRECT_URL")
USER_AGENT       = os.getenv("USER_AGENT")


# ------------------------------ USER related calls ------------------------------

def get_user_info_from_hh(access_token: str) -> Optional[dict]:
    """Get user info from HH.ru API
    Args:
        access_token (str): Access token for HH.ru API
    Returns:
        dict: User info from HH.ru API or None if request failed
    """
    r = requests.get(
        "https://api.hh.ru/me",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
        },
        timeout=10,
    )
    r.raise_for_status()
    if r.status_code == 200:
        return r.json()
    else:
        logger.error(f"Error: {r.status_code} {r.text}")
        return None


def clean_user_info_received_from_hh(user_info: dict) -> dict:
    """Clean user info recieved from HH.ru API
    Args:
        user_info (dict): User info from HH.ru API
    Returns:
        dict: Cleaned user info with only the needed fields
    """
    cleaned_user_info = {
        "auth_type": user_info["auth_type"],
        "id": user_info["id"],
        "email": user_info["email"],
        "first_name": user_info["first_name"],
        "middle_name": user_info["middle_name"],
        "last_name": user_info["last_name"],
        "manager": user_info["manager"],
        "employer": user_info["employer"],
        "phone": user_info["phone"],
    }
    return cleaned_user_info

# ------------------------------ VACANCY related calls ------------------------------

def get_employer_vacancies_from_hh(access_token: str):
    r = requests.get(
        "https://api.hh.ru/employers/9163396/vacancies/active",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
        },
        timeout=10,
    )
    r.raise_for_status()
    if r.status_code == 200:
        logger.debug(f"request successful: {r.text}")
        return r.json()
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None


def filter_open_employer_vacancies(vacancies_json: dict, status_to_filter: str) -> dict:
    """
    Build a JSON-ready dict of open vacancies from HH.ru response.
    Args:
        vacancies_json (dict): JSON object from HH.ru API containing vacancies
    Returns:
        dict: {"<vacancy_id>": {"id": "<id>", "name": "<name>"}, ...}
    """
    result = {}

    # Get items list from JSON
    items = vacancies_json.get("items", [])

    # Extract id and name from each item with status open
    for item in items:
        # Validate that vacancy has status open ("type":{"id": "open"}
        item_type = item.get("type")
        if not item_type or item_type.get("id") != status_to_filter:
            continue

        vacancy_id = item.get("id")
        vacancy_name = item.get("name")

        if vacancy_id and vacancy_name:
            result[str(vacancy_id)] = {"id": str(vacancy_id), "name": vacancy_name, "status": status_to_filter}

    return result


def get_vacancy_description_from_hh(access_token: str, vacancy_id: str) -> Optional[dict]:
    """Get vacancy description from HH.ru API and return it as a dictionary"""
    r = requests.get(
        f"https://api.hh.ru/vacancies/{vacancy_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
        },
        timeout=10,
    )
    r.raise_for_status()
    if r.status_code == 200:
        logger.debug(f"request successful: {r.text}")
        return r.json()
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None

# ------------------------------ NEGOTIATIONS related calls ------------------------------

def get_available_employer_states_and_collections_negotiations(access_token: str, vacancy_id: str):
    """Returns the list of negotiations for a vacancy"""
    r = requests.get(
        "https://api.hh.ru/negotiations",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
        },
        params={
            "vacancy_id": vacancy_id
        },
        timeout=15,
    )
    r.raise_for_status()
    if r.status_code == 200:
        logger.debug(f"request successful: {r.text}")
        return r.json()
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None


def get_negotiations_by_collection(access_token: str, vacancy_id: str, collection: str):
    url = f"https://api.hh.ru/negotiations/{collection}?vacancy_id={vacancy_id}"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT},
        timeout=15
    )
    r.raise_for_status()
    if r.status_code == 200:
        logger.debug(f"request successful: {r.text}")
        return r.json()
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None


def get_negotiations_by_state(access_token: str, vacancy_id: str, state_id: str):
    """Get negotiations by state to see what collections are available"""
    url = f"https://api.hh.ru/negotiations/?vacancy_id={vacancy_id}&state={state_id}"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT},
        timeout=15
    )
    r.raise_for_status()
    if r.status_code == 200:
        logger.debug(f"request successful: {r.text}")
        return r.json()
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None


def get_negotiations_messages(access_token: str, negotiation_id: str):
    url = f"https://api.hh.ru/negotiations/{negotiation_id}/messages"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT},
        timeout=15
    )
    r.raise_for_status()
    if r.status_code == 200:
        logger.debug(f"request successful: {r.text}")
        return r.json()
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None


def change_collection_status_of_negotiation(
    access_token: str, 
    negotiation_id: str,
    collection_name: str,
    new_state: str):
    url = f"https://api.hh.ru/negotiations/{collection_name}/{negotiation_id}"
    r = requests.put(
        url,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT},
        timeout=15,
        json={"collection": collection_name, "status": new_state}
    )
    r.raise_for_status()
    if r.status_code in (200, 201, 204):
        logger.debug(f"request successful: {r.text}")
        # Some HH endpoints return 204 No Content or empty body on success
        if r.text and r.headers.get("Content-Type", "").startswith("application/json"):
            try:
                return r.json()
            except Exception:
                pass
        return {"status": "success", "code": r.status_code}
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None


def send_negotiation_message(access_token: str, negotiation_id: str, user_message: str):
    user_message_formatted = user_message.strip()
    url = f"https://api.hh.ru/negotiations/{negotiation_id}/messages"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=15,
        params={"message": f"{user_message_formatted}"}
    )
    logger.error(f"request failed: {r.status_code} {r.text}")
    r.raise_for_status()
    """
    if r.status_code == 200:
        logger.debug(f"request successful: {r.text}")
        return r.json()
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None
    """


def get_negotiations_history(access_token: str, resume_id: str):
    url = f"https://api.hh.ru/resumes/{resume_id}/negotiations_history"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT},
        timeout=15,
    )
    r.raise_for_status()
    if r.status_code == 200:
        logger.debug(f"request successful: {r.text}")
        return r.json()
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None


# ------------------------------ RESUME related calls ------------------------------

def get_resume_info(access_token: str, resume_id: str):
    url = f"https://api.hh.ru/resumes/{resume_id}"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT},
        timeout=15
    )
    r.raise_for_status()
    if r.status_code == 200:
        logger.debug(f"request successful: {r.text}")
        return r.json()
    else:
        logger.error(f"request failed: {r.status_code} {r.text}")
        return None


# ------------------------------ SUPPORTING functions ------------------------------

def get_dictionary_from_hh(access_token: str):
    """Get dictionary from HH.ru API and write it to a JSON file"""
    r = requests.get(
        "https://api.hh.ru/dictionaries",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
        },
        timeout=10,
    )
    r.raise_for_status()
    if r.status_code == 200:
        hh_dictionaries_file_path = Path("docs") / "hh_dictionaries.json"
        create_json_file_with_dictionary_content(file_path=hh_dictionaries_file_path, content_to_write=r.json())
        logger.debug(f"dictionaries written to {Path('docs') / 'hh_dictionaries.json'}")
    else:
        logger.error(f"Error: {r.status_code} {r.text}")


if __name__ == "__main__":
    #exchange_code_for_token(CODE_2)
    #get_user_info(ACCESS_TOKEN_2)
    #get_employer_vacancies(ACCESS_TOKEN_2)
    #print(get_vacancy_info(access_token="", vacancy_id=""))
    #get_negotiations_list(ACCESS_TOKEN_2)
    #get_negotiations(ACCESS_TOKEN_2, VACANCY_ID_2)
    #get_negotiations_by_collection(ACCESS_TOKEN_2, VACANCY_ID_2, "consider")
    #hh_dict = get_hh_dictionary(ACCESS_TOKEN_2, "education")
    pass