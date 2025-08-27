import os
import logging

logger = logging.getLogger(__name__)

# In-memory user "database" loaded from environment variables.
# The expected format for the environment variable is:
# APP_USERS="user1:pass1,user2:pass2"
USERS = {}

users_env = os.getenv("APP_USERS")
if users_env:
    pairs = users_env.split(',')
    for pair in pairs:
        stripped_pair = pair.strip()
        if not stripped_pair:
            continue
        if ':' not in stripped_pair:
            logger.warning(f"Skipping malformed user entry: '{stripped_pair}'. Expected 'username:password'.")
            continue
        username, password = stripped_pair.split(':', 1)
        if not username or not password:
            logger.warning(f"Skipping malformed user entry with empty username or password: '{stripped_pair}'.")
            continue
        USERS[username] = password
    logger.info(f"Loaded {len(USERS)} user(s) from APP_USERS environment variable.")

if not USERS:
    logger.warning("No users configured via APP_USERS. Using default fallback user 'admin:changeme'.")
    USERS = {"admin": "changeme"}