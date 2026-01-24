# FreshRoles 🔍

**Automated job discovery for software engineering internships**

FreshRoles monitors LinkedIn for new job postings, scores them against your profile using AI, and sends real-time notifications to your phone via [ntfy](https://ntfy.sh).

## Features

- **LinkedIn Monitoring**: Scrapes LinkedIn job search using Playwright + cookies
- **AI Matching**: Uses Ollama embeddings to score jobs against your profile
- **Real-time Notifications**: Push notifications via ntfy.sh
- **Customizable Profiles**: Define your ideal role, skills, and location preferences
- **US-Only Filtering**: Built-in filters for US-based positions

## Quick Start

### 1. Install

```bash
# Clone the repo
git clone https://github.com/WutIsHummus/FreshRoles.git
cd FreshRoles

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -e .
pip install playwright beautifulsoup4
playwright install chromium
```

### 2. Set Up LinkedIn Cookies

1. Log into LinkedIn in your browser
2. Export cookies using a browser extension (e.g., "Cookie-Editor")
3. Save as `cookies.json` in the project root

### 3. Set Up Notifications

1. Install the [ntfy app](https://ntfy.sh) on your phone
2. Subscribe to a topic (e.g., `my-job-alerts`)
3. Use that topic name with the `--ntfy-topic` flag

### 4. (Optional) Set Up AI Matching

For best results, install [Ollama](https://ollama.com) for local AI embeddings:

```bash
# Install Ollama from ollama.com, then:
ollama serve  # Start the server
ollama pull nomic-embed-text  # Download the embedding model
```

### 5. Run the Monitor

```bash
python -m freshroles monitor \
  --query "software engineer intern" \
  --ntfy-topic my-job-alerts
```

## Configuration

### Profile Setup

Create your profile in `configs/profiles/your_name.yaml`:

```yaml
name: your_name

desired_roles:
  - Software Engineer Intern
  - Backend Intern
  - Full Stack Intern

must_have_keywords:
  - intern

must_not_keywords:
  - senior
  - staff
  - 5+ years

preferred_locations:
  - United States
  - Remote

remote_preference: remote
min_score_threshold: 0.15
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TPR_SECONDS` | 86400 | Lookback window (24h) |
| `FRESHROLES_NTFY_TOPIC` | - | ntfy topic for notifications |

## Commands

```bash
# Monitor continuously (main command)
python -m freshroles monitor --query "software engineer intern" --ntfy-topic my-topic

# One-time LinkedIn scan
python -m freshroles scan-linkedin --query "backend intern" --location "Texas"

# Match existing jobs against profile
python -m freshroles match --profile configs/profiles/your_name.yaml

# Create a new profile interactively
python -m freshroles create-profile
```

## Project Structure

```
FreshRoles/
├── freshroles/
│   ├── adapters/         # LinkedIn scraper
│   ├── matching/         # AI scoring + keyword matching
│   ├── notify/           # ntfy notifications
│   ├── storage/          # SQLite database
│   └── cli.py            # Main CLI
├── configs/
│   ├── profiles/         # User profiles (YAML)
│   └── companies/        # Company configs (optional)
├── cookies.json          # LinkedIn cookies (you create this)
└── freshroles.db         # SQLite database (auto-created)
```

## Requirements

- Python 3.11+
- Playwright (for LinkedIn scraping)
- Ollama (optional, for AI matching)

## How It Works

1. **Scrape**: Uses Playwright + cookies to fetch LinkedIn job search results
2. **Parse**: Extracts job data from HTML/embedded JSON
3. **Deduplicate**: Checks SQLite database for already-seen jobs
4. **Score**: Uses Ollama embeddings + keyword matching to score jobs
5. **Notify**: Sends matching jobs to ntfy.sh
6. **Repeat**: Polls every 5 minutes (configurable)

## License

MIT License - See [LICENSE](LICENSE)

## Contributing

Pull requests welcome! Please open an issue first to discuss changes.
