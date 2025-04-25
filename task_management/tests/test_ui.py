import os
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

import pytest
from playwright.sync_api import expect, sync_playwright

# Mark these tests to be run in headless browser
pytestmark = pytest.mark.playwright

@pytest.fixture(scope="module")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "ignore_https_errors": True,
        "viewport": {
            "width": 1280,
            "height": 720,
        }
    }

# Configure browser launch options for Docker environment
@pytest.fixture(scope="session")
def browser_launch_args():
    return {
        "chromium": {
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                "--window-size=1280,720"
            ]
        }
    }

def test_task_creation_ui(page, live_server, user):
    """Test task creation through the browser UI."""
    # Login
    page.goto(f"{live_server.url}/accounts/login/")
    page.fill('input[name="username"]', 'testuser')
    page.fill('input[name="password"]', 'securepassword123')
    page.click('button[type="submit"]')
    
    # Navigate to task dashboard
    page.goto(f"{live_server.url}/task_management/")
    
    # Open add task modal
    page.click('button#add-task-btn')
    page.wait_for_selector('#taskModal.show')
    
    # Fill the form
    page.fill('input#id_task_name', 'UI Test Task')
    page.fill('textarea#id_task_description', 'Created via UI test')
    page.fill('input#dueDateInput', '2023-12-31')
    
    # Select recurrence
    page.click('#recurrenceDropdown')
    page.click('text=Weekly')
    
    # Save the task
    page.click('button#saveTask')
    page.wait_for_selector('text=Task added successfully')
    
    # Verify task appears in list
    expect(page.locator('text=UI Test Task')).to_be_visible()

def test_task_completion_ui(page, live_server, user, task):
    """Test marking a task as complete through the UI."""
    # Login
    page.goto(f"{live_server.url}/accounts/login/")
    page.fill('input[name="username"]', 'testuser')
    page.fill('input[name="password"]', 'securepassword123')
    page.click('button[type="submit"]')
    
    # Navigate to task dashboard
    page.goto(f"{live_server.url}/task_management/")
    
    # Find and click the complete checkbox
    task_selector = f'#task-{task.id}'
    page.wait_for_selector(task_selector)
    page.click(f'{task_selector} .complete-task')
    
    # Wait for completion animation
    page.wait_for_selector(f'{task_selector} .task-title.strikethrough')
    
    # Verify task is marked as complete
    expect(page.locator(f'{task_selector} .fas.fa-check-circle')).to_be_visible()

def test_find_login_page(page, live_server):
    """Debug test to find the login page."""
    # Try common login URLs
    urls = [
        '/login/',
        '/accounts/login/',
        '/auth/login/',
        '/',  # Maybe login is on homepage?
        '/user/login/'
    ]
    
    for url in urls:
        full_url = f"{live_server.url}{url}"
        print(f"Trying {full_url}")
        page.goto(full_url)
        page.screenshot(path=f"/tmp/login_attempt_{url.replace('/', '_')}.png")
        
        # Check for login indicators
        has_username = page.locator('input[name="username"]').count() > 0
        has_password = page.locator('input[name="password"]').count() > 0
        has_google = page.locator('text=Sign in with Google').count() > 0
        
        print(f"URL: {url}, Username field: {has_username}, Password field: {has_password}, Google login: {has_google}")
        
    # Just pass to see the output
    assert True