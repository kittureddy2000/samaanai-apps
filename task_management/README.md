# Task Management Application

## Overview

This Django application provides a comprehensive task management solution, allowing users to organize their tasks, integrate with external services like Google Tasks and Microsoft To-Do, and manage tasks efficiently through a web interface.

## Features

*   **Task Creation & Management:** Create, edit, and delete tasks with details like description, due date, reminder time, and recurrence.
*   **Task Lists:** Organize tasks into customizable lists. Predefined lists include "All Tasks," "Important," "Past Due," and "Samaan Tasks."
*   **Task Completion:** Mark tasks as complete or incomplete.
*   **Recurring Tasks:** Set tasks to repeat daily, weekly, monthly, or yearly. Completing a recurring task automatically advances its due date to the next occurrence and logs the completion in history.
*   **Favorites:** Mark important tasks as favorites for quick access.
*   **Search & Filtering:** Search tasks by name or description, and filter by status (All, Completed, Past Due).
*   **Sorting:** Sort tasks by due date or importance.
*   **Image Attachments:** Attach images to tasks (stored in Google Cloud Storage).
*   **Google Tasks Integration:** Bi-directional synchronization with Google Tasks.
*   **Microsoft To-Do Integration:** Bi-directional synchronization with Microsoft To-Do.
*   **Asynchronous Operations:** Uses Google Cloud Tasks for reliable background synchronization.

## Technology Stack

*   **Backend:** Django (Python)
*   **Frontend:** HTML, CSS, JavaScript (jQuery, Bootstrap)
*   **Database:** PostgreSQL (or configurable via Django settings)
*   **Background Tasks:** Google Cloud Tasks
*   **External APIs:** Google Tasks API, Microsoft Graph API
*   **Authentication:** Django's built-in authentication, Google OAuth2, Microsoft OAuth2
*   **Deployment:** Configured for Google Cloud Run (using Docker)

## Setup & Installation

1.  **Prerequisites:**
    *   Python 3.10+
    *   Pip (Python package installer)
    *   Git
    *   Google Cloud SDK (for deployment and Cloud Tasks setup)
    *   Access to a PostgreSQL database (or configure `settings.py` for another DB)

2.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

3.  **Set up Virtual Environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure Environment Variables:**
    Create a `.env` file in the project root (where `manage.py` is located) and add the following variables. **Do not commit this file to version control.**
    ```dotenv
    # Django Settings
    SECRET_KEY='your_django_secret_key' # Generate a strong secret key
    DEBUG=True # Set to False in production
    DATABASE_URL='postgres://user:password@host:port/dbname' # Your PostgreSQL connection string

    # Google OAuth2 Credentials (from Google Cloud Console)
    SOCIAL_AUTH_GOOGLE_OAUTH2_KEY='your_google_client_id'
    SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET='your_google_client_secret'

    # Microsoft OAuth2 Credentials (from Azure Portal)
    SOCIAL_AUTH_MICROSOFT_GRAPH_KEY='your_microsoft_client_id'
    SOCIAL_AUTH_MICROSOFT_GRAPH_SECRET='your_microsoft_client_secret'

    # Google Cloud Project Settings
    PROJECT_ID='your_gcp_project_id'
    CLOUD_TASKS_LOCATION='your_gcp_region' # e.g., us-west1
    GCS_BUCKET_NAME='your_google_cloud_storage_bucket_name' # For image attachments

    # Application Settings
    BASE_URL='http://localhost:8000' # Your application's base URL (change for production)
    ENVIRONMENT='development' # Set to 'production' when deploying

    # Optional: Set if using Google Cloud Storage for static/media files in production
    # GS_BUCKET_NAME='your_static_files_gcs_bucket'
    # STATIC_URL='/static/'
    # MEDIA_URL='/media/'
    ```
    *Replace placeholders with your actual credentials and settings.*

6.  **Database Migrations:**
    ```bash
    python manage.py migrate
    ```

7.  **Set up Google Cloud Tasks Queues:**
    *   Ensure you are authenticated with Google Cloud SDK (`gcloud auth login`, `gcloud config set project YOUR_PROJECT_ID`).
    *   Run the management command to create the necessary queues:
        ```bash
        python manage.py setup_cloud_tasks --project <your_gcp_project_id> --location <your_gcp_region>
        ```
    *   Alternatively, manually create the following queues in your Google Cloud project within the specified location:
        *   `google-task-update-queue`
        *   `ms-task-update-queue`
        *   `task-sync-queue`
    *   *Ensure the service account running your application (especially in Cloud Run) has permissions to enqueue tasks (`roles/cloudtasks.enqueuer`) and potentially create/manage queues if using the command.*

8.  **Create Superuser (Optional):**
    ```bash
    python manage.py createsuperuser
    ```

9.  **Run Development Server:**
    ```bash
    python manage.py runserver
    ```
    Access the application at `http://localhost:8000`.

## Task Synchronization (Google & Microsoft)

The application provides bi-directional synchronization between tasks stored locally (Samaanai) and tasks in the user's connected Google Tasks and Microsoft To-Do accounts.

### Architecture

*   **Asynchronous Processing:** To avoid blocking web requests during potentially long-running API calls, synchronization tasks (pushing updates *from* Samaanai *to* external services) are handled asynchronously using **Google Cloud Tasks**.
*   **Queues:** Three Cloud Tasks queues are used:
    *   `google-task-update-queue`: Handles updates to be pushed to Google Tasks.
    *   `ms-task-update-queue`: Handles updates to be pushed to Microsoft To-Do.
    *   `task-sync-queue`: Handles periodic background sync requests (pulling updates *from* external services *to* Samaanai for all users).
*   **Database Models:**
    *   `Task`: Stores the core task data. Includes `source` (`google` or `microsoft`) and `source_id` fields to link with external tasks. `last_update_date` is crucial for conflict resolution.
    *   `TaskList`: Represents task lists, linked to external list IDs via `list_code`.
    *   `UserToken`: Securely stores OAuth2 access and refresh tokens for connected Google/Microsoft accounts.
    *   `TaskSyncStatus`: Tracks the completion status of background sync operations.

### Authentication

*   Users connect their Google and Microsoft accounts via standard OAuth2 flows.
*   The application requests necessary permissions (e.g., `tasks` scope for Google, `Tasks.ReadWrite` for Microsoft).
*   Access and refresh tokens are stored in the `UserToken` model, associated with the Django user.
*   Tokens are automatically refreshed when expired using the stored refresh token (`auth_utils.py`, `sync_utils.py`).

### Sync FROM External Services TO Samaanai (Pull Sync)

This process imports tasks and updates from Google/Microsoft into the Samaanai database.

1.  **Trigger:**
    *   **Manual:** User clicks the "Sync" button in the UI (`views.sync_google_tasks`, `views.sync_microsoft_tasks`).
    *   **Automatic (Background):** A scheduled job (e.g., Google Cloud Scheduler - *needs separate setup*) can periodically trigger the `/task_management/sync_tasks/` endpoint (`sync_utils.trigger_background_sync`). This enqueues individual sync tasks for each user into the `task-sync-queue`. Cloud Tasks then calls `/task_management/process_sync_task/` (`sync_utils.process_sync_task`) for each user.

2.  **Processing (`sync_utils.sync_user_tasks`):**
    *   Retrieves the valid access token for the user and provider (`UserToken`).
    *   Calls the appropriate fetch function: `fetch_google_tasks_and_save` or `fetch_microsoft_tasks_and_save`.

3.  **API Calls & Logic (`fetch_..._tasks_and_save`):**
    *   **Get Lists:** Fetches all task lists from the external service API (Google Tasks `tasklists.list`, Microsoft Graph `/me/todo/lists`). Corresponding `TaskList` objects are created/updated in Samaanai.
    *   **Get Tasks:** Fetches tasks from each list. Uses `updatedMin` (Google) or `$filter=lastModifiedDateTime ge ...` (Microsoft) based on `UserToken.last_synced_at` to only retrieve tasks modified since the last sync, optimizing performance. Handles API pagination.
    *   **Compare & Update/Create:** For each fetched task:
        *   It checks if a corresponding task exists in Samaanai using `source` and `source_id`.
        *   **If exists:** Compares fields (name, description, due date, completion status). If differences are found, the Samaanai `Task` object is updated.
        *   **If not exists:** A new `Task` object is created in Samaanai.
    *   **Handle Deletions (Google):** During the first sync or if explicitly needed, it compares all fetched Google task IDs against existing Samaanai tasks for that list. Tasks present in Samaanai but *not* returned by the API are assumed deleted in Google and marked as completed in Samaanai. *(Note: Microsoft deletion handling might need review/implementation)*.
    *   **Update Sync Timestamp:** Updates `UserToken.last_synced_at` to the current time upon successful completion.

### Sync FROM Samaanai TO External Services (Push Sync)

This process pushes changes made within the Samaanai application to the connected Google/Microsoft accounts.

1.  **Trigger (`signals.sync_task_update`):**
    *   A Django `post_save` signal is attached to the `Task` model.
    *   This signal function runs *after* any `Task` object is saved.

2.  **Filtering:**
    *   **Recursion Prevention:** Checks for a temporary `_skip_signal` attribute on the task instance. This is set briefly *after* an update *originating from a sync operation* to prevent infinite loops (e.g., sync updates task -> signal runs -> sync updates task...).
    *   **User-Initiated Check:** For tasks with `source` as 'google' or 'microsoft', it checks if the save was triggered by a direct user action (e.g., `update_fields` is present in the save call) rather than an automatic process (like the pull sync). This prevents unnecessary push updates when simply importing tasks.

3.  **Asynchronous Task Creation:**
    *   If the save should trigger a sync, it determines the correct queue (`google-task-update-queue` or `ms-task-update-queue`) and target endpoint (`/process_google_task_update/` or `/process_ms_task_update/`).
    *   It uses the `google-cloud-tasks` client library to create and enqueue a new task.
    *   The task payload contains the `user_id` and the Samaanai `task_id` of the task that needs updating.

4.  **Task Processing (Cloud Tasks Worker Endpoints):**
    *   Google Cloud Tasks automatically calls the appropriate endpoint (`/process_google_task_update/` or `/process_ms_task_update/` defined in `sync_utils.py`).
    *   These views parse the `user_id` and `task_id` from the request body.
    *   They retrieve the corresponding `User` and `Task` objects.
    *   They call the relevant update function: `update_google_task` or `update_ms_task`.

5.  **API Calls & Logic (`update_google_task`, `update_ms_task`):**
    *   Retrieves a valid access token for the user.
    *   **Conflict Resolution:** Fetches the *current* state of the task directly from the external API (Google Tasks `tasks.get`, Microsoft Graph `GET /me/todo/lists/.../tasks/...`). It compares the `last_update_date` of the Samaanai task with the `lastModifiedDateTime` (Microsoft) or `updated` timestamp (Google) of the external task. If the external task is newer, the update from Samaanai is *skipped* to prevent overwriting more recent changes made directly in the external service.
    *   **Prepare Payload:** Constructs the request body/payload for the external API with the updated data from the Samaanai task (title, notes/description, due date, status - 'completed'/'needsAction' for Google, 'completed'/'notStarted' for Microsoft).
    *   **API Call:** Sends the update request to the external API (Google Tasks `tasks.update`, Microsoft Graph `PATCH /me/todo/lists/.../tasks/...`).
    *   **Mark Synced (Prevent Recursion):** After a successful external update, it briefly sets the `_skip_signal` flag on the Samaanai `Task` object *before* saving it (if necessary, though often not needed here as the save already happened). This ensures the signal handler doesn't immediately re-trigger another push sync for the same change.

## Recurring Tasks

*   When a recurring task is marked complete via the `complete_task` view:
    1.  A `TaskHistory` record is created to log the completion of that specific instance, capturing the task details and the completion timestamp (implicitly the creation time of the history record).
    2.  The `due_date` of the original `Task` object is advanced based on its `recurrence` setting (Daily, Weekly, Monthly, Yearly) using `timedelta` and `relativedelta`.
    3.  The `task_completed` status of the original `Task` object is reset to `False`.
    4.  The updated task (with the new due date) is saved. This triggers the push sync mechanism described above if the task is linked to Google/Microsoft.

## Key Files

*   `models.py`: Defines `Task`, `TaskList`, `TaskHistory`, `UserToken`, `TaskSyncStatus`.
*   `views.py`: Contains main view logic, including UI rendering (`get_lists`), task operations (`complete_task`, `edit_task`), and manual sync triggers (`sync_google_tasks`, `sync_microsoft_tasks`).
*   `sync_utils.py`: Houses the core synchronization logic:
    *   `sync_user_tasks`: Orchestrates pull sync.
    *   `fetch_google_tasks_and_save`, `fetch_microsoft_tasks_and_save`: Pull data from APIs.
    *   `update_google_task`, `update_ms_task`: Push data to APIs.
    *   `process_google_task_update`, `process_ms_task_update`: Cloud Tasks worker endpoints.
    *   `trigger_background_sync`, `process_sync_task`: Handles scheduled/background sync.
*   `signals.py`: Contains the `post_save` signal handler (`sync_task_update`) that triggers push syncs.
*   `auth_utils.py`: Handles OAuth2 authentication flows.
*   `urls.py`: Defines URL patterns mapping requests to views and sync endpoints.
*   `templates/`: HTML templates for the user interface.
*   `static/`: CSS and JavaScript files.

## Troubleshooting Sync Issues

*   **Check Logs:** Application logs (especially `sync_utils.py` and `signals.py`) provide detailed information about sync operations and errors. Configure Django logging appropriately.
*   **Google Cloud Tasks Console:** Monitor the status of the queues (`google-task-update-queue`, `ms-task-update-queue`, `task-sync-queue`). Look for failed task executions and their logs.
*   **Token Expiry:** Ensure the OAuth tokens stored in `UserToken` are valid and refreshable. Errors fetching data often point to token issues. Reconnecting the account might be necessary.
*   **API Rate Limits:** Google and Microsoft APIs have rate limits. Excessive syncing might lead to temporary blocks (HTTP 429 errors). Check external service documentation.
*   **Permissions:** Verify the application has the necessary API permissions granted during the OAuth flow. Ensure the service account (if deployed) has Cloud Tasks permissions.
*   **Unique Constraints:** Errors mentioning unique constraints (like on `TaskHistory.source_id`) might indicate issues with generating unique IDs during rapid operations. 

# Run all tests
pytest

# Run specific test file
pytest tests/test_models.py

# Run with coverage
pytest --cov=task_management

# Run only browser tests
pytest -m playwright

# Skip slow tests
pytest -k "not slow"

# Run model tests
docker-compose exec web python -m pytest task_management/tests/test_models.py -v

# Run form tests
docker-compose exec web python -m pytest task_management/tests/test_forms.py -v

# Run view tests
docker-compose exec web python -m pytest task_management/tests/test_views.py -v

# Run Google sync tests
docker-compose exec web python -m pytest task_management/tests/test_sync_google.py -v

# Run Microsoft sync tests
docker-compose exec web python -m pytest task_management/tests/test_sync_ms.py -v

# Run specific test class
docker-compose exec web python -m pytest task_management/tests/test_ui.py

docker-compose exec web python -m pytest task_management/tests/test_sync_edge_cases.py