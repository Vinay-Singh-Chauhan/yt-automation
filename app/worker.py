import json
import logging
import sys

from app.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.worker '<request-json>'")
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        raise SystemExit("Worker argument must be a JSON object") from exc
    video_id = run_pipeline(payload.get("payload", payload), payload.get("message_id"))
    print(json.dumps({"youtube_video_id": video_id, "skipped": video_id is None}))


if __name__ == "__main__":
    main()
