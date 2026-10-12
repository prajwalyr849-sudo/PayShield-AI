from dataclasses import dataclass , field
from typing import List

@dataclass

class TransactionItem:
    name: str
    quantity: int
    price: float

@dataclass

class Transaction:
    transaction_id:str
    user_id: str
    merchant_category:str
    merchant_name:str
    amount:float
    currency:str
    payment_method:str
    items:list[TransactionItem]=field(default_factory=list)
    agent_name:str="unknown"
    agent_confidence:float=0.0