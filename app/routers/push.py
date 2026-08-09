from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.push_subscription import VapidPublicKeyRead

router = APIRouter(prefix="/push", tags=["push"])


# Public by design -- the VAPID public key is meant to be handed to the
# browser's PushManager.subscribe({applicationServerKey}), not kept secret
# (only vapid_private_key, used server-side to sign push messages, is).
@router.get("/vapid-public-key", response_model=VapidPublicKeyRead)
async def get_vapid_public_key() -> VapidPublicKeyRead:
    return VapidPublicKeyRead(public_key=get_settings().vapid_public_key)
