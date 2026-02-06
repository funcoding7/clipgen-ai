# ClipGen AI

ClipGen AI is a powerful video processing application that uses AI to extract viral clips from long-form videos, convert them into Shorts/Reels format (9:16), and enables semantic search across video content.

## Features

-   **AI Clip Extraction**: Automatically identifies and extracts potential viral clips from uploaded videos or YouTube URLs.
-   **Shorts Conversion**: Converts standard 16:9 clips into 9:16 vertical format suitable for TikTok, Instagram Reels, and YouTube Shorts.
-   **Semantic Search**: Search for specific moments within videos using natural language queries (powered by Vector Store).
-   **Background Processing**: Uses Celery and Redis for handling robust video processing tasks asynchronously.
-   **User Management**: Secure authentication and user management via Clerk.

## Tech Stack

-   **Frontend**: Next.js 15, React 19, Tailwind CSS, Clerk (Auth)
-   **Backend**: FastAPI, Celery, SQLAlchemy
-   **AI/ML**: Google Gemini AI (Generative AI), ChromaDB (Vector Search)
-   **Infrastructure**: Docker (PostgreSQL, Redis), AWS S3 (Storage)

## Prerequisites

-   Python 3.10+
-   Node.js 18+
-   Docker & Docker Compose
-   AWS Account (for S3)
-   Clerk Account (for Auth)
-   Google AI Studio API Key

## Setup & Installation

### 1. Database & Redis (Docker)
Start the PostgreSQL and Redis containers:
```bash
docker compose up -d
```

### 2. Backend Setup
Navigate to the root directory and set up the Python environment:
```bash
# Create virtual environment
python3 -m venv env
source env/bin/activate

# Install dependencies
pip install -r requirements.txt  # Ensure you have a requirements.txt, otherwise install manually based on imports
```

**Environment Variables**: Create a `.env` file in the root directory:
```env
DATABASE_URL=postgresql://clipgen:clipgen@localhost:5433/clipgen
REDIS_URL=redis://localhost:6379/0
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_BUCKET_NAME=your_bucket_name
GEMINI_API_KEY=your_gemini_key
```

**Run the Backend**:
```bash
# Start FastAPI server
uvicorn app.main:app --reload

# Start Celery worker (in a separate terminal)
celery -A app.tasks worker --loglevel=info
```

### 3. Frontend Setup
Navigate to the `frontend` directory:
```bash
cd frontend
npm install
```

**Environment Variables**: Create `.env.local` in `frontend/`:
```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your_clerk_key
CLERK_SECRET_KEY=your_clerk_secret
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Run the Frontend**:
```bash
npm run dev
```

## Usage

1.  Sign up/Login via the frontend.
2.  Upload a video file or paste a YouTube URL.
3.  Wait for the AI to process and extract clips.
4.  View extracted clips on the dashboard.
5.  Click "Convert to Shorts" to generate a vertical version of a clip.
6.  Use the search bar to find specific moments in your videos.

## License

[MIT](LICENSE)
