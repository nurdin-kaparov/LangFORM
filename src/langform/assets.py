from __future__ import annotations

import hashlib
import mimetypes
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .schemas import AssetRecord
from .storage import JSONStore


def _iso_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


class AssetRegistry:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.store = JSONStore(self.workspace / "registry" / "assets.json", [])

    def list(self) -> list[AssetRecord]:
        return [AssetRecord.from_dict(x) for x in self.store.load()]

    def get(self, asset_id: str) -> AssetRecord:
        for asset in self.list():
            if asset.asset_id == asset_id:
                return asset
        raise KeyError(f"Asset not found: {asset_id}")

    def save_asset(self, asset: AssetRecord) -> None:
        assets = self.list()
        replaced = False
        for i, existing in enumerate(assets):
            if existing.asset_id == asset.asset_id:
                assets[i] = asset
                replaced = True
                break
        if not replaced:
            assets.append(asset)
        self.store.save([a.to_dict() for a in assets])

    def register(self, reference: str, copy_uploaded: bool = False) -> AssetRecord:
        if reference.startswith(("http://", "https://")):
            parsed = urlparse(reference)
            name = Path(parsed.path).name or parsed.netloc
            asset = AssetRecord(
                asset_id=f"asset_{uuid.uuid4().hex[:12]}",
                reference_type="web_url",
                location=reference,
                name=name,
                file_type=Path(name).suffix.lower() or None,
                status="registered",
            )
            self.save_asset(asset)
            return asset

        path = Path(reference).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Asset file not found: {path}")

        if copy_uploaded:
            upload_dir = self.workspace / "uploaded_assets"
            upload_dir.mkdir(parents=True, exist_ok=True)
            target = upload_dir / path.name
            if target.exists():
                target = upload_dir / f"{path.stem}_{uuid.uuid4().hex[:8]}{path.suffix}"
            shutil.copy2(path, target)
            path = target.resolve()
            ref_type = "uploaded_file"
        else:
            ref_type = "local_path"

        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()

        asset = AssetRecord(
            asset_id=f"asset_{uuid.uuid4().hex[:12]}",
            reference_type=ref_type,
            location=str(path),
            name=path.name,
            file_type=path.suffix.lower() or mimetypes.guess_extension(mimetypes.guess_type(path.name)[0] or ""),
            size_bytes=stat.st_size,
            created_at=_iso_timestamp(stat.st_ctime),
            modified_at=_iso_timestamp(stat.st_mtime),
            sha256=digest,
            status="registered",
        )
        self.save_asset(asset)
        return asset
