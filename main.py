"""
Orchestrator for running two bots: manager_bot and applicant_bot.
Launches them as separate processes and monitors their status.
"""

import os
import sys
import subprocess
import signal
import time
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ------------- CONFIGURATION OF LOGGING -------------

# Create logs directory
data_dir = Path(os.getenv("USERS_DATA_DIR", "/users_data"))
logs_dir = data_dir / "logs" / "orchestrator_logs"
# Create logs directory and all parent directories if they don't exist
logs_dir.mkdir(parents=True, exist_ok=True)
# Create log file with timestamp
log_filename = logs_dir / f"orchestrator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Create rotating file handler
file_handler = logging.handlers.RotatingFileHandler(
    log_filename,
    maxBytes=20 * 1024 * 1024,  # 20MB
    backupCount=20,
    encoding='utf-8'
)

# Configure logging with both file and console handlers
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        file_handler,
        logging.StreamHandler(sys.stdout)  # Also write to console
    ]
)

logger = logging.getLogger("hrvibe_orchestrator")
logger.info(f"Orchestrator logging configured. Logs written to: {log_filename}")


def start_bot_process(name: str, cwd: str) -> subprocess.Popen:
    """
    Launches a bot as a separate process: python main.py in the specified directory.
    Args:
        name: string "manager" or "applicant" (for logging)
        cwd: path to project directory (manager_bot or applicant_bot)
    Returns:
        subprocess.Popen object of the launched process
    Raises:
        subprocess.SubprocessError: if the process failed to start
        FileNotFoundError: if main.py is not found
    """
    logger.info("Starting %s bot in %s", name, cwd)
    
    # Check that the directory exists
    if not os.path.isdir(cwd):
        raise FileNotFoundError(f"Directory {cwd} does not exist")
    
    # Check that main.py exists
    main_py_path = os.path.join(cwd, "main.py")
    if not os.path.isfile(main_py_path):
        raise FileNotFoundError(f"main.py not found in {cwd}")
    
    cmd = [sys.executable, "main.py"]
    
    # Inherit ENV, including TELEGRAM_* tokens, USERS_DATA_DIR, etc.
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=sys.stdout,   # so bot logs go to Render's common logs
        stderr=sys.stderr,
    )
    
    logger.info("%s bot started with PID %s", name, proc.pid)
    return proc


def shutdown(procs: list, reason: str):
    """
    Gracefully terminates all child processes.
    
    Args:
        procs: list of subprocess.Popen objects
        reason: shutdown reason (for logging)
    """
    logger.info("Shutting down child processes (reason: %s)...", reason)
    
    # First, try to gracefully terminate all alive processes
    for p in procs:
        if p.poll() is None:
            try:
                logger.debug("Terminating process PID %s", p.pid)
                p.terminate()
            except Exception as e:
                logger.warning("Error terminating process PID %s: %s", p.pid, e)
        else:
            logger.debug("Process PID %s already exited (code=%s)", p.pid, p.poll())
    
    # Wait for processes to terminate (maximum 30 seconds)
    deadline = time.time() + 30
    for p in procs:
        if p.poll() is None:
            while p.poll() is None and time.time() < deadline:
                time.sleep(0.5)
            
            if p.poll() is None:
                logger.warning("Process PID %s did not exit in time, killing...", p.pid)
                try:
                    p.kill()
                except Exception as e:
                    logger.warning("Error killing process PID %s: %s", p.pid, e)
            else:
                logger.info("Process PID %s exited with code %s", p.pid, p.poll())
        else:
            logger.debug("Process PID %s already exited (code=%s)", p.pid, p.poll())
    
    logger.info("Shutdown completed")


def main():
    """Main orchestrator function."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    manager_cwd = os.path.join(project_root, "manager_bot")
    applicant_cwd = os.path.join(project_root, "applicant_bot")
    
    logger.info("Orchestrator starting...")
    logger.info("Project root: %s", project_root)
    
    # Check and create directory for shared data
    users_data_dir = Path(os.getenv("USERS_DATA_DIR", "/users_data"))
    try:
        os.makedirs(users_data_dir, exist_ok=True)
        logger.info("USERS_DATA_DIR = %s (created/verified)", users_data_dir)
    except Exception as e:
        logger.error("Failed to create USERS_DATA_DIR %s: %s", users_data_dir, e)
        sys.exit(1)
    
    # Launch processes
    manager_proc = None
    applicant_proc = None
    procs = []
    
    try:
        # Start manager bot
        try:
            manager_proc = start_bot_process("manager", manager_cwd)
            procs.append(manager_proc)
        except Exception as e:
            logger.error("Failed to start manager bot: %s", e, exc_info=True)
            raise
        
        # Small delay before starting the second bot
        time.sleep(1)
        
        # Start applicant bot
        try:
            applicant_proc = start_bot_process("applicant", applicant_cwd)
            procs.append(applicant_proc)
        except Exception as e:
            logger.error("Failed to start applicant bot: %s", e, exc_info=True)
            # If applicant bot failed to start, terminate manager bot
            if manager_proc and manager_proc.poll() is None:
                logger.info("Terminating manager bot due to applicant bot startup failure")
                shutdown([manager_proc], "applicant-startup-failure")
            raise
        
        logger.info("Both bots started successfully")
        
        # Configure signal handlers
        shutdown_requested = False
        
        def handle_sigterm(signum, frame):
            nonlocal shutdown_requested
            if not shutdown_requested:
                shutdown_requested = True
                shutdown(procs, "SIGTERM")
                sys.exit(0)
        
        def handle_sigint(signum, frame):
            nonlocal shutdown_requested
            if not shutdown_requested:
                shutdown_requested = True
                shutdown(procs, "SIGINT")
                sys.exit(0)
        
        signal.signal(signal.SIGTERM, handle_sigterm)
        signal.signal(signal.SIGINT, handle_sigint)
        
        # Monitor processes
        logger.info("Monitoring bot processes...")
        while True:
            manager_code = manager_proc.poll() if manager_proc else None
            applicant_code = applicant_proc.poll() if applicant_proc else None
            
            # If at least one process has terminated
            if manager_code is not None or applicant_code is not None:
                logger.error(
                    "One of the bots exited: manager=%s, applicant=%s",
                    manager_code,
                    applicant_code
                )
                break
            
            time.sleep(2)
    
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt")
        shutdown(procs, "KeyboardInterrupt")
        sys.exit(0)
    
    except Exception as e:
        logger.error("Orchestrator error: %s", e, exc_info=True)
        shutdown(procs, "exception")
        sys.exit(1)
    
    finally:
        # Final termination of all processes
        if procs:
            shutdown(procs, "main-exit")
    
    logger.info("Orchestrator exiting")
    sys.exit(1)  # Non-zero exit code if one of the bots crashed


if __name__ == "__main__":
    main()
