import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)


# Shape matches the browser's own PushSubscription.toJSON() from
# PushManager.subscribe() -- {endpoint, keys: {p256dh, auth}} -- so the
# frontend can pass that object straight through with no reshaping.
class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(min_length=1)
    keys: PushSubscriptionKeys


class PushSubscriptionDelete(BaseModel):
    endpoint: str = Field(min_length=1)


class PushSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint: str
    user_agent: str | None
    created_at: datetime


class PushTestResultRead(BaseModel):
    total_subscriptions: int
    delivered: int


class VapidPublicKeyRead(BaseModel):
    public_key: str
