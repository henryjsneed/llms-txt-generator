# llms.txt Generator

Generate a spec-compliant [llms.txt](https://llmstxt.org/) file for any website by analyzing its structure and content.

## Architecture

```
              ┌──────────────────────────────────┐
              │  Next.js on Amplify (SSR)        │
              │  UI + API routes                 │
              └──┬──────────┬──────────────┬─────┘
    submit URL   │          │ enqueue      │ poll
                 │          ▼              │
                 │         SQS             │
                 │          │              │
                 │          ▼              │
                 │  ┌────────────────────┐ │
                 │  │  Python Lambda     │ │
                 │  │                    │ │
                 │  │  1. Fetch homepage │ │
                 │  │  2. Priority-BFS   │ │
                 │  │  3. Extract pages  │ │
                 │  │  4. Group sections │ │
                 │  │  5. Generate txt   │ │
                 │  └────────┬───────────┘ │
                 │  write    │             │
                 │  result   │             │ read
                 ▼           ▼             ▼
              ┌──────────────────────────────────┐
              │           DynamoDB               │
              │  job state + generated output    │
              │  (24h TTL)                       │
              └──────────────────────────────────┘
```

On submission, the frontend writes a PENDING job item to DynamoDB and enqueues a message to SQS. The Lambda worker consumes the job, crawls the target site, generates llms.txt, and updates the same DynamoDB item with the output and a COMPLETED status. The frontend polls every two seconds and renders the result when the job is COMPLETED.  

**Components:**

- **Next.js (Amplify Hosting)** — UI and API routes. Job creation writes to DynamoDB and enqueues to SQS. Polling reads from DynamoDB.
- **SQS + DLQ** — buffers crawl jobs. 3 retries before dead-letter queue.
- **Python Lambda** — consumes SQS messages, crawls the target site with SSRF protection, extracts page metadata, groups pages into sections, generates spec-compliant llms.txt, writes result to DynamoDB.
- **DynamoDB** — single table with 24h TTL on crawl job items. Stores job state and generated output.
- **AWS CDK** — provisions all backend infrastructure.

### Key Design Decisions

- **Two languages**: TypeScript for the web layer (Next.js/React), Python for the crawl pipeline (BeautifulSoup, httpx, lxml). The shared contract is DynamoDB so there's no inter service API to maintain.
- **Priority-BFS from homepage links**: the homepage is fetched first, and its links seed the BFS frontier. This means the crawl budget goes to pages the site itself considers important. Depth is the sole priority signal.
- **Polling over WebSockets**: crawls take 30–180s; polling every 2s is 15–60 lightweight GetItem calls. WebSockets would add API Gateway, connection management, and Lambda concurrency concerns for no UX benefit.
- **Job record only**: page metadata lives in Lambda memory during processing and only the final llms.txt string is persisted. DynamoDB usage is 3 operations per job (PutItem, UpdateItem × 2).
- **SSRF defense in depth**: the frontend rejects obviously invalid URLs client-side. Lambda revalidates with DNS resolution and IP range checks before every fetch, including redirects.
- **robots.txt compliance**: the crawler fetches and respects robots.txt before crawling. The user agent string identifies the bot and includes a contact URL.
- **24h TTL**: results auto-expire so there's no stale data accumulation and limited storage cost.

## Live App

**[https://main.dan3xvvgw8g9b.amplifyapp.com](https://main.dan3xvvgw8g9b.amplifyapp.com)**

1. Enter a website URL (e.g., `https://www.apple.com`)
2. Click "Generate"
3. Wait 30–120 seconds while the site is crawled
4. View, copy, or download the generated llms.txt

The output follows the [llms.txt spec](https://llmstxt.org/): an H1 title, blockquote description, H2 sections with categorized page links, and an Optional section for smaller categories.

## Local Development

### Prerequisites

- Node.js 20+
- Python 3.12+
- Docker (for DynamoDB Local)

### Setup

Three terminals: DynamoDB Local, Next.js, and the generator.

```bash
git clone <repo-url> && cd llms-txt-generator

# Terminal 1 — DynamoDB Local
docker compose up -d

# Terminal 2 — Next.js
cd frontend
cp ../.env.template .env.local
npm install
npm run dev # http://localhost:3000

# Terminal 3 — Python generator
cd generator
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
DYNAMODB_ENDPOINT=http://localhost:8000 python -m llms_txt_generator.dev_runner
```

Submit a URL at [localhost:3000](http://localhost:3000). The dev runner picks it up within 2 seconds, crawls the site, and writes the result back to DynamoDB Local.

```bash
# Run tests
cd generator && source .venv/bin/activate && pytest tests/ -v
```

### Environment Variables

See `[.env.template](.env.template)` for the canonical list. Copy to `frontend/.env.local` for local dev; set the same keys in Amplify for production.


| Variable              | Description                        | Example                                   |
| --------------------- | ---------------------------------- | ----------------------------------------- |
| `AWS_REGION`          | AWS region                         | `us-west-2`                               |
| `DYNAMODB_TABLE_NAME` | DynamoDB table name                | `llms-txt-generator`                      |
| `SQS_QUEUE_URL`       | SQS queue URL                      | `https://sqs.us-west-2.amazonaws.com/...` |
| `DYNAMODB_ENDPOINT`   | Local DynamoDB endpoint (dev only) | `http://localhost:8000`                   |


## Deployment

### 1. Backend (CDK)

```bash
cd infra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cdk bootstrap   # first time only
cdk deploy
```

Note the stack outputs: `TableName`, `QueueUrl`, `AmplifyPolicyArn`, `DlqUrl`. CDK builds and pushes the Lambda container image during deploy.

### 2. Frontend (Amplify)

1. AWS Amplify console → "Host web app" → connect GitHub repo
2. Set platform to **WEB_COMPUTE** (SSR), app root to `frontend/`
3. Add environment variables from CDK outputs: `DYNAMODB_TABLE_NAME`, `SQS_QUEUE_URL`
4. Attach the `AmplifyPolicyArn` IAM policy to the Amplify service role
5. Deploy — Amplify builds and hosts automatically on push

## Project Structure

```
llms-txt-generator/
├── frontend/               # Next.js (TypeScript)
│   ├── src/app/            # Pages and API routes
│   ├── src/components/     # React components
│   └── src/lib/            # AWS clients, types, URL validation
├── generator/              # Python Lambda
│   ├── src/llms_txt_generator/
│   │   ├── handler.py      # Lambda entry point
│   │   ├── crawler/        # SSRF-safe fetcher, BFS orchestrator, robots.txt
│   │   ├── extraction/     # HTML metadata extraction (BeautifulSoup)
│   │   ├── ranking/        # Page grouping by URL structure
│   │   └── generator/      # llms.txt markdown generation
│   └── tests/
├── infra/                  # AWS CDK (Python)
│   └── stacks/backend_stack.py
├── amplify.yml             # Amplify build spec
├── docker-compose.yml      # DynamoDB Local
└── README.md
```

## Crawl Bounds


| Parameter        | Default | Description                                    |
| ---------------- | ------- | ---------------------------------------------- |
| Max pages        | 300     | Total pages crawled per job                    |
| Max depth        | 3       | Link-following depth from homepage             |
| Concurrency      | 5       | Simultaneous HTTP requests                     |
| Per-prefix quota | 10      | Max pages from the same top-level path segment |
| Request timeout  | 10s     | Per-request limit                              |
| Crawl timeout    | 360s    | Total time budget for the entire crawl         |
| Response size    | 5 MB    | Max body size per page                         |


## Future Work

- Result caching for recently-crawled domains
- `llms-full.txt` generation with expanded page contents
- Granular crawl progress in the UI (percentage, current section)
- CloudWatch alarms on DLQ depth and Lambda errors
- DLQ consumer for inspecting and retrying failed jobs
- CDK-managed Amplify provisioning

