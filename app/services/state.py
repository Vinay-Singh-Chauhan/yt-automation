from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from app.config import Settings


class RunState:
    def __init__(self, settings: Settings):
        self._collection = firestore.Client(project=settings.project_id).collection(
            settings.firestore_collection
        )

    def create_if_new(self, run_id: str, payload: dict) -> bool:
        reference = self._collection.document(run_id)
        transaction = self._collection._client.transaction()

        @firestore.transactional
        def create(transaction):
            snapshot = reference.get(transaction=transaction)
            if snapshot.exists:
                current = snapshot.to_dict() or {}
                if current.get("status") == "complete":
                    return False
                updated_at = current.get("updated_at")
                if (
                    current.get("status") in {"queued", "generating", "rendered", "uploaded"}
                    and updated_at
                    and updated_at > datetime.now(timezone.utc) - timedelta(hours=1)
                ):
                    return False
                retries = current.get("retry_count", 0) + 1
            else:
                retries = 0
            transaction.set(
                reference,
                {
                    "status": "queued",
                    "request": payload,
                    "retry_count": retries,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return True

        return create(transaction)

    def update(self, run_id: str, **fields) -> None:
        self._collection.document(run_id).set(
            {**fields, "updated_at": firestore.SERVER_TIMESTAMP}, merge=True
        )

    def get(self, run_id: str) -> dict:
        snapshot = self._collection.document(run_id).get()
        return snapshot.to_dict() or {}

    def get_recent_titles(self, limit: int = 15) -> list[str]:
        """Fetch recently generated/uploaded video titles to avoid duplicate topics."""
        try:
            query = (
                self._collection.order_by("updated_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            titles = []
            for doc in query:
                data = doc.to_dict() or {}
                title = data.get("title")
                if title and title not in titles:
                    titles.append(title)
            return titles
        except Exception:
            # Non-blocking fallback if indexes or permissions are not yet ready
            return []
