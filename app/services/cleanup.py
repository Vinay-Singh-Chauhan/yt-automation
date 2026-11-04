from pathlib import Path

from google.cloud import storage

from app.config import Settings


class AssetStore:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = storage.Client(project=settings.project_id)

    def archive_run(self, run_id: str, work_dir: Path) -> list[str]:
        bucket = self._client.bucket(self._settings.bucket_name)
        uploaded: list[str] = []
        for path in sorted(work_dir.iterdir()):
            if not path.is_file():
                continue
            blob_name = f"runs/{run_id}/{path.name}"
            bucket.blob(blob_name).upload_from_filename(str(path))
            uploaded.append(blob_name)
        return uploaded

    @staticmethod
    def delete_local(work_dir: Path) -> None:
        for path in work_dir.iterdir():
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                import shutil

                shutil.rmtree(path)
        work_dir.rmdir()

    def delete_run(self, run_id: str) -> None:
        bucket = self._client.bucket(self._settings.bucket_name)
        blobs = list(bucket.list_blobs(prefix=f"runs/{run_id}/"))
        for blob in blobs:
            blob.delete()
