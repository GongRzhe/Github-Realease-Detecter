#!/usr/bin/env python3
import os
import time
import json
import asyncio
import requests
import re
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from pydantic import BaseModel, Field

# Import AutoGen components
from autogen_core import FunctionCall, MessageContext, RoutedAgent, message_handler
from autogen_core.model_context import BufferedChatCompletionContext
from autogen_core.models import SystemMessage, UserMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams


# Custom JSON Encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# Define Pydantic models for our data structures
class Release(BaseModel):
    id: int
    tag_name: str
    name: str
    published_at: str
    html_url: str
    body: Optional[str] = None


class RepoConfig(BaseModel):
    owner: str
    repo: str
    latest_check: Optional[str] = None  # Store as string instead of datetime
    releases: List[Release] = Field(default_factory=list)


class ReleaseHistory(BaseModel):
    repositories: List[RepoConfig] = Field(default_factory=list)


class EmailPayload(BaseModel):
    to: List[str]
    subject: str
    body: str
    htmlBody: Optional[str] = None
    mimeType: str = "multipart/alternative"
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None


# GitHub Release Agent to monitor releases
class GitHubReleaseAgent(RoutedAgent):
    def __init__(self, history_file: str = "release_history.json", token: Optional[str] = None):
        super().__init__("A GitHub Release monitoring agent")
        self.headers = {"User-Agent": "GitHub-Release-Monitor"}
        if token:
            self.headers["Authorization"] = f"token {token}"
        self.history_file = history_file
        self.history = self._load_history()
    
    def _load_history(self) -> ReleaseHistory:
        """Load release history from file or create new if not exists."""
        # Resolve absolute path for history file
        history_file_path = os.path.abspath(self.history_file)
        print(f"Loading release history from: {history_file_path}")
        
        if os.path.exists(history_file_path):
            try:
                with open(history_file_path, 'r') as f:
                    data = json.load(f)
                history = ReleaseHistory(**data)
                print(f"Loaded history with {len(history.repositories)} repositories")
                for repo in history.repositories:
                    print(f"  - {repo.owner}/{repo.repo}: {len(repo.releases)} releases")
                return history
            except Exception as e:
                print(f"Error loading history: {e}")
                return ReleaseHistory()
        else:
            print(f"History file not found. Starting with empty history.")
            return ReleaseHistory()
    
    def _save_history(self):
        """Save release history to file."""
        # Resolve absolute path for history file
        history_file_path = os.path.abspath(self.history_file)
        print(f"Saving release history to: {history_file_path}")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(history_file_path), exist_ok=True)
        
        with open(history_file_path, 'w') as f:
            # Use the custom encoder to handle datetime objects
            json.dump(self.history.model_dump(), f, indent=2, cls=DateTimeEncoder)
        
        print(f"Saved history with {len(self.history.repositories)} repositories")
    
    def _get_repo_index(self, owner: str, repo: str) -> int:
        """Get index of repository in history or -1 if not found."""
        for i, repo_config in enumerate(self.history.repositories):
            if repo_config.owner == owner and repo_config.repo == repo:
                return i
        return -1
    
    def _ensure_repo_exists(self, owner: str, repo: str) -> int:
        """Ensure repository exists in history and return its index."""
        index = self._get_repo_index(owner, repo)
        if index == -1:
            # Repository doesn't exist, add it
            self.history.repositories.append(RepoConfig(owner=owner, repo=repo))
            index = len(self.history.repositories) - 1
        return index
    
    async def get_releases(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """Fetch all releases from GitHub API for a specific repository."""
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        try:
            response = requests.get(api_url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching releases for {owner}/{repo}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Status code: {e.response.status_code}")
                print(f"Response: {e.response.text}")
            return []
    
    async def check_for_new_releases(self, owner: str, repo: str) -> List[Tuple[str, str, Release]]:
        """
        Check for new releases in a specific repository.
        
        Returns:
            List of tuples containing (owner, repo, release) for new releases.
        """
        releases_data = await self.get_releases(owner, repo)
        if not releases_data:
            return []
        
        # Ensure repository exists in history
        repo_index = self._ensure_repo_exists(owner, repo)
        
        # Update latest check time - store as string
        self.history.repositories[repo_index].latest_check = datetime.now().isoformat()
        
        # Extract IDs of known releases
        known_release_ids = [release.id for release in self.history.repositories[repo_index].releases]
        print(f"Repository {owner}/{repo} has {len(known_release_ids)} known releases")
        
        new_releases = []
        for release_data in releases_data:
            if release_data['id'] not in known_release_ids:
                print(f"Found new release: {release_data['name'] or release_data['tag_name']} (ID: {release_data['id']})")
                release = Release(
                    id=release_data['id'],
                    tag_name=release_data['tag_name'],
                    name=release_data['name'] or release_data['tag_name'],
                    published_at=release_data['published_at'],
                    html_url=release_data['html_url'],
                    body=release_data.get('body', '')
                )
                new_releases.append((owner, repo, release))
                self.history.repositories[repo_index].releases.append(release)
            else:
                print(f"Skipping known release: {release_data['name'] or release_data['tag_name']} (ID: {release_data['id']})")
        
        if new_releases:
            self._save_history()
            
        return new_releases
    
    async def check_all_repositories(self, repositories: List[Tuple[str, str]]) -> List[Tuple[str, str, Release]]:
        """
        Check for new releases across all specified repositories.
        
        Args:
            repositories: List of (owner, repo) tuples to check
            
        Returns:
            List of (owner, repo, release) tuples for all new releases
        """
        all_new_releases = []
        
        for owner, repo in repositories:
            new_releases = await self.check_for_new_releases(owner, repo)
            all_new_releases.extend(new_releases)
        
        return all_new_releases


# Content Analysis Agent using LLM to extract key information
class ContentAnalysisAgent(RoutedAgent):
    def __init__(self, model_client: OpenAIChatCompletionClient):
        super().__init__("A release content analysis agent")
        self._model_client = model_client
        self._system_message = SystemMessage(
            content=(
                "You are an expert at analyzing GitHub release notes and extracting the most important "
                "information. Your task is to analyze release notes and identify:\n"
                "1. Key features or improvements\n"
                "2. Bug fixes\n"
                "3. Breaking changes\n"
                "4. Security updates\n"
                "5. Overall summary\n\n"
                "Format your response as a structured summary with HTML formatting for better readability "
                "in email notifications. Use proper HTML tags like <h2>, <h3>, <ul>, <li>, <p>, etc. "
                "DO NOT use Markdown or code block syntax like ```html or ```. "
                "Provide ONLY valid HTML that can be directly embedded in an email."
            )
        )
    
    async def analyze_release(self, owner: str, repo: str, release: Release) -> str:
        """Analyze release notes and extract key information."""
        prompt = (
            f"Repository: {owner}/{repo}\n"
            f"Release: {release.name} ({release.tag_name})\n"
            f"Published at: {release.published_at}\n\n"
            f"Release Notes:\n{release.body or 'No release notes provided.'}\n\n"
            "Please extract the key information from these release notes and format it with HTML for an email. "
            "DO NOT use Markdown syntax or code block delimiters like ```html or ```."
        )
        
        # Create without temperature parameter
        llm_result = await self._model_client.create(
            messages=[self._system_message, UserMessage(content=prompt, source="user")],
        )
        
        response = llm_result.content
        assert isinstance(response, str)
        
        # Clean up any markdown code block delimiters that might have been included
        response = re.sub(r'```html', '', response)
        response = re.sub(r'```', '', response)
        
        return response


# Email Notification Agent using Gmail MCP Server
class EmailNotificationAgent(RoutedAgent):
    def __init__(self, workbench: McpWorkbench):
        super().__init__("An email notification agent")
        self._workbench = workbench
    
    async def send_notification(self, recipient: str, owner: str, repo: str, release: Release, content_analysis: str) -> bool:
        """Send email notification with release information."""
        # Format subject
        subject = f"New GitHub Release: {owner}/{repo} - {release.name}"
        
        # Clean up any markdown that might have been included
        clean_content = re.sub(r'```html', '', content_analysis)
        clean_content = re.sub(r'```', '', clean_content)
        
        # Basic text content for text/plain part
        text_body = f"""
New GitHub Release: {release.name} ({release.tag_name})
Repository: {owner}/{repo}
Published at: {release.published_at}
URL: {release.html_url}

Release Analysis:
{clean_content.replace('<h2>', '').replace('</h2>', '').replace('<h3>', '').replace('</h3>', '').replace('<p>', '').replace('</p>', '').replace('<br>', '\n').replace('<ul>', '').replace('</ul>', '').replace('<li>', '- ').replace('</li>', '')}
"""
        
        # HTML content for text/html part
        html_body = f"""
<html>
<body>
  <h1>New GitHub Release: {release.name}</h1>
  <p><strong>Repository:</strong> <a href="https://github.com/{owner}/{repo}">{owner}/{repo}</a></p>
  <p><strong>Tag:</strong> {release.tag_name}</p>
  <p><strong>Published at:</strong> {release.published_at}</p>
  <p><strong>URL:</strong> <a href="{release.html_url}">{release.html_url}</a></p>
  
  <hr>
  <h2>Release Analysis</h2>
  {clean_content}
</body>
</html>
"""
        
        # Create email payload
        email_payload = EmailPayload(
            to=[recipient],
            subject=subject,
            body=text_body,
            htmlBody=html_body,
            mimeType="multipart/alternative"
        )
        
        try:
            # Call the Gmail MCP server to send the email
            result = await self._workbench.call_tool(
                "send_email", 
                # Use model_dump() instead of dict()
                arguments=email_payload.model_dump(exclude_none=True)
            )
            
            if result.is_error:
                print(f"Error sending email: {result.to_text()}")
                return False
            
            print(f"Email notification sent to {recipient} successfully")
            return True
        except Exception as e:
            print(f"Failed to send email notification: {e}")
            return False


# Main Release Monitor Orchestrator
class ReleaseMonitorOrchestrator:
    def __init__(
        self,
        repositories: List[Tuple[str, str]],
        recipient_email: str,
        github_token: Optional[str] = None,
        check_interval: int = 3600,
        history_file: str = "release_history.json"
    ):
        """
        Initialize the orchestrator.
        
        Args:
            repositories: List of (owner, repo) tuples to monitor
            recipient_email: Email address to send notifications to
            github_token: GitHub personal access token for API authentication
            check_interval: Time interval between checks in seconds
            history_file: Path to the file for storing release history
        """
        self.repositories = repositories
        self.recipient_email = recipient_email
        self.check_interval = check_interval
        
        # Setup OpenAI client with temperature parameter here
        self.model_client = OpenAIChatCompletionClient(
            model="gpt-4.1-mini", 
            temperature=0.3  # Set temperature here instead of in the create() call
        )
        
        # Create agents
        self.github_agent = GitHubReleaseAgent(history_file, github_token)
        self.analysis_agent = ContentAnalysisAgent(self.model_client)
        
        # Gmail MCP server configuration
        self.gmail_mcp_server = StdioServerParams(
            command="npx",
            args=["@gongrzhe/server-gmail-autoauth-mcp"]
        )
    
    async def initialize(self):
        """
        Initialize by loading all repositories and their current releases.
        This creates the initial history without sending notifications.
        """
        print(f"\n[{datetime.now()}] Initializing release monitor...")
        print(f"Loading current releases for {len(self.repositories)} repositories")
        
        # Check all repositories to build up the initial history
        init_releases = await self.github_agent.check_all_repositories(self.repositories)
        
        if init_releases:
            print(f"Found {len(init_releases)} existing release(s) during initialization")
            print("These releases have been added to history and will NOT trigger notifications")
        else:
            print("No existing releases found during initialization")
        
        # Save the history to ensure all current releases are recorded
        self.github_agent._save_history()
        
        print("Initialization complete - only new releases will trigger notifications")
    
    async def start_monitoring(self):
        """Start monitoring for new releases across all repositories."""
        repo_list = ", ".join([f"{owner}/{repo}" for owner, repo in self.repositories])
        print(f"Starting to monitor {len(self.repositories)} repositories: {repo_list}")
        print(f"Checking every {self.check_interval} seconds")
        print(f"Email notifications will be sent to: {self.recipient_email}")
        
        # Initialize first to load existing releases
        await self.initialize()
        
        # Start the workbench in a context manager
        async with McpWorkbench(self.gmail_mcp_server) as workbench:
            # Create email agent with workbench
            email_agent = EmailNotificationAgent(workbench)
            
            try:
                while True:
                    print(f"\n[{datetime.now()}] Checking for new releases...")
                    
                    # Check for new releases across all repositories
                    new_releases = await self.github_agent.check_all_repositories(self.repositories)
                    
                    if new_releases:
                        print(f"Found {len(new_releases)} new release(s)!")
                        
                        for owner, repo, release in new_releases:
                            print(f"New release in {owner}/{repo}: {release.name} ({release.tag_name})")
                            print(f"Published at: {release.published_at}")
                            print(f"URL: {release.html_url}")
                            print("-" * 40)
                            
                            # Analyze release content
                            content_analysis = await self.analysis_agent.analyze_release(owner, repo, release)
                            
                            # Send email notification
                            await email_agent.send_notification(
                                self.recipient_email, owner, repo, release, content_analysis
                            )
                    else:
                        print(f"No new releases found in any repository")
                    
                    print(f"Next check in {self.check_interval} seconds")
                    await asyncio.sleep(self.check_interval)
            
            except KeyboardInterrupt:
                print("\nMonitoring stopped by user")
            finally:
                # Close the model client
                await self.model_client.close()


# Command-line interface
async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Monitor GitHub repositories for new releases')
    parser.add_argument('--repos', required=True, nargs='+', help='Repositories to monitor in the format owner/repo (e.g., "microsoft/autogen")')
    parser.add_argument('--email', required=True, help='Email address to receive notifications')
    parser.add_argument('--token', help='GitHub personal access token')
    parser.add_argument('--interval', type=int, default=3600, help='Check interval in seconds (default: 3600)')
    parser.add_argument('--history-file', default='release_history.json', help='File to store release history')
    
    args = parser.parse_args()
    
    # Parse repositories from command line
    repositories = []
    for repo_str in args.repos:
        parts = repo_str.split('/')
        if len(parts) != 2:
            print(f"Error: Repository '{repo_str}' is not in the format 'owner/repo'")
            continue
        repositories.append((parts[0], parts[1]))
    
    if not repositories:
        print("Error: No valid repositories specified")
        return
    
    # Set up the orchestrator
    orchestrator = ReleaseMonitorOrchestrator(
        repositories=repositories,
        recipient_email=args.email,
        github_token=args.token,
        check_interval=args.interval,
        history_file=args.history_file
    )
    
    # Start monitoring
    await orchestrator.start_monitoring()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
