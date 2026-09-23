from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class Transaction(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    source: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, le=1e15, allow_inf_nan=False)
    currency: str = Field(default="USD", min_length=2, max_length=30)
    payment_format: str = Field(default="Wire", max_length=40)
    label: Literal[0, 1] | None = None

    @field_validator("timestamp")
    @classmethod
    def normalize_time(cls, value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @field_validator("id", "source", "target", "currency")
    @classmethod
    def clean_text(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Value must contain printable characters")
        return value

    @field_validator("currency")
    @classmethod
    def canonical_currency(cls, value):
        aliases = {"US Dollar":"USD", "Euro":"EUR", "UK Pound":"GBP", "Swiss Franc":"CHF", "Yen":"JPY", "Yuan":"CNY", "Rupee":"INR", "Ruble":"RUB", "Canadian Dollar":"CAD", "Australian Dollar":"AUD", "Bitcoin":"BTC", "Mexican Peso":"MXN", "Brazil Real":"BRL", "Saudi Riyal":"SAR", "Shekel":"ILS"}
        return {k.casefold():v for k,v in aliases.items()}.get(value.casefold(), value.upper())


class Scenario(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    origin: Literal["demo", "custom", "ibm"] = "custom"
    transactions: list[Transaction] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({t.id for t in self.transactions}) != len(self.transactions):
            raise ValueError("Transaction IDs must be unique")
        return self
