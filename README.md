# GitHub Release Detector

A tool that automatically monitors GitHub repositories for new releases and sends email notifications when they're detected. Stay up-to-date with your favorite open source projects without constantly checking for updates.

![GitHub Release Detector](https://img.shields.io/badge/status-active-brightgreen)
![MCP](https://img.shields.io/badge/MCP-enabled-blue)
![AutoGen](https://img.shields.io/badge/AutoGen-compatible-orange)
![GitHub](https://img.shields.io/badge/GitHub-API-181717?logo=github)
![Agent](https://img.shields.io/badge/Agent-powered-yellow)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-workflow-2088FF?logo=github-actions)

## Overview

GitHub Release Detector is an agent-based monitoring system that leverages the Model Context Protocol (MCP) architecture to create an autonomous pipeline for tracking and notifying users of open-source software releases. The system implements a multi-layered service architecture connecting GitHub's REST API with Gmail's SMTP services through OAuth2 authentication.

![image](https://github.com/user-attachments/assets/9724028f-bb01-4e0d-b2a4-6003ac2f5c39)


## Features

- 🔍 Monitor multiple GitHub repositories for new releases
- 📧 Receive email notifications when new releases are detected
- 🤖 Includes detailed release notes and changelog information
- ⏱️ Configurable checking intervals
- 🔄 Easy setup with GitHub Actions for continuous monitoring
- 🔐 Secure Gmail authentication

## Prerequisites

- Python 3.12+
- Node.js 20+
- Gmail account
- Google Cloud Platform OAuth credentials

## Installation

### Local Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/GongRzhe/Github-Realease-Detecter.git
   cd Github-Realease-Detecter
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install the Gmail MCP tool:
   ```bash
   npm install -g @gongrzhe/server-gmail-autoauth-mcp
   ```

4. Set up OAuth credentials:
   - Create a project in [Google Cloud Console](https://console.cloud.google.com/)
   - Enable the Gmail API
   - Create OAuth credentials (Desktop app)
   - Download the credentials as `gcp-oauth.keys.json`

### GitHub Actions Setup

1. Fork this repository
2. Add the following secrets to your repository:
   - `OPENAI_API_KEY`: Your OpenAI API key (if you're using AI features)
   - `REPOS_TO_MONITOR`: Comma-separated list of repos (e.g., owner/repo1 owner/repo2)
   - `RECIPIENT_EMAIL`: Email address to receive notifications
   - `GCP_OAUTH_B64`: Base64-encoded OAuth credentials (see below)
   - `GMAIL_AUTH_B64`: Base64-encoded Gmail credentials (see below)

#### Encoding Secrets for GitHub Actions

In PowerShell:
```powershell
# For OAuth credentials
$fileContent = Get-Content -Path "gcp-oauth.keys.json" -Raw
$encodedContent = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($fileContent))
$encodedContent | Out-File -FilePath "gcp-oauth.keys.json.b64"

# For Gmail credentials (if you have them already)
$fileContent = Get-Content -Path "credentials.json" -Raw
$encodedContent = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($fileContent))
$encodedContent | Out-File -FilePath "credentials.json.b64"
```

## Configuration

Create a configuration file or use environment variables:

```bash
# Example .env file
OPENAI_API_KEY=sk-XXX
```

## Usage

### Running Locally

```bash
python github_release_monitor.py --repos owner/repo1 owner/repo2 --email recipient@example.com --interval 60
```

### Using GitHub Actions

The included workflow will run automatically on schedule or can be triggered manually.

To manually trigger the workflow:
1. Go to the Actions tab in your repository
2. Select "GitHub Release Monitor" workflow
3. Click "Run workflow"

## How It Works

1. The script periodically checks the GitHub API for new releases in the specified repositories
2. When a new release is detected, it formats an email notification with release details
3. The Gmail MCP tool authenticates with your Gmail account and sends the notification
4. The system keeps track of which releases have already been reported to avoid duplicates

## Troubleshooting

### Common Issues

1. **JSON Parsing Errors**: Ensure your OAuth credentials are properly encoded when using GitHub Actions
2. **Authentication Failures**: Run the tool with `auth` parameter locally first to authenticate:
   ```bash
   npx @gongrzhe/server-gmail-autoauth-mcp auth
   ```
3. **Rate Limiting**: Use a GitHub token to increase API rate limits

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- GitHub API for providing the release information
- Google's Gmail API for email functionality

---

Made with ❤️ by [GongRzhe](https://github.com/GongRzhe)
